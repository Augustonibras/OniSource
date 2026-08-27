"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";

const SESSION_KEY = "onisource_session";

type SupplierRole = "MANUFACTURER" | "DISTRIBUTOR" | "TRADER";
type Confidence = "HIGH" | "MEDIUM" | "LOW";

interface Session {
  email: string;
  role: string;
}

interface SupplierResult {
  company_name: string;
  website: string;
  country: string;
  role: SupplierRole;
  confidence: Confidence;
  notes: string;
}

interface SearchFilters {
  excludeCountries: string[];
  onlyCountries: string[];
  brazilOnly: boolean;
}

interface SearchApiResponse {
  results?: SupplierResult[];
  tokens_used?: number;
  error?: string;
}

interface CountryTagsProps {
  id: string;
  label: string;
  placeholder: string;
  values: string[];
  disabled: boolean;
  onChange: (values: string[]) => void;
}

const ROLE_SECTIONS: Array<{
  role: SupplierRole;
  title: string;
  icon: string;
  badgeClass: string;
}> = [
  {
    role: "MANUFACTURER",
    title: "Fabricantes",
    icon: "🏭",
    badgeClass: "bg-emerald-100 text-emerald-800",
  },
  {
    role: "DISTRIBUTOR",
    title: "Distribuidores",
    icon: "🚚",
    badgeClass: "bg-blue-100 text-blue-800",
  },
  {
    role: "TRADER",
    title: "Traders",
    icon: "🌐",
    badgeClass: "bg-brand-gold-200 text-amber-900",
  },
];

const CONFIDENCE_STYLES: Record<
  Confidence,
  { label: string; className: string }
> = {
  HIGH: { label: "Alta", className: "bg-emerald-100 text-emerald-800" },
  MEDIUM: { label: "Média", className: "bg-amber-100 text-amber-800" },
  LOW: { label: "Baixa", className: "bg-gray-100 text-gray-600" },
};

const COUNTRY_CODES: Record<string, string> = {
  argentina: "AR",
  australia: "AU",
  brazil: "BR",
  brasil: "BR",
  canada: "CA",
  china: "CN",
  france: "FR",
  franca: "FR",
  germany: "DE",
  alemanha: "DE",
  india: "IN",
  italy: "IT",
  italia: "IT",
  japan: "JP",
  japao: "JP",
  mexico: "MX",
  netherlands: "NL",
  paisesbaixos: "NL",
  southafrica: "ZA",
  coreiadosul: "KR",
  southkorea: "KR",
  spain: "ES",
  espanha: "ES",
  unitedkingdom: "GB",
  reinounido: "GB",
  unitedstates: "US",
  estadosunidos: "US",
  vietnam: "VN",
};

function subscribeToSession() {
  return () => undefined;
}

function getSessionSnapshot() {
  return localStorage.getItem(SESSION_KEY);
}

function getServerSessionSnapshot() {
  return null;
}

function parseSession(value: string | null): Session | null {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as Partial<Session>;
    if (typeof parsed.email === "string" && typeof parsed.role === "string") {
      return { email: parsed.email, role: parsed.role };
    }
  } catch {
    return null;
  }

  return null;
}

function countryFlag(country: string) {
  const normalized = country
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z]/g, "")
    .toLowerCase();
  const code =
    country.length === 2 ? country.toUpperCase() : COUNTRY_CODES[normalized];

  if (!code || !/^[A-Z]{2}$/.test(code)) {
    return "";
  }

  return String.fromCodePoint(
    ...code.split("").map((character) => 127397 + character.charCodeAt(0)),
  );
}

