export const NON_COMPANY_DOMAINS = [
  "instagram.com",
  "facebook.com",
  "linkedin.com",
  "twitter.com",
  "x.com",
  "youtube.com",
  "tiktok.com",
  "pinterest.com",
  "reddit.com",
  "wikipedia.org",
  "quora.com",
] as const;

const GENERICIZED_COUNTRY_DOMAINS = new Set([
  "ai",
  "cc",
  "co",
  "io",
  "ly",
  "me",
  "tv",
]);

const COUNTRY_ALIASES = [
  ["África do Sul", "south africa", "africa do sul"],
  ["Alemanha", "germany", "alemanha"],
  ["Arábia Saudita", "saudi arabia", "arabia saudita"],
  ["Argentina", "argentina"],
  ["Austrália", "australia"],
  ["Bélgica", "belgium", "belgica"],
  ["Bolívia", "bolivia"],
  ["Brasil", "brazil", "brasil"],
  ["Canadá", "canada"],
  ["Chile", "chile"],
  ["China", "china"],
  ["Colômbia", "colombia"],
  ["Coreia do Sul", "south korea", "coreia do sul"],
  ["Egito", "egypt", "egito"],
  ["Emirados Árabes Unidos", "united arab emirates", "emirados arabes unidos"],
  ["Equador", "ecuador", "equador"],
  ["Espanha", "spain", "espanha"],
  ["Estados Unidos", "united states", "usa", "estados unidos"],
  ["França", "france", "franca"],
  ["Índia", "india"],
  ["Indonésia", "indonesia"],
  ["Israel", "israel"],
  ["Itália", "italy", "italia"],
  ["Japão", "japan", "japao"],
  ["Jordânia", "jordan", "jordania"],
  ["Malásia", "malaysia", "malasia"],
  ["Marrocos", "morocco", "marrocos"],
  ["México", "mexico"],
  ["Países Baixos", "netherlands", "paises baixos"],
  ["Paquistão", "pakistan", "paquistao"],
  ["Paraguai", "paraguay", "paraguai"],
  ["Peru", "peru"],
  ["Polônia", "poland", "polonia"],
  ["Portugal", "portugal"],
  ["Reino Unido", "united kingdom", "reino unido"],
  ["Rússia", "russia", "russia"],
  ["Singapura", "singapore", "singapura"],
  ["Suíça", "switzerland", "suica"],
  ["Taiwan", "taiwan"],
  ["Tailândia", "thailand", "tailandia"],
  ["Tunísia", "tunisia"],
  ["Turquia", "turkey", "turkiye", "turquia"],
  ["Uruguai", "uruguay", "uruguai"],
  ["Vietnã", "vietnam", "vietna"],
] as const;

const LOCATION_SIGNAL =
  /\b(?:address|based|company|country|distributor|factory|facility|founded|headquartered|located|made|manufacturer|manufacturing plant|office|operations|producer|production site|supplier|endereco|empresa|fabrica|localizad[ao]|pais|planta|sede|sediad[ao]|unidade produtiva)\b/i;

function normalizedDomain(value: string) {
  const raw = value.trim().toLowerCase();
  try {
    return new URL(raw.includes("://") ? raw : `https://${raw}`).hostname;
  } catch {
    return raw.replace(/^[a-z]+:\/\//, "").split(/[/:]/)[0];
  }
}

function folded(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function escaped(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function isBlockedCompanyDomain(value: string) {
  const domain = normalizedDomain(value);
  return NON_COMPANY_DOMAINS.some(
    (blocked) => domain === blocked || domain.endsWith(`.${blocked}`),
  );
}

export function companyNameFromDomain(value: string) {
  const labels = normalizedDomain(value).split(".").filter(Boolean);
  const countrySuffix = labels.at(-1)?.length === 2;
  const secondLevel = labels.at(-2) ?? "";
  const baseIndex =
    countrySuffix && /^(?:co|com|net|org)$/.test(secondLevel)
      ? labels.length - 3
      : labels.length - 2;
  const base = labels[Math.max(0, baseIndex)] ?? normalizedDomain(value);
  return base
    .replace(/[-_]+/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

export function extractCountryFromEvidence(domain: string, content: string) {
  const tld = normalizedDomain(domain).split(".").at(-1) ?? "";
  if (tld.length === 2 && !GENERICIZED_COUNTRY_DOMAINS.has(tld)) {
    const country = new Intl.DisplayNames(["pt-BR"], { type: "region" }).of(
      tld.toUpperCase(),
    );
    if (country && country.toUpperCase() !== tld.toUpperCase()) return country;
  }

  const text = folded(content);
  let earliest: { index: number; country: string } | undefined;
  for (const [country, ...aliases] of COUNTRY_ALIASES) {
    for (const alias of aliases) {
      const matches = text.matchAll(new RegExp(`\\b${escaped(alias)}\\b`, "g"));
      for (const match of matches) {
        const index = match.index ?? 0;
        const context = text.slice(Math.max(0, index - 140), index);
        if (
          LOCATION_SIGNAL.test(context) &&
          (!earliest || index < earliest.index)
        ) {
          earliest = { index, country };
        }
      }
    }
  }
  return earliest?.country ?? "Não informado";
}
