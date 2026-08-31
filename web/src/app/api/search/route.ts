import { resolveMP } from "@/data/mp-codes";
import {
  CONFIDENCE_LEVELS,
  runSearchPipeline,
  SearchPipelineError,
  SUPPLIER_ROLES,
  type Confidence,
  type SupplierResult,
  type SupplierRole,
} from "@/lib/search-pipeline";
import { createServerSupabaseClient } from "@/lib/supabase-server";
import type { SupabaseClient } from "@supabase/supabase-js";

export const runtime = "nodejs";

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

function normalizeStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function isSupplierResult(value: unknown): value is SupplierResult {
  if (!value || typeof value !== "object") return false;
  const result = value as Record<string, unknown>;
  return (
    typeof result.company_name === "string" &&
    typeof result.website === "string" &&
    typeof result.country === "string" &&
    typeof result.notes === "string" &&
    SUPPLIER_ROLES.includes(result.role as SupplierRole) &&
    CONFIDENCE_LEVELS.includes(result.confidence as Confidence)
  );
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
    excludeCountries: normalizeStrings(body.filters?.excludeCountries),
    onlyCountries: normalizeStrings(body.filters?.onlyCountries),
    brazilOnly: body.filters?.brazilOnly === true,
  };
  const excludedCompanies = normalizeStrings(body.exclude);
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

  const tavilyApiKey = process.env.TAVILY_API_KEY;
  const geminiApiKey = process.env.GEMINI_API_KEY;
  if (!tavilyApiKey) {
    return errorResponse("TAVILY_API_KEY was not found in the environment.", 500);
  }
  if (!geminiApiKey) {
    return errorResponse("GEMINI_API_KEY was not found in the environment.", 500);
  }

  let results: SupplierResult[];
  let tokensUsed: number;
  try {
    const pipeline = await runSearchPipeline({
      productContext: resolved,
      filters,
      excludedCompanies,
      tavilyApiKey,
      geminiApiKey,
    });
    results = pipeline.results;
    tokensUsed = pipeline.tokensUsed;
  } catch (error) {
    if (error instanceof SearchPipelineError) {
      return errorResponse(error.message, error.status);
    }
    return errorResponse("Erro interno na busca.", 500);
  }

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
    if (error) console.error("Unable to record search history.", error);
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
