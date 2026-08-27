import { resolveMP } from "@/data/mp-codes";

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

function formatCountries(countries: string[], fallback: string) {
  return countries.length > 0 ? countries.join(", ") : fallback;
}

function buildPrompt(
  query: string,
  filters: Required<SearchFilters>,
  mpCode: number | null,
) {
  const mpContext =
    mpCode === null
      ? ""
      : `\nThe user searched by internal code MP ${mpCode}, which corresponds to: ${query}. Search for suppliers of this product.`;

  return `You are OniSource, a chemical sourcing intelligence engine.

The user is searching for suppliers of: "${query}"${mpContext}

Filters applied:
- Exclude countries: ${formatCountries(filters.excludeCountries, "none")}
- Search only in countries: ${formatCountries(filters.onlyCountries, "all")}
- Brazil only: ${filters.brazilOnly}

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

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return errorResponse("GEMINI_API_KEY was not found in the environment.", 500);
  }

  const { resolved, mpCode } = resolveMP(query);
  const prompt = buildPrompt(resolved, filters, mpCode);
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

  try {
    const supabase = createServerSupabaseClient();
    const { error } = await supabase.from("searches").insert({
      user_email: userEmail,
      query,
      filters,
      results,
      tokens_used: tokensUsed,
    });

    if (error) {
      return errorResponse("Unable to save the search result.", 500);
    }
  } catch {
    return errorResponse("Unable to save the search result.", 500);
  }

  return Response.json({
    results,
    tokens_used: tokensUsed,
    resolvedQuery: resolved,
    mpCode,
  });
}
