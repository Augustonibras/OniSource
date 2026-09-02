import type { SupabaseClient } from "@supabase/supabase-js";

import {
  BRAZILIAN_REGIONS,
  CONTINENTS,
} from "@/data/onibras-catalog";
import { extractJsonArray } from "@/lib/gemini-results";
import {
  filterSalesResultsByLocation,
  isSouthAmericaLocation,
} from "@/lib/sales-geography";
import { createServerSupabaseClient } from "@/lib/supabase-server";

export const runtime = "nodejs";

const GEMINI_ENDPOINT =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent";
const LOCATION_TYPES = ["brazil_region", "country", "continent"] as const;
const PROSPECT_ROLES = ["Mill/Plant", "Distributor", "Industry"] as const;
const CONFIDENCE_LEVELS = ["Alta", "Média", "Baixa"] as const;

type LocationType = (typeof LOCATION_TYPES)[number];
type ProspectRole = (typeof PROSPECT_ROLES)[number];
type ProspectConfidence = (typeof CONFIDENCE_LEVELS)[number];

interface SalesRequest {
  product?: string;
  productDescription?: string;
  productApplication?: string;
  productMarket?: string;
  locationType?: LocationType;
  locationValue?: string;
  userEmail?: string;
  exclude?: string[];
  forceRefresh?: boolean;
}

interface ProspectResult {
  company: string;
  country: string;
  website: string;
  role: ProspectRole;
  confidence: ProspectConfidence;
  note: string;
}

interface GeminiResponse {
  candidates?: Array<{
    content?: {
      parts?: Array<{ text?: string }>;
    };
  }>;
}

interface SavedSalesSearch {
  id: string;
  product_name: string;
  product_market: string;
  location_type: LocationType;
  location_value: string;
  results: unknown;
  created_at: string;
}

function errorResponse(error: string, status: number, details?: string) {
  return Response.json(
    { error, code: status, ...(details === undefined ? {} : { details }) },
    { status },
  );
}

function normalizeNames(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((name): name is string => typeof name === "string")
    .map((name) => name.trim())
    .filter(Boolean);
}

function locationDescription(locationType: LocationType, locationValue: string) {
  if (locationType === "brazil_region") {
    const label =
      BRAZILIAN_REGIONS.find((region) => region.value === locationValue)?.label ??
      locationValue;
    return `Brazil, specifically the ${label} region`;
  }
  if (locationType === "continent") {
    const label =
      CONTINENTS.find((continent) => continent.value === locationValue)?.label ??
      locationValue;
    return `Continent: ${label} (find companies in multiple countries across this continent)`;
  }
  return `Country: ${locationValue}`;
}

function buildPrompt(
  product: string,
  productDescription: string,
  productApplication: string,
  productMarket: string,
  location: string,
  excludedCompanies: string[],
  excludeBrazil: boolean,
) {
  const excludeInstruction =
    excludedCompanies.length > 0
      ? `IMPORTANT: Do NOT include any of these companies: ${excludedCompanies.join(", ")}. Find OTHER potential customers not in this list.`
      : "";
  const brazilInstruction = excludeBrazil
    ? "IMPORTANT: Do NOT include companies located in Brazil. Return only potential customers from other South American countries."
    : "";

  return `You are a sales intelligence assistant for OniBras Produtos Químicos, a Brazilian specialty chemical company.

TASK: Find potential customers (buyers) for the following OniBras product in the specified location.

PRODUCT: ${product}
DESCRIPTION: ${productDescription}
APPLICATION: ${productApplication}
MARKET SEGMENT: ${productMarket}

LOCATION: ${location}

Search for:
- Sugar mills, ethanol plants, distilleries (for sugar & ethanol products)
- Water treatment plants, municipal water utilities, industrial effluent treatment companies (for water treatment products)
- Paint manufacturers, coatings companies, ink producers (for paints & coatings products)
- Industrial plants, manufacturing facilities, maintenance companies (for industrial products)
- Chemical distributors that serve the above industries in the target region

For each potential customer found, provide:
- company: Company name
- country: Country
- website: Company website URL (if found)
- role: one of "Mill/Plant", "Distributor", "Industry"
- confidence: "Alta", "Média", or "Baixa"
- note: Brief description in Brazilian Portuguese of why this company is a potential customer, mentioning their industry and relevance

${excludeInstruction}
${brazilInstruction}

IMPORTANT: All text fields in your response MUST be written in Brazilian Portuguese (pt-BR).

Respond ONLY with a JSON array. No markdown fences, no explanations. Example:
[{"company":"Usina São Martinho","country":"Brazil","website":"https://www.saomartinho.com.br","role":"Mill/Plant","confidence":"Alta","note":"Uma das maiores usinas de açúcar e etanol do Brasil, potencial consumidor de reagentes de clarificação e análise laboratorial."}]`;
}

function isProspectResult(value: unknown): value is ProspectResult {
  if (!value || typeof value !== "object") {
    return false;
  }
  const prospect = value as Record<string, unknown>;
  return (
    typeof prospect.company === "string" &&
    typeof prospect.country === "string" &&
    typeof prospect.website === "string" &&
    typeof prospect.note === "string" &&
    PROSPECT_ROLES.includes(prospect.role as ProspectRole) &&
    CONFIDENCE_LEVELS.includes(prospect.confidence as ProspectConfidence)
  );
}

