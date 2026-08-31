export const CLASSIFIER_V9_PROMPT_VERSION = "v9";
export const MAX_CONTENT_CHARS = 40_000;
export const CONTENT_BUDGET_POLICY = "per_page_equal_quota_redistribute_v1";

const PAGE_BREAK = "\n--- PAGE BREAK ---\n";
const TRUNCATED_MARKER = "[TRUNCATED]";

export const CLASSIFIER_V9_TEMPLATE = `You classify the role of an entity relative to a specific product for an internal sourcing evidence system.

Use only the supplied domain, page title, product context, and extracted page content. The classification must always be relative to product_context. Never infer a role from the domain name, site appearance, wording quality, or an unsupported claim. When evidence is missing, ambiguous, or contradictory, return UNKNOWN. A false MANUFACTURER classification is worse than a false negative.

Allowed role values are exactly: MANUFACTURER, DISTRIBUTOR, TRADER, MARKETPLACE_OR_DIRECTORY, NOT_A_SUPPLIER, NOT_A_COMPANY, UNCERTAIN, UNKNOWN.
Allowed confidence values are exactly: HIGH, MEDIUM, LOW.

Class definitions:
- MANUFACTURER: the company itself produces or operates manufacturing for the product in product_context, supported by an active own-production verb or stronger process, plant, certification, technological, or industrial evidence rather than a generic manufacturer label.
- DISTRIBUTOR: the company distributes or resells the product in product_context without supported evidence that it manufactures that product itself.
- TRADER: the company trades, imports, exports, or intermediates the product in product_context without supported own production.
- MARKETPLACE_OR_DIRECTORY: the page lists multiple sellers, suppliers, companies, or trade records as a marketplace, directory, or data platform rather than representing one supplier.
- NOT_A_SUPPLIER: the entity is a company, but the supplied evidence shows that it does not sell or supply the product in product_context.
- NOT_A_COMPANY: the page is a news portal, market report, government body, association, or other non-company information source.
- UNCERTAIN: the evidence supports that this is a potentially relevant company, but its product-relative commercial role remains conflicting or cannot be separated between manufacturer, distributor, and trader.
- UNKNOWN: the supplied evidence is absent or insufficient to establish that the entity is relevant to the product or to assign any other class.

Classification unit:
- The task is to classify the entity that owns the domain, using its pages as evidence about that entity.
- A page about a discontinued, sold out, or out-of-line product does not make the entity NOT_A_SUPPLIER; it is evidence about one product, not about the nature of the company.
- An article, blog post, comparison, or ranking published on the company's own site does not make the entity MARKETPLACE_OR_DIRECTORY or NOT_A_COMPANY. Those classes describe the nature of the entity: a marketplace or directory exists to list third parties, while NOT_A_COMPANY is a news outlet, market-research consultancy, government body, or association. A trading company that publishes a ranking remains a trading company.
- When the domain content is predominantly commercial, such as products, quotations, and sales contacts, and only part is editorial, classify according to the commercial content.

Role precedence (apply before the numbered commercial-role rules):
- First decide whether the entity itself is NOT_A_COMPANY or MARKETPLACE_OR_DIRECTORY. These entity-nature classes take precedence over every commercial role.
- Next decide DISTRIBUTOR. Once the DISTRIBUTOR rule matches, do not apply the TRADER fallback rules below.
- An entity is DISTRIBUTOR when any of these conditions is true: it explicitly identifies itself as a "distributor", "dealer", "reseller", "authorized distributor", or equivalent; it sells named products from identifiable manufacturer brands, such as "Spectrum Chemical graded products" or "we distribute Brand X", without claiming own production; or it operates as a distribution or logistics arm, including warehousing or fulfillment, for third-party products.
- DISTRIBUTOR is not TRADER. A distributor has a public identity tied to reselling identifiable brands. A trader buys and resells without a public brand affiliation or under a generic own brand.

Decision rules (apply in this exact order after the role-precedence checks):
1. Selling, representing, or acting as an agent for third-party brands is decisive for TRADER when the DISTRIBUTOR rule above does not apply. Examples include "agents for different brands", "we supply Lomon, Taihai, panzhihua", and "LOMON Brand". This remains TRADER even if the entity also calls itself a manufacturer.
2. Multiple self-declared roles mean TRADER. If the entity describes itself simultaneously as a manufacturer and as a trading company, agent, or distributor, such as "Business Type: Manufacturer, Distributor/Wholesaler, Agent, Trade Company", and there is no own-production proof, the role is TRADER.
3. MANUFACTURER requires both an active first-person own-production verb and specific evidence of the entity's own facilities. The verb may be "we manufacture", "we produce", "is a producer of", or "operates plants producing". The facility evidence must include at least one of: the name or location of an owned factory or plant; production capacity stated numerically in tons, MT, or volume; or a detailed production-process description explicitly attributed to the entity's own facilities. There must also be no evidence of selling a third-party brand.
   - MANUFACTURER: "WOTAIchem operates three dedicated titanium dioxide manufacturing plants in China" because it identifies plants and process. "ICL operates phosphoric acid plants in Israel and China with combined capacity of 1.2M tons" because it provides locations and capacity.
   - TRADER with needs_review true: "Veeransh Chemicals manufactures and supplies Phosphoric Acid to Vietnam" because it has a verb but no plant or capacity. "SNDB uses state-of-the-art manufacturing processes such as the wet process" because the generic process is not attributed to its own facility.
   - TRADER without needs_review: third-party brand resale or multiple self-declared roles such as manufacturer plus trading company or agent.
   - A generic manufacturer label without an active production verb is not enough, for example "we are a professional manufacturer" or "leading manufacturer in China".
4. The intermediation fallback is subordinate to rule 3. Commercializing without proof of production is intermediation when the active production verb and specific own-facility evidence required by rule 3 are not both present. Classify such an entity as TRADER rather than UNCERTAIN.
5. When an active first-person production verb exists but the required specific plant, process, or numeric capacity evidence is absent, classify the entity as TRADER and set needs_review to true.

Review rule:
- needs_review must be true whenever decision rule 5 applies or confidence is LOW; otherwise it may be false.

Evidence rules:
- citation must be a literal, contiguous excerpt from extracted_content; whitespace may be normalized, but words and punctuation must not be changed.
- Do not use the domain or title as the citation.
- For a commercial company role, citation must evidence the entity's commercial activity with the product. It does not need to prove the exact role. A literal institutional sentence showing that the entity commercializes the product is valid.
- For MARKETPLACE_OR_DIRECTORY or NOT_A_COMPANY, citation must evidence the nature of the entity.
- Choose the shortest excerpt that satisfies the applicable citation rule.
- [TRUNCATED] marks the end of a page whose remaining content was omitted by the deterministic per-page budget.
- If no excerpt satisfying the applicable citation rule exists in extracted_content, set role to UNKNOWN and citation to an empty string.
- reasoning must be short and must not add facts absent from the supplied input.
- marketplace_signal and noise_signal are human-configured retrieval hints. They are evidence inputs to consider, not automatic classifications.

Return exactly one JSON object with no Markdown, commentary, or additional keys:
{{"role":"UNKNOWN","confidence":"LOW","citation":"","reasoning":"short evidence-based reason","needs_review":true}}

domain:
{normalized_domain}

title:
{title}

product_context:
{product_context}

evidence_truncated:
{evidence_truncated}

marketplace_signal:
{marketplace_signal_text}

marketplace_signal_reason:
{marketplace_signal_reason}

noise_signal:
{noise_signal_text}

noise_signal_reason:
{noise_signal_reason}

extracted_content:
{budgeted_evidence.content}
`;

