export interface EvidenceSignals {
  has_production_page: boolean;
  has_certifications: boolean;
  sells_third_party_brands: boolean;
  has_technical_specs: boolean;
}

export type QualityRole =
  | "MANUFACTURER"
  | "DISTRIBUTOR"
  | "TRADER"
  | "UNKNOWN";

export type ClassificationFeedback =
  | "MANUFACTURER_CONFIRMED"
  | "DISTRIBUTOR_CONFIRMED"
  | "TRADER_CONFIRMED"
  | "IRRELEVANT";

export function extractEvidenceSignals(content: string): EvidenceSignals {
  const text = content.toLowerCase();
  return {
    has_production_page:
      /\b(factory|factories|plant|plants|production facilit(?:y|ies)|manufacturing facilit(?:y|ies)|nossa fábrica|nossas fábricas|unidade(?:s)? produtiva(?:s)?)\b/i.test(
        text,
      ),
    has_certifications:
      /\b(iso\s*9001|iso\s*14001|reach|fda|certifica(?:ção|ções)|certified)\b/i.test(
        text,
      ),
    sells_third_party_brands:
      /\b(authorized distributor|authorised distributor|dealer for|reseller of|we distribute|distribuidor autorizado|revendedor autorizado|representante da marca|third[- ]party brands?)\b/i.test(
        text,
      ),
    has_technical_specs:
      /\b(technical data sheet|ficha técnica|tds|sds|safety data sheet|specifications?|especifica(?:ção|ções))\b/i.test(
        text,
      ),
  };
}

export function calculateEvidenceScore(input: {
  role: QualityRole;
  signals: EvidenceSignals;
  fromDirectory?: boolean;
  autoDowngraded?: boolean;
  classificationFeedback?: ClassificationFeedback | null;
}) {
  if (
    input.classificationFeedback === "MANUFACTURER_CONFIRMED" ||
    input.classificationFeedback === "DISTRIBUTOR_CONFIRMED"
  ) {
    return 150;
  }
  const base = {
    MANUFACTURER: 100,
    DISTRIBUTOR: 70,
    TRADER: 40,
    UNKNOWN: 10,
  }[input.role];
  return (
    base +
    (input.signals.has_production_page ? 15 : 0) +
    (input.signals.has_certifications ? 10 : 0) +
    (input.signals.has_technical_specs ? 10 : 0) +
    (input.fromDirectory ? 5 : 0) -
    (input.signals.sells_third_party_brands ? 20 : 0) -
    (input.autoDowngraded ? 30 : 0)
  );
}

export function normalizeSupplierDomain(value: string) {
  const raw = value.trim().toLowerCase().replace(/\/$/, "");
  try {
    return new URL(raw.includes("://") ? raw : `https://${raw}`).host;
  } catch {
    return raw.replace(/^[a-z]+:\/\//, "").split("/")[0];
  }
}

export function deduplicateItemsByDomain<T>(
  items: T[],
  getUrl: (item: T) => string,
) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const domain = normalizeSupplierDomain(getUrl(item));
    if (!domain || seen.has(domain)) return false;
    seen.add(domain);
    return true;
  });
}
