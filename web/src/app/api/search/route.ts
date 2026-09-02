import { resolveMP } from "@/data/mp-codes";
import type { SupabaseClient } from "@supabase/supabase-js";

import { createServerSupabaseClient } from "../../../lib/supabase-server";
import { extractJsonArray } from "../../../lib/gemini-results";

export const runtime = "nodejs";

const GEMINI_ENDPOINT =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent";

const ROLES = ["MANUFACTURER", "DISTRIBUTOR", "TRADER"] as const;
const CONFIDENCE_LEVELS = ["HIGH", "MEDIUM", "LOW"] as const;

type SupplierRole = (typeof ROLES)[number];
type Confidence = (typeof CONFIDENCE_LEVELS)[number];

interface SearchFilters {
  excludeCountries?: string[];
  onlyCountries?: string[];
  brazilOnly?: boolean;
}

interface SearchRequest {
  query: string;
  filters?: SearchFilters;
  userEmail: string;
  exclude?: string[];
  forceRefresh?: boolean;
}

interface SupplierResult {
  company_name: string;
  website: string;
  country: string;
  role: SupplierRole;
  confidence: Confidence;
  notes: string;
}

interface GeminiResponse {
  candidates?: Array<{
    content?: {
      parts?: Array<{ text?: string }>;
    };
  }>;
  usageMetadata?: {
    promptTokenCount?: number;
    candidatesTokenCount?: number;
  };
}

interface SavedSearchResult {
  id: string;
  query: string;
  resolved_query: string | null;
  mp_code: number | null;
  filters: unknown;
  results: unknown;
  created_at: string;
}

function errorResponse(error: string, status: number, details?: string) {
  return Response.json(
    { error, code: status, ...(details === undefined ? {} : { details }) },
    { status },
  );
}

function normalizeCountries(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((country): country is string => typeof country === "string")
    .map((country) => country.trim())
    .filter(Boolean);
}

function normalizeCompanyNames(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((company): company is string => typeof company === "string")
    .map((company) => company.trim())
    .filter(Boolean);
}

function formatCountries(countries: string[], fallback: string) {
  return countries.length > 0 ? countries.join(", ") : fallback;
}

function buildPrompt(
  query: string,
  filters: Required<SearchFilters>,
  mpCode: number | null,
  excludedCompanies: string[],
) {
  const mpContext =
    mpCode === null
      ? ""
      : `\nThe user searched by internal code MP ${mpCode}, which corresponds to: ${query}. Search for suppliers of this product.`;
  const exclusionInstruction =
    excludedCompanies.length === 0
      ? ""
      : `\nIMPORTANT: Do NOT include any of these companies in your results: ${excludedCompanies.join(", ")}. Find OTHER suppliers not in this list.\n`;

  return `You are OniSource, a chemical sourcing intelligence engine.

IMPORTANT: All text fields in your response MUST be written in Brazilian Portuguese (pt-BR). This includes the 'note' field, company descriptions, and any other text. Do NOT write in English.

The user is searching for suppliers of: "${query}"${mpContext}

Filters applied:
- Exclude countries: ${formatCountries(filters.excludeCountries, "none")}
- Search only in countries: ${formatCountries(filters.onlyCountries, "all")}
- Brazil only: ${filters.brazilOnly}
${exclusionInstruction}

Instructions:
1. Identify 8-15 potential suppliers (companies) for this product worldwide, respecting the country filters.
2. For each supplier, provide:
   - company_name
   - website (if known)
   - country
   - role: one of MANUFACTURER, DISTRIBUTOR, TRADER (use these definitions: MANUFACTURER = company that produces the product in own facilities; DISTRIBUTOR = authorized reseller of identified manufacturer brands; TRADER = intermediary, trading company, or company whose production cannot be verified)
   - confidence: HIGH, MEDIUM, or LOW
   - notes: one sentence about why this supplier is relevant
3. Rank results: MANUFACTURER first, then DISTRIBUTOR, then TRADER. Within each group, HIGH confidence first.
4. Respond ONLY with a valid JSON array. No markdown, no backticks, no preamble. Example format:
[{"company_name":"...","website":"...","country":"...","role":"MANUFACTURER","confidence":"HIGH","notes":"..."}]`;
}

function isSupplierResult(value: unknown): value is SupplierResult {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.company_name === "string" &&
    typeof candidate.website === "string" &&
    typeof candidate.country === "string" &&
    typeof candidate.notes === "string" &&
    ROLES.includes(candidate.role as SupplierRole) &&
    CONFIDENCE_LEVELS.includes(candidate.confidence as Confidence)
  );
}

function parseResults(text: string): SupplierResult[] {
  const jsonArray = extractJsonArray(text);
  if (!jsonArray) {
    throw new Error("Gemini response does not contain a JSON array.");
  }

  const parsed: unknown = JSON.parse(jsonArray);
  if (!Array.isArray(parsed) || !parsed.every(isSupplierResult)) {
    throw new Error("Gemini returned an invalid supplier result array.");
  }
  return parsed;
}

function sanitizedErrorMessage(error: unknown, apiKey: string) {
  const message = error instanceof Error ? error.message : String(error);
  return message.replaceAll(apiKey, "***");
}

async function recordSearchHistory(
  supabase: SupabaseClient,
  userEmail: string,
  query: string,
  filters: Required<SearchFilters>,
  results: SupplierResult[],
  tokensUsed: number,
) {
  return supabase.from("searches").insert({
    user_email: userEmail,
    query,
    filters,
    results,
    tokens_used: tokensUsed,
  });
}

