const CAS_PATTERN = /\b\d{2,7}-\d{2}-\d\b/;

const KNOWN_CAS_BY_MP: Record<number, string> = {
  41: "7664-38-2",
  52: "7664-38-2",
  110: "13463-67-7",
};

export interface ProductIdentity {
  canonicalName: string;
  casNumber: string | null;
  cacheKey: string;
}

export function normalizeCanonicalProductName(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");
}

function knownCasFromName(value: string) {
  const normalized = normalizeCanonicalProductName(value);
  if (
    normalized.includes("acido fosforico") ||
    normalized.includes("phosphoric acid")
  ) {
    return "7664-38-2";
  }
  if (
    normalized.includes("dioxido de titanio") ||
    normalized.includes("titanium dioxide")
  ) {
    return "13463-67-7";
  }
  return null;
}

export function buildProductIdentity(
  inputQuery: string,
  resolvedProductName: string,
  mpCode: number | null,
): ProductIdentity {
  const explicitCas = inputQuery.match(CAS_PATTERN)?.[0] ?? null;
  const casNumber =
    explicitCas ??
    (mpCode === null ? null : KNOWN_CAS_BY_MP[mpCode] ?? null) ??
    knownCasFromName(resolvedProductName) ??
    knownCasFromName(inputQuery);
  const canonicalName = normalizeCanonicalProductName(resolvedProductName);
  return {
    canonicalName,
    casNumber,
    cacheKey: casNumber ? `cas:${casNumber}` : `name:${canonicalName}`,
  };
}
