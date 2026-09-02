import {
  renderClassifierV9Prompt,
  type ClassifierPromptInput,
} from "./prompts/classifier-v9";

const TAVILY_ENDPOINT = "https://api.tavily.com/search";
const GEMINI_ENDPOINT =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent";

export const SUPPLIER_ROLES = [
  "MANUFACTURER",
  "DISTRIBUTOR",
  "TRADER",
] as const;
export const CLASSIFIER_ROLES = [
  ...SUPPLIER_ROLES,
  "MARKETPLACE_OR_DIRECTORY",
  "NOT_A_SUPPLIER",
  "NOT_A_COMPANY",
  "UNCERTAIN",
  "UNKNOWN",
] as const;
export const CONFIDENCE_LEVELS = ["HIGH", "MEDIUM", "LOW"] as const;

export type SupplierRole = (typeof SUPPLIER_ROLES)[number];
export type ClassifierRole = (typeof CLASSIFIER_ROLES)[number];
export type Confidence = (typeof CONFIDENCE_LEVELS)[number];

export interface PipelineFilters {
  excludeCountries: string[];
  onlyCountries: string[];
  brazilOnly: boolean;
}

export interface SupplierResult {
  company_name: string;
  website: string;
  country: string;
  role: SupplierRole;
  confidence: Confidence;
  notes: string;
  citation: string;
  citation_verified: boolean;
  needs_review: boolean;
  evidence_truncated: boolean;
  source_urls: string[];
}

interface TavilyResult {
  title?: string;
  url?: string;
  content?: string;
  raw_content?: string | null;
  score?: number;
}

interface TavilyResponse {
  results?: TavilyResult[];
}

interface GeminiResponse {
  candidates?: Array<{
    content?: { parts?: Array<{ text?: string }> };
  }>;
  usageMetadata?: {
    promptTokenCount?: number;
    candidatesTokenCount?: number;
  };
}

interface ClassifierResponse {
  role: ClassifierRole;
  confidence: Confidence;
  citation: string;
  reasoning: string;
  needs_review: boolean;
}

interface DomainEvidence {
  domain: string;
  title: string;
  content: string;
  urls: string[];
}

type FetchImplementation = typeof fetch;

export class SearchPipelineError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export function normalizeResultDomain(value: string) {
  const raw = value.trim().toLowerCase().replace(/\/$/, "");
  try {
    return new URL(raw.includes("://") ? raw : `https://${raw}`).host;
  } catch {
    return raw.replace(/^[a-z]+:\/\//, "").split("/")[0];
  }
}

export function deduplicateByDomain(results: TavilyResult[]) {
  const seen = new Set<string>();
  return results.filter((result) => {
    if (!result.url) return false;
    const domain = normalizeResultDomain(result.url);
    if (!domain || seen.has(domain)) return false;
    seen.add(domain);
    return true;
  });
}

function groupEvidenceByDomain(results: TavilyResult[]): DomainEvidence[] {
  const grouped = new Map<string, DomainEvidence>();
  for (const result of results) {
    if (!result.url) continue;
    const domain = normalizeResultDomain(result.url);
    if (!domain) continue;
    const content = (result.raw_content || result.content || "").trim();
    const existing = grouped.get(domain);
    if (existing) {
      if (content) {
        existing.content = existing.content
          ? `${existing.content}\n--- PAGE BREAK ---\n${content}`
          : content;
      }
      existing.urls.push(result.url);
      continue;
    }
    grouped.set(domain, {
      domain,
      title: result.title?.trim() || domain,
      content,
      urls: [result.url],
    });
  }
  return [...grouped.values()];
}

function buildSearchQuery(
  productContext: string,
  filters: PipelineFilters,
  excludedCompanies: string[],
) {
  const location = filters.brazilOnly
    ? " Brazil"
    : filters.onlyCountries.length > 0
      ? ` ${filters.onlyCountries.join(" OR ")}`
      : "";
  const exclusions = [
    ...filters.excludeCountries.map((country) => `-${JSON.stringify(country)}`),
    ...excludedCompanies.map((company) => `-${JSON.stringify(company)}`),
  ];
  return `${productContext} manufacturer distributor supplier${location}${
    exclusions.length > 0 ? ` ${exclusions.join(" ")}` : ""
  }`;
}

async function searchTavily(
  query: string,
  apiKey: string,
  fetchImpl: FetchImplementation,
) {
  const response = await fetchImpl(TAVILY_ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      search_depth: "advanced",
      include_answer: false,
      include_raw_content: "text",
      max_results: 15,
    }),
  });
  if (!response.ok) {
    throw new SearchPipelineError(
      response.status === 429
        ? "Tavily rate limit exceeded."
        : "Tavily search request failed.",
      response.status,
    );
  }
  const data = (await response.json()) as TavilyResponse;
  if (!Array.isArray(data.results)) {
    throw new SearchPipelineError("Tavily returned a malformed response.", 502);
  }
  return data.results;
}