function websiteUrl(website: string) {
  if (!website.trim()) {
    return null;
  }

  const candidate = /^https?:\/\//i.test(website)
    ? website
    : `https://${website}`;

  try {
    const url = new URL(candidate);
    return ["http:", "https:"].includes(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

function buildFilterPromptLine(filters: SearchFilters) {
  if (filters.brazilOnly) {
    return "- Restringir a busca a fornecedores no Brasil";
  }
  if (filters.onlyCountries.length > 0) {
    return `- Buscar somente em: ${filters.onlyCountries.join(", ")}`;
  }
  if (filters.excludeCountries.length > 0) {
    return `- Excluir fornecedores de: ${filters.excludeCountries.join(", ")}`;
  }
  return "- Sem restrição geográfica adicional";
}

function buildAdvancedPrompt(query: string, filters: SearchFilters) {
  return `Preciso encontrar fornecedores internacionais de ${query}.

Requisitos:
- Buscar fabricantes reais (com fábrica própria, capacidade produtiva comprovada)
- Incluir distribuidores autorizados se houver vantagem logística
- Evitar intermediários sem valor agregado identificável
${buildFilterPromptLine(filters)}

Para cada fornecedor, forneça:
1. Nome da empresa e website
2. País de origem e localização da planta (se fabricante)
3. Classificação: Fabricante / Distribuidor / Trader
4. Produtos relevantes e capacidade
5. Contato comercial (se disponível publicamente)

Priorize fabricantes com presença industrial verificável. Ordene por relevância.`;
}

function CountryTags({
  id,
  label,
  placeholder,
  values,
  disabled,
  onChange,
}: CountryTagsProps) {
  const [draft, setDraft] = useState("");

  function addCountry() {
    const country = draft.trim();
    if (!country) {
      return;
    }
    if (!values.some((value) => value.toLowerCase() === country.toLowerCase())) {
      onChange([...values, country]);
    }
    setDraft("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      addCountry();
    }
    if (event.key === "Backspace" && !draft && values.length > 0) {
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div>
      <label
        htmlFor={id}
        className="mb-2 block text-sm font-medium text-gray-700"
      >
        {label}
      </label>
      <div
        className={`flex min-h-12 flex-wrap items-center gap-2 rounded-lg border bg-white px-3 py-2 transition focus-within:ring-4 ${
          disabled
            ? "cursor-not-allowed border-gray-200 bg-gray-100 opacity-60"
            : "border-gray-300 focus-within:border-brand-blue-700 focus-within:ring-brand-blue-300/30"
        }`}
      >
        {values.map((country) => (
          <span
            key={country.toLowerCase()}
            className="inline-flex items-center gap-1 rounded-full bg-brand-blue-50 px-3 py-1 text-sm text-brand-blue-800"
          >
            {country}
            <button
              type="button"
              onClick={() =>
                onChange(values.filter((value) => value !== country))
              }
              disabled={disabled}
              aria-label={`Remover ${country}`}
              className="ml-1 font-bold text-brand-blue-700 hover:text-brand-blue-900"
            >
              ×
            </button>
          </span>
        ))}
        <input
          id={id}
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={addCountry}
          disabled={disabled}
          placeholder={values.length === 0 ? placeholder : ""}
          className="min-w-52 flex-1 bg-transparent py-1 text-sm text-gray-900 outline-none placeholder:text-gray-400 disabled:cursor-not-allowed"
        />
      </div>
    </div>
  );
}

export default function SearchPage() {
  const router = useRouter();
  const sessionValue = useSyncExternalStore(
    subscribeToSession,
    getSessionSnapshot,
    getServerSessionSnapshot,
  );
  const session = useMemo(() => parseSession(sessionValue), [sessionValue]);
  const [query, setQuery] = useState("");
  const [isFiltersOpen, setIsFiltersOpen] = useState(false);
  const [brazilOnly, setBrazilOnly] = useState(false);
  const [onlyCountries, setOnlyCountries] = useState<string[]>([]);
  const [excludeCountries, setExcludeCountries] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<SupplierResult[] | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [submittedFilters, setSubmittedFilters] = useState<SearchFilters | null>(
    null,
  );
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!session) {
      router.replace("/");
    }
  }, [router, session]);

  function handleSignOut() {
    localStorage.removeItem(SESSION_KEY);
    router.replace("/");
  }

  function handleBrazilToggle() {
    setBrazilOnly((current) => !current);
    setOnlyCountries([]);
    setExcludeCountries([]);
  }

  function handleOnlyCountries(values: string[]) {
    setOnlyCountries(values);
    if (values.length > 0) {
      setExcludeCountries([]);
    }
  }

  function handleExcludeCountries(values: string[]) {
    setExcludeCountries(values);
    if (values.length > 0) {
      setOnlyCountries([]);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!normalizedQuery || !session?.email) {
      return;
    }

    const filters: SearchFilters = {
      brazilOnly,
      onlyCountries,
      excludeCountries,
    };

    setIsLoading(true);
    setErrorMessage("");
    setResults(null);

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: normalizedQuery,
          filters,
          userEmail: session.email,
        }),
      });
      const data = (await response.json()) as SearchApiResponse;

      if (!response.ok || !data.results) {
        setErrorMessage(data.error ?? "Não foi possível concluir a pesquisa.");
        return;
      }

      setSubmittedQuery(normalizedQuery);
      setSubmittedFilters(filters);
      setResults(data.results);
    } catch {
      setErrorMessage("Não foi possível conectar ao serviço de pesquisa.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCopyPrompt() {
    if (!submittedFilters) {
      return;
    }
    await navigator.clipboard.writeText(
      buildAdvancedPrompt(submittedQuery, submittedFilters),
    );
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  const counts = useMemo(
    () => ({
      MANUFACTURER:
        results?.filter((result) => result.role === "MANUFACTURER").length ?? 0,
      DISTRIBUTOR:
        results?.filter((result) => result.role === "DISTRIBUTOR").length ?? 0,
      TRADER: results?.filter((result) => result.role === "TRADER").length ?? 0,
    }),
    [results],
  );

  const advancedPrompt =
    submittedFilters && submittedQuery
      ? buildAdvancedPrompt(submittedQuery, submittedFilters)
      : "";

  if (!session) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-brand-blue-50">
        <p className="text-sm text-gray-500">Verificando acesso...</p>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-brand-blue-50 text-gray-900">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2.5">
            <Image
              src="/onisource-symbol.svg"
              alt="Símbolo OniSource"
              width={32}
              height={32}
              priority
            />
            <span className="text-lg font-semibold text-brand-blue-800">
              OniSource
            </span>
          </div>
          <div className="flex items-center gap-3 sm:gap-5">
            <span className="hidden text-sm text-gray-500 sm:inline">
              {session.email}
            </span>
            <button
              type="button"
              onClick={handleSignOut}
              className="rounded-lg border border-brand-blue-300 px-3 py-2 text-sm font-semibold text-brand-blue-800 transition hover:border-brand-blue-700 hover:bg-brand-blue-50 focus:outline-none focus:ring-4 focus:ring-brand-blue-300/40"
            >
              Sair
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
        <section className="mx-auto max-w-4xl">
          <h1 className="text-2xl font-semibold text-brand-blue-800">
            O que você está procurando?
          </h1>

          <form onSubmit={handleSearch} className="mt-6">
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-lg text-gray-400"
                >
                  🔍
                </span>
                <label htmlFor="search-query" className="sr-only">
                  Produto, matéria-prima ou código
                </label>
                <input
                  id="search-query"
                  type="search"
                  required
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Nome do produto, matéria-prima ou código (ex: Dióxido de Titânio, Ácido Fosfórico, MP 110...)"
                  className="h-14 w-full rounded-lg border border-gray-300 bg-white pl-12 pr-4 text-base shadow-sm outline-none transition placeholder:text-gray-400 focus:border-brand-blue-700 focus:ring-4 focus:ring-brand-blue-300/30"
                />
              </div>
              <button
                type="submit"
                disabled={isLoading || !query.trim()}
                className="h-14 rounded-lg bg-brand-blue-800 px-7 font-semibold text-white shadow-sm transition hover:bg-brand-blue-700 focus:outline-none focus:ring-4 focus:ring-brand-blue-300 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isLoading ? "Pesquisando..." : "Pesquisar"}
              </button>
            </div>

            <button
              type="button"
              onClick={() => setIsFiltersOpen((current) => !current)}
              aria-expanded={isFiltersOpen}
              aria-controls="advanced-filters"
              className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-brand-blue-700 hover:text-brand-blue-900"
            >
              <span aria-hidden="true">{isFiltersOpen ? "▾" : "▸"}</span>
              Filtros avançados
            </button>

            {isFiltersOpen ? (
              <div
                id="advanced-filters"
                className="mt-4 space-y-5 rounded-xl border border-brand-blue-300/70 bg-white p-5 shadow-sm"
              >
                <div className="flex items-center justify-between gap-4 border-b border-gray-100 pb-5">
                  <div>
                    <p className="text-sm font-medium text-gray-800">
                      Busca somente no Brasil
                    </p>
                    <p className="mt-1 text-xs text-gray-500">
                      Desabilita os demais filtros de país.
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={brazilOnly}
                    onClick={handleBrazilToggle}
                    className={`relative h-7 w-12 shrink-0 rounded-full transition-colors focus:outline-none focus:ring-4 focus:ring-brand-blue-300/50 ${
                      brazilOnly ? "bg-brand-blue-800" : "bg-gray-300"
                    }`}
                  >
                    <span
                      className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                        brazilOnly ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                    <span className="sr-only">
                      {brazilOnly ? "Desativar" : "Ativar"} busca somente no Brasil
                    </span>
                  </button>
                </div>

                <CountryTags
                  id="only-countries"
                  label="Pesquisar somente nesses países"
                  placeholder="Digite um país e pressione Enter"
                  values={onlyCountries}
                  disabled={brazilOnly || excludeCountries.length > 0}
                  onChange={handleOnlyCountries}
                />
                <CountryTags
                  id="exclude-countries"
                  label="Excluir esses países"
                  placeholder="Países para excluir da busca"
                  values={excludeCountries}
                  disabled={brazilOnly || onlyCountries.length > 0}
                  onChange={handleExcludeCountries}
                />
              </div>
            ) : null}
          </form>
        </section>

        {isLoading ? (
          <section className="flex flex-col items-center justify-center py-24 text-brand-blue-800">
            <span className="h-9 w-9 animate-spin rounded-full border-4 border-brand-blue-300 border-t-brand-blue-800" />
            <p className="mt-4 font-medium">Analisando fornecedores...</p>
          </section>
        ) : null}

        {errorMessage ? (
          <div
            role="alert"
            className="mx-auto mt-8 max-w-4xl rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {errorMessage}
          </div>
        ) : null}

        {!isLoading && results ? (
          <section className="mt-12 space-y-10">
            <div className="border-b border-brand-blue-300 pb-4">
              <p className="font-semibold text-brand-blue-900">
                {results.length} resultados encontrados ({counts.MANUFACTURER}{" "}
                fabricantes, {counts.DISTRIBUTOR} distribuidores, {counts.TRADER}{" "}
                traders)
              </p>
            </div>

            {results.length === 0 ? (
              <div className="rounded-xl border border-gray-200 bg-white px-6 py-12 text-center text-gray-500">
                Nenhum fornecedor encontrado. Tente ajustar os filtros ou
                reformular a busca.
              </div>
            ) : (
              ROLE_SECTIONS.map((section) => {
                const sectionResults = results.filter(
                  (result) => result.role === section.role,
                );
                if (sectionResults.length === 0) {
                  return null;
                }

                return (
                  <div key={section.role}>
                    <div className="mb-4 flex items-center gap-3">
                      <span aria-hidden="true" className="text-xl">
                        {section.icon}
                      </span>
                      <h2 className="text-xl font-semibold text-brand-blue-900">
                        {section.title}
                      </h2>
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs font-bold ${section.badgeClass}`}
                      >
                        {sectionResults.length}
                      </span>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      {sectionResults.map((result, index) => {
                        const link = websiteUrl(result.website);
                        const confidence = CONFIDENCE_STYLES[result.confidence];
                        const flag = countryFlag(result.country);

                        return (
                          <article
                            key={`${result.company_name}-${index}`}
                            className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                {link ? (
                                  <a
                                    href={link}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="font-semibold text-brand-blue-800 hover:text-brand-blue-700 hover:underline"
                                  >
                                    {result.company_name}
                                  </a>
                                ) : (
                                  <h3 className="font-semibold text-brand-blue-800">
                                    {result.company_name}
                                  </h3>
                                )}
                                <p className="mt-1 text-sm text-gray-500">
                                  {flag ? `${flag} ` : ""}
                                  {result.country}
                                </p>
                              </div>
                              <span
                                className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${confidence.className}`}
                              >
                                {confidence.label}
                              </span>
                            </div>
                            <p className="mt-4 text-sm leading-6 text-gray-600">
                              {result.notes}
                            </p>
                          </article>
                        );
                      })}
                    </div>
                  </div>
                );
              })
            )}

            {advancedPrompt ? (
              <div className="rounded-xl border border-brand-blue-300 bg-brand-blue-50 p-5 sm:p-6">
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                  <h2 className="flex items-center gap-2 font-semibold text-brand-blue-900">
                    <span aria-hidden="true">📋</span>
                    Prompt de pesquisa avançada
                  </h2>
                  <button
                    type="button"
                    onClick={handleCopyPrompt}
                    className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-brand-blue-800 shadow-sm ring-1 ring-brand-blue-300 transition hover:bg-brand-blue-800 hover:text-white focus:outline-none focus:ring-4 focus:ring-brand-blue-300/50"
                  >
                    {copied ? "Copiado ✓" : "Copiar prompt"}
                  </button>
                </div>
                <textarea
                  readOnly
                  value={advancedPrompt}
                  aria-label="Prompt de pesquisa avançada"
                  className="mt-4 h-72 w-full resize-none rounded-lg border border-brand-blue-300 bg-white p-4 text-sm leading-6 text-gray-700 outline-none"
                />
              </div>
            ) : null}
          </section>
        ) : null}
      </main>
    </div>
  );
}
