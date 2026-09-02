import industrialDirectories from "../../../config/industrial_directories.json";

import {
  renderClassifierV9Prompt,
  type ClassifierPromptInput,
} from "./prompts/classifier-v9";
import {
  calculateEvidenceScore,
  deduplicateItemsByDomain,
  extractEvidenceSignals,
  normalizeSupplierDomain,
  type ClassificationFeedback,
  type EvidenceSignals,
} from "./search-quality";

const TAVILY_ENDPOINT = "https://api.tavily.com/search";
const GEMINI_ENDPOINT =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent";
const PAGE_BREAK = "\n--- PAGE BREAK ---\n";
const MAX_EXPANSION_QUERIES = 6;

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
  from_directory: boolean;
  evidence_signals: EvidenceSignals;
  auto_downgraded: boolean;
  evidence_score: number;
  classification_feedback: ClassificationFeedback | null;
  feedback_user_email: string | null;
  previously_verified: boolean;
}

interface TavilyResult {
  title?: string;
  url?: string;
  content?: string;
  raw_content?: string | null;
  score?: number;
  fromDirectory?: boolean;
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
  fromDirectory: boolean;
}

interface SearchQueryPlan {
  query: string;
  includeDomains?: string[];
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

export const normalizeResultDomain = normalizeSupplierDomain;

export function deduplicateByDomain(results: TavilyResult[]) {
  return deduplicateItemsByDomain(results, (result) => result.url ?? "");
}

function isIndustrialDirectory(domain: string) {
  return Object.values(industrialDirectories)
    .flat()
    .some(
      (directory) => domain === directory || domain.endsWith(`.${directory}`),
    );
}

function groupEvidenceByDomain(results: TavilyResult[]): DomainEvidence[] {
  const grouped = new Map<string, DomainEvidence>();
  for (const result of results) {
    if (!result.url) continue;
    const domain = normalizeResultDomain(result.url);
    if (!domain) continue;
    const content = (result.raw_content || result.content || "").trim();
    const fromDirectory = result.fromDirectory === true || isIndustrialDirectory(domain);
    const existing = grouped.get(domain);
    if (existing) {
      if (content) {
        existing.content = existing.content
          ? `${existing.content}${PAGE_BREAK}${content}`
          : content;
      }
      existing.urls.push(result.url);
      existing.fromDirectory ||= fromDirectory;
      continue;
    }
    grouped.set(domain, {
      domain,
      title: result.title?.trim() || domain,
      content,
      urls: [result.url],
      fromDirectory,
    });
  }
  return [...grouped.values()];
}

function locationTerms(filters: PipelineFilters) {
  if (filters.brazilOnly) return " Brazil";
  if (filters.onlyCountries.length > 0) {
    return ` ${filters.onlyCountries.join(" OR ")}`;
  }
  return "";
}

function excludedTerms(filters: PipelineFilters, companies: string[]) {
  return [
    ...filters.excludeCountries.map((country) => `-${JSON.stringify(country)}`),
    ...companies.map((company) => `-${JSON.stringify(company)}`),
  ];
}

function regionalDirectories(filters: PipelineFilters) {
  const countries = filters.brazilOnly
    ? ["brazil"]
    : filters.onlyCountries.map((country) =>
        country
          .normalize("NFD")
          .replace(/[\u0300-\u036f]/g, "")
          .toLowerCase(),
      );
  if (countries.some((country) => country === "brazil" || country === "brasil")) {
    return industrialDirectories.brazil;
  }
  if (countries.includes("china")) return industrialDirectories.china;
  const latamCountries = new Set([
    "argentina",
    "bolivia",
    "chile",
    "colombia",
    "ecuador",
    "mexico",
    "paraguay",
    "peru",
    "uruguay",
    "venezuela",
  ]);
  if (countries.some((country) => latamCountries.has(country))) {
    return industrialDirectories.latam;
  }
  return [
    ...industrialDirectories.china,
    ...industrialDirectories.brazil,
    ...industrialDirectories.latam,
  ];
}

export function buildRoundOneQueries(
  productContext: string,
  filters: PipelineFilters,
  excludedCompanies: string[],
): SearchQueryPlan[] {
  const location = locationTerms(filters);
  const exclusions = excludedTerms(filters, excludedCompanies);
  const suffix = exclusions.length > 0 ? ` ${exclusions.join(" ")}` : "";
  return [
    {
      query: `${productContext} manufacturer distributor supplier${location}${suffix}`,
    },
    {
      query: `${productContext} manufacturer supplier${location}${suffix}`,
      includeDomains: industrialDirectories.global,
    },
    {
      query: `${productContext} industrial supplier${location}${suffix}`,
      includeDomains: regionalDirectories(filters),
    },
  ];
}

export function buildRoundTwoQueries(
  productContext: string,
  firstRound: SupplierResult[],
): SearchQueryPlan[] {
  const manufacturerExpansion = firstRound
    .filter((result) => result.role === "MANUFACTURER")
    .slice(0, 3)
    .map((result) => ({
      query: `${JSON.stringify(result.company_name)} distributor dealer reseller`,
    }));
  return [
    ...manufacturerExpansion,
    { query: `${productContext} manufacturer production plant site` },
  ].slice(0, MAX_EXPANSION_QUERIES);
}

async function searchTavily(
  plan: SearchQueryPlan,
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
      query: plan.query,
      search_depth: "advanced",
      include_answer: false,
      include_raw_content: "text",
      max_results: plan.includeDomains ? 5 : 10,
      ...(plan.includeDomains ? { include_domains: plan.includeDomains } : {}),
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
  return data.results.map((result) => ({
    ...result,
    fromDirectory: plan.includeDomains !== undefined,
  }));
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
    marketplaceSignal: evidence.fromDirectory,
    marketplaceSignalReason: evidence.fromDirectory
      ? "industrial_directory_query"
      : "",
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
  return {
    classification: parsed,
    citationVerified:
      normalizedCitation.length > 0 &&
      normalizedWhitespace(rendered.evidence).includes(normalizedCitation),
    evidenceTruncated: rendered.evidenceTruncated,
    budgetedEvidence: rendered.evidence,
    tokensUsed:
      (data.usageMetadata?.promptTokenCount ?? 0) +
      (data.usageMetadata?.candidatesTokenCount ?? 0),
  };
}

function companyNameFromTitle(title: string, domain: string) {
  const name = title.split(/\s+[|–—-]\s+/)[0]?.trim();
  return name || domain;
}

async function classifyEvidence(
  evidenceItems: DomainEvidence[],
  productContext: string,
  geminiApiKey: string,
  fetchImpl: FetchImplementation,
) {
  const classified = await Promise.all(
    evidenceItems.map(async (evidence) => ({
      evidence,
      ...(await classifyDomain(
        evidence,
        productContext,
        geminiApiKey,
        fetchImpl,
      )),
    })),
  );
  const results = classified.flatMap((item) => {
    if (!SUPPLIER_ROLES.includes(item.classification.role as SupplierRole)) {
      return [];
    }
    const signals = extractEvidenceSignals(item.evidence.content);
    const autoDowngraded =
      item.classification.role === "MANUFACTURER" &&
      signals.sells_third_party_brands &&
      !signals.has_production_page;
    const role = autoDowngraded
      ? "TRADER"
      : (item.classification.role as SupplierRole);
    return [
      {
        company_name: companyNameFromTitle(
          item.evidence.title,
          item.evidence.domain,
        ),
        website: `https://${item.evidence.domain}`,
        country: "Não informado",
        role,
        confidence: item.classification.confidence,
        notes: item.classification.reasoning,
        citation: item.classification.citation,
        citation_verified: item.citationVerified,
        needs_review: item.classification.needs_review,
        evidence_truncated: item.evidenceTruncated,
        source_urls: item.evidence.urls,
        from_directory: item.evidence.fromDirectory,
        evidence_signals: signals,
        auto_downgraded: autoDowngraded,
        evidence_score: calculateEvidenceScore({
          role,
          signals,
          fromDirectory: item.evidence.fromDirectory,
          autoDowngraded,
        }),
        classification_feedback: null,
        feedback_user_email: null,
        previously_verified: false,
      },
    ];
  });
  return {
    results,
    tokensUsed: classified.reduce((sum, item) => sum + item.tokensUsed, 0),
  };
}

function normalizeCompanyName(value: string) {
  return value.trim().toLocaleLowerCase("pt-BR");
}

export async function runSearchPipeline(
  input: {
    productContext: string;
    filters: PipelineFilters;
    excludedCompanies: string[];
    tavilyApiKey: string;
    geminiApiKey: string;
    priorFeedbackResults?: SupplierResult[];
    irrelevantCompanies?: string[];
  },
  fetchImpl: FetchImplementation = fetch,
) {
  const irrelevant = new Set(
    (input.irrelevantCompanies ?? []).map(normalizeCompanyName),
  );
  const exclusions = [
    ...input.excludedCompanies,
    ...(input.irrelevantCompanies ?? []),
  ];
  const roundOnePlans = buildRoundOneQueries(
    input.productContext,
    input.filters,
    exclusions,
  );
  const roundOneRaw = (
    await Promise.all(
      roundOnePlans.map((plan) =>
        searchTavily(plan, input.tavilyApiKey, fetchImpl),
      ),
    )
  ).flat();
  const roundOne = await classifyEvidence(
    groupEvidenceByDomain(roundOneRaw),
    input.productContext,
    input.geminiApiKey,
    fetchImpl,
  );

  const roundTwoPlans = buildRoundTwoQueries(
    input.productContext,
    roundOne.results,
  );
  const roundTwoRaw = (
    await Promise.all(
      roundTwoPlans.map((plan) =>
        searchTavily(plan, input.tavilyApiKey, fetchImpl),
      ),
    )
  ).flat();
  const roundOneDomains = new Set(
    roundOneRaw
      .map((result) => normalizeResultDomain(result.url ?? ""))
      .filter(Boolean),
  );
  const newRoundTwoEvidence = groupEvidenceByDomain(roundTwoRaw).filter(
    (item) => !roundOneDomains.has(item.domain),
  );
  const roundTwo = await classifyEvidence(
    newRoundTwoEvidence,
    input.productContext,
    input.geminiApiKey,
    fetchImpl,
  );

  const combined = [
    ...(input.priorFeedbackResults ?? []),
    ...roundOne.results,
    ...roundTwo.results,
  ].filter(
    (result) =>
      !irrelevant.has(normalizeCompanyName(result.company_name)) &&
      !input.excludedCompanies.some(
        (company) => normalizeCompanyName(company) === normalizeCompanyName(result.company_name),
      ),
  );
  const results = deduplicateItemsByDomain(
    combined,
    (result) => result.website,
  ).sort((left, right) => right.evidence_score - left.evidence_score);
  return {
    results,
    tokensUsed: roundOne.tokensUsed + roundTwo.tokensUsed,
  };
}