function isClassifierResponse(value: unknown): value is ClassifierResponse {
  if (!value || typeof value !== "object") return false;
  const result = value as Record<string, unknown>;
  return (
    CLASSIFIER_ROLES.includes(result.role as ClassifierRole) &&
    CONFIDENCE_LEVELS.includes(result.confidence as Confidence) &&
    typeof result.citation === "string" &&
    typeof result.reasoning === "string" &&
    typeof result.needs_review === "boolean"
  );
}

function normalizedWhitespace(value: string) {
  return value.split(/\s+/).filter(Boolean).join(" ");
}

async function classifyDomain(
  evidence: DomainEvidence,
  productContext: string,
  apiKey: string,
  fetchImpl: FetchImplementation,
) {
  const promptInput: ClassifierPromptInput = {
    domain: evidence.domain,
    title: evidence.title,
    extractedContent: evidence.content,
    productContext,
  };
  const rendered = renderClassifierV9Prompt(promptInput);
  const response = await fetchImpl(GEMINI_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey,
    },
    body: JSON.stringify({
      contents: [{ parts: [{ text: rendered.prompt }] }],
      generationConfig: {
        temperature: 0,
        responseMimeType: "application/json",
        maxOutputTokens: 2048,
      },
    }),
  });
  if (!response.ok) {
    throw new SearchPipelineError(
      response.status === 429
        ? "Gemini rate limit exceeded."
        : response.status === 503
          ? "Gemini is temporarily unavailable."
          : "Gemini classification request failed.",
      response.status,
    );
  }
  const data = (await response.json()) as GeminiResponse;
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text?.trim()) {
    throw new SearchPipelineError("Gemini returned an empty classification.", 502);
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new SearchPipelineError("Gemini returned invalid classification JSON.", 502);
  }
  if (!isClassifierResponse(parsed)) {
    throw new SearchPipelineError("Gemini returned an invalid classification.", 502);
  }
  const normalizedCitation = normalizedWhitespace(parsed.citation);
  const citationVerified =
    normalizedCitation.length > 0 &&
    normalizedWhitespace(rendered.evidence).includes(normalizedCitation);
  return {
    classification: parsed,
    citationVerified,
    evidenceTruncated: rendered.evidenceTruncated,
    tokensUsed:
      (data.usageMetadata?.promptTokenCount ?? 0) +
      (data.usageMetadata?.candidatesTokenCount ?? 0),
  };
}

function companyNameFromTitle(title: string, domain: string) {
  const name = title.split(/\s+[|–—-]\s+/)[0]?.trim();
  return name || domain;
}

export async function runSearchPipeline(
  input: {
    productContext: string;
    filters: PipelineFilters;
    excludedCompanies: string[];
    tavilyApiKey: string;
    geminiApiKey: string;
  },
  fetchImpl: FetchImplementation = fetch,
) {
  const query = buildSearchQuery(
    input.productContext,
    input.filters,
    input.excludedCompanies,
  );
  const tavilyResults = await searchTavily(query, input.tavilyApiKey, fetchImpl);
  const evidenceByDomain = groupEvidenceByDomain(tavilyResults);
  const classified = await Promise.all(
    evidenceByDomain.map(async (evidence) => ({
      evidence,
      ...(await classifyDomain(
        evidence,
        input.productContext,
        input.geminiApiKey,
        fetchImpl,
      )),
    })),
  );
  const results: SupplierResult[] = classified.flatMap((item) => {
    if (!SUPPLIER_ROLES.includes(item.classification.role as SupplierRole)) {
      return [];
    }
    return [
      {
        company_name: companyNameFromTitle(
          item.evidence.title,
          item.evidence.domain,
        ),
        website: `https://${item.evidence.domain}`,
        country: "Não informado",
        role: item.classification.role as SupplierRole,
        confidence: item.classification.confidence,
        notes: item.classification.reasoning,
        citation: item.classification.citation,
        citation_verified: item.citationVerified,
        needs_review: item.classification.needs_review,
        evidence_truncated: item.evidenceTruncated,
        source_urls: item.evidence.urls,
      },
    ];
  });
  return {
    results,
    tokensUsed: classified.reduce((sum, item) => sum + item.tokensUsed, 0),
  };
}