function parseResults(text: string): ProspectResult[] {
  const jsonArray = extractJsonArray(text);
  if (!jsonArray) {
    throw new Error("Gemini response does not contain a JSON array.");
  }
  const parsed: unknown = JSON.parse(jsonArray);
  if (!Array.isArray(parsed) || !parsed.every(isProspectResult)) {
    throw new Error("Gemini returned an invalid prospect result array.");
  }
  return parsed;
}

function sanitizedErrorMessage(error: unknown, apiKey: string) {
  const message = error instanceof Error ? error.message : String(error);
  return message.replaceAll(apiKey, "***");
}

async function findCachedResult(
  supabase: SupabaseClient,
  product: string,
  locationType: LocationType,
  locationValue: string,
) {
  const sevenDaysAgo = new Date(
    Date.now() - 7 * 24 * 60 * 60 * 1000,
  ).toISOString();
  const escapedProduct = product.replace(/([\\%_])/g, "\\$1");
  const escapedLocation = locationValue.replace(/([\\%_])/g, "\\$1");
  const { data, error } = await supabase
    .from("sales_searches")
    .select("*")
    .ilike("product_name", escapedProduct)
    .eq("location_type", locationType)
    .ilike("location_value", escapedLocation)
    .gte("created_at", sevenDaysAgo)
    .order("created_at", { ascending: false })
    .limit(10);

  if (error) {
    console.error("Unable to check the sales search cache.", error);
    return null;
  }

  return ((data ?? []) as SavedSalesSearch[]).find(
    (row) =>
      row.product_name.trim().toLocaleLowerCase("pt-BR") ===
        product.toLocaleLowerCase("pt-BR") &&
      row.location_value.trim().toLocaleLowerCase("pt-BR") ===
        locationValue.toLocaleLowerCase("pt-BR") &&
      Array.isArray(row.results) &&
      row.results.every(isProspectResult),
  );
}

export async function POST(request: Request) {
  let body: SalesRequest;
  try {
    body = (await request.json()) as SalesRequest;
  } catch {
    return errorResponse("Invalid JSON request body.", 400);
  }

  const product = body.product?.trim() ?? "";
  const productDescription = body.productDescription?.trim() ?? "";
  const productApplication = body.productApplication?.trim() ?? "";
  const productMarket = body.productMarket?.trim() ?? "";
  const locationType = body.locationType;
  const locationValue = body.locationValue?.trim() ?? "";
  const userEmail = body.userEmail?.trim().toLowerCase() ?? "";
  const excludedCompanies = normalizeNames(body.exclude);
  const excludeBrazil = isSouthAmericaLocation(locationType ?? "", locationValue);

  if (
    !product ||
    !productDescription ||
    !productApplication ||
    !productMarket ||
    !locationType ||
    !LOCATION_TYPES.includes(locationType) ||
    !locationValue ||
    !userEmail
  ) {
    return errorResponse("Product, location and userEmail are required.", 400);
  }

  let supabase: SupabaseClient | null = null;
  try {
    supabase = createServerSupabaseClient();
  } catch (error) {
    console.error("Unable to initialize Supabase for sales persistence.", error);
  }

  if (supabase && excludedCompanies.length === 0 && body.forceRefresh !== true) {
    const cachedResult = await findCachedResult(
      supabase,
      product,
      locationType,
      locationValue,
    );
    if (cachedResult) {
      const cachedResults = filterSalesResultsByLocation(
        cachedResult.results as ProspectResult[],
        locationType,
        locationValue,
      );
      return Response.json({
        results: cachedResults,
        salesSearchId: cachedResult.id,
        cached: true,
        resultCount: cachedResults.length,
        createdAt: cachedResult.created_at,
      });
    }
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return errorResponse("GEMINI_API_KEY was not found in the environment.", 500);
  }

  const prompt = buildPrompt(
    product,
    productDescription,
    productApplication,
    productMarket,
    locationDescription(locationType, locationValue),
    excludedCompanies,
    excludeBrazil,
  );
  let results: ProspectResult[];

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

    const geminiData = (await geminiResponse.json()) as GeminiResponse;
    const parts = geminiData.candidates?.[0]?.content?.parts;
    if (!parts || parts.length === 0 || !parts[0]?.text?.trim()) {
      return errorResponse("O modelo não retornou resultados.", 422);
    }

    try {
      results = filterSalesResultsByLocation(
        parseResults(parts[0].text),
        locationType,
        locationValue,
      );
    } catch {
      return errorResponse(
        "Não foi possível processar a resposta. Tente reformular a busca.",
        422,
        parts[0].text.slice(0, 200),
      );
    }
  } catch (error) {
    return errorResponse(
      "Erro interno na busca de clientes.",
      500,
      sanitizedErrorMessage(error, apiKey),
    );
  }

  let savedSearch: { id: string; created_at: string } | null = null;
  if (supabase) {
    const { data, error } = await supabase
      .from("sales_searches")
      .insert({
        product_name: product,
        product_market: productMarket,
        location_type: locationType,
        location_value: locationValue,
        results,
        result_count: results.length,
        user_email: userEmail,
      })
      .select("id,created_at")
      .single();

    if (error) {
      console.error("Unable to save the sales search result.", error);
    } else {
      savedSearch = data;
    }
  }

  return Response.json({
    results,
    cached: false,
    resultCount: results.length,
    ...(savedSearch
      ? { salesSearchId: savedSearch.id, createdAt: savedSearch.created_at }
      : {}),
  });
}