export async function POST(request: Request) {
  let body: SearchRequest;

  try {
    body = (await request.json()) as SearchRequest;
  } catch {
    return errorResponse("Invalid JSON request body.", 400);
  }

  const query = typeof body.query === "string" ? body.query.trim() : "";
  const userEmail =
    typeof body.userEmail === "string"
      ? body.userEmail.trim().toLowerCase()
      : "";

  if (!query || !userEmail) {
    return errorResponse("Query and userEmail are required.", 400);
  }

  const filters: Required<SearchFilters> = {
    excludeCountries: normalizeCountries(body.filters?.excludeCountries),
    onlyCountries: normalizeCountries(body.filters?.onlyCountries),
    brazilOnly: body.filters?.brazilOnly === true,
  };
  const excludedCompanies = normalizeCompanyNames(body.exclude);

  if (filters.brazilOnly) {
    filters.excludeCountries = [];
    filters.onlyCountries = [];
  } else if (
    filters.excludeCountries.length > 0 &&
    filters.onlyCountries.length > 0
  ) {
    return errorResponse(
      "Country inclusion and exclusion filters cannot be combined.",
      400,
    );
  }

  const { resolved, mpCode } = resolveMP(query);
  let supabase: SupabaseClient | null = null;
  try {
    supabase = createServerSupabaseClient();
  } catch (error) {
    console.error("Unable to initialize Supabase for search persistence.", error);
  }

  if (supabase && excludedCompanies.length === 0 && body.forceRefresh !== true) {
    const sevenDaysAgo = new Date(
      Date.now() - 7 * 24 * 60 * 60 * 1000,
    ).toISOString();
    const escapedQuery = query.replace(/([\\%_])/g, "\\$1");
    const { data: cachedRows, error: cacheError } = await supabase
      .from("search_results")
      .select("id,query,resolved_query,mp_code,filters,results,created_at")
      .ilike("query", escapedQuery)
      .filter("filters", "eq", JSON.stringify(filters))
      .gte("created_at", sevenDaysAgo)
      .order("created_at", { ascending: false })
      .limit(10);

    if (cacheError) {
      console.error("Unable to check the saved search result cache.", cacheError);
    } else {
      const cachedResult = (cachedRows as SavedSearchResult[] | null)?.find(
        (row) =>
          row.query.trim().toLocaleLowerCase("pt-BR") ===
            query.toLocaleLowerCase("pt-BR") &&
          Array.isArray(row.results) &&
          row.results.every(isSupplierResult),
      );

      if (cachedResult) {
        const cachedResults = cachedResult.results as SupplierResult[];
        const { error: historyError } = await recordSearchHistory(
          supabase,
          userEmail,
          query,
          filters,
          cachedResults,
          0,
        );
        if (historyError) {
          console.error("Unable to record cached search history.", historyError);
        }

        return Response.json({
          results: cachedResults,
          tokens_used: 0,
          resolvedQuery: cachedResult.resolved_query ?? resolved,
          mpCode: cachedResult.mp_code,
          searchResultId: cachedResult.id,
          cached: true,
          createdAt: cachedResult.created_at,
        });
      }
    }
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return errorResponse("GEMINI_API_KEY was not found in the environment.", 500);
  }

  const prompt = buildPrompt(resolved, filters, mpCode, excludedCompanies);
  let geminiData: GeminiResponse;
  let results: SupplierResult[];

  try {
    const endpoint = new URL(GEMINI_ENDPOINT);
    endpoint.searchParams.set("key", apiKey);
    const geminiResponse = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { maxOutputTokens: 8192 },
      }),
    });

    if (!geminiResponse.ok) {
      if (geminiResponse.status === 429) {
        return errorResponse("Gemini rate limit exceeded.", 429);
      }
      if (geminiResponse.status === 503) {
        return errorResponse("Gemini is temporarily unavailable.", 503);
      }
      return errorResponse("Gemini request failed.", geminiResponse.status);
    }

    geminiData = (await geminiResponse.json()) as GeminiResponse;
    const parts = geminiData.candidates?.[0]?.content?.parts;
    if (!parts || parts.length === 0 || !parts[0]?.text?.trim()) {
      return errorResponse(
        "O modelo não retornou resultados. Tente uma busca mais específica.",
        422,
      );
    }

    const responseText = parts[0].text;

    try {
      results = parseResults(responseText);
    } catch {
      return errorResponse(
        "Não foi possível processar a resposta. Tente reformular a busca.",
        422,
        responseText.slice(0, 200),
      );
    }
  } catch (error) {
    return errorResponse(
      "Erro interno na busca.",
      500,
      sanitizedErrorMessage(error, apiKey),
    );
  }

  const tokensUsed =
    (geminiData.usageMetadata?.promptTokenCount ?? 0) +
    (geminiData.usageMetadata?.candidatesTokenCount ?? 0);
  let savedSearchResult: { id: string; created_at: string } | null = null;

  if (supabase) {
    const { data, error } = await supabase
      .from("search_results")
      .insert({
        query,
        resolved_query: resolved,
        mp_code: mpCode,
        filters,
        results,
        result_count: results.length,
        user_email: userEmail,
      })
      .select("id,created_at")
      .single();

    if (error) {
      console.error("Unable to save the search result for reuse.", error);
    } else {
      savedSearchResult = data;
    }
  }

  try {
    const historyClient = supabase ?? createServerSupabaseClient();
    const { error } = await recordSearchHistory(
      historyClient,
      userEmail,
      query,
      filters,
      results,
      tokensUsed,
    );

    if (error) {
      console.error("Unable to record search history.", error);
    }
  } catch (error) {
    console.error("Unable to record search history.", error);
  }

  return Response.json({
    results,
    tokens_used: tokensUsed,
    resolvedQuery: resolved,
    mpCode,
    cached: false,
    ...(savedSearchResult
      ? {
          searchResultId: savedSearchResult.id,
          createdAt: savedSearchResult.created_at,
        }
      : {}),
  });
}