export interface ClassifierPromptInput {
  domain: string;
  title: string;
  extractedContent: string;
  productContext: string;
  marketplaceSignal?: boolean;
  marketplaceSignalReason?: string;
  noiseSignal?: boolean;
  noiseSignalReason?: string;
}

export interface RenderedClassifierPrompt {
  prompt: string;
  evidence: string;
  evidenceTruncated: boolean;
}

function normalizeDomain(value: string) {
  const raw = value.trim().toLowerCase().replace(/\/$/, "");
  try {
    return new URL(raw.includes("://") ? raw : `https://${raw}`).host;
  } catch {
    return raw.replace(/^[a-z]+:\/\//, "").split("/")[0];
  }
}

function allocatePageCharacters(lengths: number[]) {
  const allocations = Array(lengths.length).fill(0) as number[];
  let remainingBudget = MAX_CONTENT_CHARS;
  let active = lengths.map((_, index) => index);
  while (active.length > 0) {
    const quota = Math.floor(remainingBudget / active.length);
    const fitting = active.filter((index) => lengths[index] <= quota);
    if (fitting.length > 0) {
      for (const index of fitting) {
        allocations[index] = lengths[index];
        remainingBudget -= lengths[index];
      }
      const fittingSet = new Set(fitting);
      active = active.filter((index) => !fittingSet.has(index));
      continue;
    }

    for (const index of active) allocations[index] = quota;
    const remainder = remainingBudget - quota * active.length;
    for (const index of active.slice(0, remainder)) allocations[index] += 1;
    break;
  }
  return allocations;
}

export function budgetClassifierEvidence(extractedContent: string) {
  const pages = extractedContent.split(PAGE_BREAK);
  const allocations = allocatePageCharacters(pages.map((page) => page.length));
  let evidenceTruncated = false;
  const evidence = pages
    .map((page, index) => {
      const allocation = allocations[index];
      if (allocation >= page.length) return page;
      evidenceTruncated = true;
      return `${page.slice(0, allocation)}${TRUNCATED_MARKER}`;
    })
    .join(PAGE_BREAK);
  return { evidence, evidenceTruncated };
}

export function renderClassifierV9Prompt(
  input: ClassifierPromptInput,
): RenderedClassifierPrompt {
  const { evidence, evidenceTruncated } = budgetClassifierEvidence(
    input.extractedContent,
  );
  const values: Record<string, string> = {
    normalized_domain: normalizeDomain(input.domain),
    title: input.title,
    product_context: input.productContext,
    evidence_truncated: String(evidenceTruncated),
    marketplace_signal_text: String(input.marketplaceSignal ?? false),
    marketplace_signal_reason: input.marketplaceSignalReason ?? "",
    noise_signal_text: String(input.noiseSignal ?? false),
    noise_signal_reason: input.noiseSignalReason ?? "",
    "budgeted_evidence.content": evidence,
  };
  const leftBrace = "\u0000LEFT_BRACE\u0000";
  const rightBrace = "\u0000RIGHT_BRACE\u0000";
  let prompt = CLASSIFIER_V9_TEMPLATE.replaceAll("{{", leftBrace).replaceAll(
    "}}",
    rightBrace,
  );
  for (const [key, value] of Object.entries(values)) {
    prompt = prompt.replaceAll(`{${key}}`, () => value);
  }
  return {
    prompt: prompt.replaceAll(leftBrace, "{").replaceAll(rightBrace, "}"),
    evidence,
    evidenceTruncated,
  };
}
