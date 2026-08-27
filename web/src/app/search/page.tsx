"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Check,
  ClipboardCopy,
  Copy,
  Factory,
  Globe,
  LogOut,
  Search,
  SearchX,
  Settings,
  SlidersHorizontal,
  Warehouse,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";

import { supabase } from "../../lib/supabase";

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
  resolvedQuery?: string;
  mpCode?: number | null;
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
  icon: LucideIcon;
  iconClass: string;
  badgeClass: string;
}> = [
  {
    role: "MANUFACTURER",
    title: "Fabricantes",
    icon: Factory,
    iconClass: "text-emerald-600",
    badgeClass: "border border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  {
    role: "DISTRIBUTOR",
    title: "Distribuidores",
    icon: Warehouse,
    iconClass: "text-blue-600",
    badgeClass: "border border-blue-200 bg-blue-50 text-blue-700",
  },
  {
    role: "TRADER",
    title: "Traders",
    icon: Globe,
    iconClass: "text-amber-600",
    badgeClass: "border border-amber-200 bg-amber-50 text-amber-700",
  },
];

const CONFIDENCE_STYLES: Record<
  Confidence,
  { label: string; className: string }
> = {
  HIGH: {
    label: "Alta",
    className: "border border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  MEDIUM: {
    label: "Média",
    className: "border border-amber-200 bg-amber-50 text-amber-700",
  },
  LOW: {
    label: "Baixa",
    className: "border border-gray-200 bg-gray-100 text-gray-500",
  },
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
        className={`flex min-h-12 flex-wrap items-center gap-2 rounded-lg border bg-white px-3 py-2 transition focus-within:ring-1 ${
          disabled
            ? "cursor-not-allowed border-gray-200 bg-gray-100 opacity-60"
            : "border-gray-300 focus-within:border-[#16327F] focus-within:ring-[#16327F]"
        }`}
      >
        {values.map((country) => (
          <span
            key={country.toLowerCase()}
            className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2.5 py-1 text-sm text-gray-700"
          >
            {country}
            <button
              type="button"
              onClick={() =>
                onChange(values.filter((value) => value !== country))
              }
              disabled={disabled}
              aria-label={`Remover ${country}`}
              className="ml-0.5 text-gray-400 hover:text-gray-700"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
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
  const [resolvedQuery, setResolvedQuery] = useState("");
  const [submittedMpCode, setSubmittedMpCode] = useState<number | null>(null);
  const [submittedFilters, setSubmittedFilters] = useState<SearchFilters | null>(
    null,
  );
  const [copied, setCopied] = useState(false);
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [reportMessage, setReportMessage] = useState("");
  const [reportError, setReportError] = useState("");
  const [isReportSubmitting, setIsReportSubmitting] = useState(false);
  const [reportSuccess, setReportSuccess] = useState(false);

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
      setResolvedQuery(data.resolvedQuery ?? normalizedQuery);
      setSubmittedMpCode(data.mpCode ?? null);
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

  async function handleReportSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) {
      return;
    }
    const message = reportMessage.trim();
    if (message.length < 10) {
      setReportError("Descreva o problema com pelo menos 10 caracteres.");
      return;
    }

    setIsReportSubmitting(true);
    setReportError("");
    const { error } = await supabase.from("reports").insert({
      user_email: session.email,
      message,
    });
    setIsReportSubmitting(false);

    if (error) {
      setReportError("Não foi possível enviar o problema. Tente novamente.");
      return;
    }

    setReportMessage("");
    setIsReportModalOpen(false);
    setReportSuccess(true);
    window.setTimeout(() => setReportSuccess(false), 3000);
  }

  const advancedPrompt =
    submittedFilters && submittedQuery
      ? buildAdvancedPrompt(submittedQuery, submittedFilters)
      : "";

  if (!session) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#F8F9FC]">
        <p className="text-sm text-gray-500">Verificando acesso...</p>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#F8F9FC] text-gray-800">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2.5">
            <Image
              src="/onisource-symbol.svg"
              alt="Símbolo OniSource"
              width={28}
              height={28}
              priority
            />
            <span className="text-lg font-semibold text-[#16327F]">
              OniSource
            </span>
          </div>
          <div className="flex items-center gap-3 sm:gap-5">
            {session.role === "admin" ? (
              <Link
                href="/admin"
                className="inline-flex items-center gap-1.5 px-1 py-2 text-sm text-gray-500 transition hover:text-[#16327F]"
              >
                <Settings className="h-4 w-4" aria-hidden="true" />
                Admin
              </Link>
            ) : null}
            <span className="hidden text-sm text-gray-500 sm:inline">
              {session.email}
            </span>
            <button
              type="button"
              onClick={handleSignOut}
              className="inline-flex items-center gap-1.5 px-1 py-2 text-sm text-gray-500 transition hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-gray-300"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              Sair
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-9 sm:px-6 lg:px-8 lg:py-12">
        <section className="mx-auto max-w-4xl">
          <h1 className="text-xl font-semibold text-gray-800">
            Buscar fornecedores
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Digite o nome do produto, matéria-prima ou código MP
          </p>

          <form onSubmit={handleSearch} className="mt-6">
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <Search
                  aria-hidden="true"
                  className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400"
                />
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
                  className="h-12 w-full rounded-lg border border-gray-300 bg-white pl-12 pr-4 text-base outline-none transition placeholder:text-gray-400 focus:border-[#16327F] focus:ring-1 focus:ring-[#16327F]"
                />
              </div>
              <button
                type="submit"
                disabled={isLoading || !query.trim()}
                className="h-12 rounded-lg bg-[#16327F] px-6 font-medium text-white transition hover:bg-[#2B4FAE] focus:outline-none focus:ring-2 focus:ring-[#85A3E3] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isLoading ? "Pesquisando..." : "Pesquisar"}
              </button>
            </div>

            <button
              type="button"
              onClick={() => setIsFiltersOpen((current) => !current)}
              aria-expanded={isFiltersOpen}
              aria-controls="advanced-filters"
              className="mt-4 inline-flex items-center gap-2 text-sm text-gray-500 transition hover:text-[#16327F]"
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
              Filtros avançados
            </button>

            {isFiltersOpen ? (
              <div
                id="advanced-filters"
                className="mt-4 space-y-5 rounded-lg border border-gray-200 bg-white p-5 shadow-sm"
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
          <section className="flex flex-col items-center justify-center py-24">
            <span className="h-9 w-9 animate-spin rounded-full border-4 border-gray-200 border-t-[#16327F]" />
            <p className="mt-4 text-sm text-gray-500">Analisando fornecedores...</p>
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
            {submittedMpCode !== null && resolvedQuery !== submittedQuery ? (
              <div className="inline-flex rounded-md border border-blue-200 bg-blue-50 px-3 py-1 text-sm text-blue-700">
                Código MP {submittedMpCode} → {resolvedQuery}
              </div>
            ) : null}
            <div className="border-b border-gray-200 pb-4">
              <p className="text-sm text-gray-500">
                {results.length} fornecedores encontrados
              </p>
            </div>

            {results.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-white px-6 py-12 text-center text-gray-500">
                <SearchX className="mx-auto h-10 w-10 text-gray-300" aria-hidden="true" />
                <p className="mt-3">
                  Nenhum fornecedor encontrado. Tente ajustar os filtros ou
                  reformular a busca.
                </p>
              </div>
            ) : (
              ROLE_SECTIONS.map((section) => {
                const sectionResults = results.filter(
                  (result) => result.role === section.role,
                );
                if (sectionResults.length === 0) {
                  return null;
                }
                const RoleIcon = section.icon;

                return (
                  <div key={section.role}>
                    <div className="mb-4 flex items-center gap-3">
                      <RoleIcon
                        className={`h-[18px] w-[18px] ${section.iconClass}`}
                        aria-hidden="true"
                      />
                      <h2 className="text-lg font-semibold text-gray-800">
                        {section.title}
                      </h2>
                      <span
                        className={`rounded-md px-2 py-0.5 text-xs font-medium ${section.badgeClass}`}
                      >
                        {sectionResults.length}
                      </span>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      {sectionResults.map((result, index) => {
                        const link = websiteUrl(result.website);
                        const confidence = CONFIDENCE_STYLES[result.confidence];

                        return (
                          <article
                            key={`${result.company_name}-${index}`}
                            className="rounded-lg border border-gray-200 bg-white p-4 transition-shadow hover:shadow-sm"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                {link ? (
                                  <a
                                    href={link}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-base font-medium text-gray-900 transition hover:text-[#16327F]"
                                  >
                                    {result.company_name}
                                  </a>
                                ) : (
                                  <h3 className="text-base font-medium text-gray-900">
                                    {result.company_name}
                                  </h3>
                                )}
                                <p className="mt-1 text-sm text-gray-500">
                                  {result.country}
                                </p>
                              </div>
                              <span
                                className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-medium ${confidence.className}`}
                              >
                                {confidence.label}
                              </span>
                            </div>
                            <p className="mt-1 text-sm leading-6 text-gray-500">
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
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                  <h2 className="flex items-center gap-2 text-sm font-medium text-gray-700">
                    <Copy className="h-4 w-4" aria-hidden="true" />
                    Prompt de pesquisa avançada
                  </h2>
                  <button
                    type="button"
                    onClick={handleCopyPrompt}
                    className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-600 transition hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-300"
                  >
                    {copied ? (
                      <>
                        <Check className="h-4 w-4" aria-hidden="true" />
                        Copiado
                      </>
                    ) : (
                      <>
                        <ClipboardCopy className="h-4 w-4" aria-hidden="true" />
                        Copiar
                      </>
                    )}
                  </button>
                </div>
                <textarea
                  readOnly
                  value={advancedPrompt}
                  aria-label="Prompt de pesquisa avançada"
                  className="mt-4 h-72 w-full resize-none rounded-md border border-gray-200 bg-white p-4 font-mono text-sm leading-6 text-gray-600 outline-none"
                />
              </div>
            ) : null}
          </section>
        ) : null}
      </main>

      <footer className="sticky bottom-0 z-20 border-t border-gray-200 bg-white/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-6xl justify-end">
          <button
            type="button"
            onClick={() => {
              setReportError("");
              setIsReportModalOpen(true);
            }}
            className="inline-flex items-center gap-2 px-1 py-2 text-sm text-gray-400 transition hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-gray-300"
          >
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            Reportar problema
          </button>
        </div>
      </footer>

      {isReportModalOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target && !isReportSubmitting) {
              setIsReportModalOpen(false);
            }
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-dialog-title"
            className="w-full max-w-lg rounded-xl bg-white p-6 shadow"
          >
            <h2
              id="report-dialog-title"
              className="flex items-center gap-2 text-xl font-semibold text-gray-800"
            >
              <AlertTriangle className="h-5 w-5 text-gray-500" aria-hidden="true" />
              Reportar problema
            </h2>
            <form onSubmit={handleReportSubmit} className="mt-5">
              <label
                htmlFor="report-message"
                className="mb-2 block text-sm font-medium text-gray-700"
              >
                Descreva o problema encontrado
              </label>
              <textarea
                id="report-message"
                required
                minLength={10}
                value={reportMessage}
                onChange={(event) => setReportMessage(event.target.value)}
                className="h-36 w-full resize-none rounded-lg border border-gray-300 p-3 text-sm text-gray-900 outline-none transition focus:border-[#16327F] focus:ring-1 focus:ring-[#16327F]"
                placeholder="Descreva o que aconteceu e o resultado esperado."
              />
              {reportError ? (
                <p className="mt-2 text-sm text-red-600" role="alert">
                  {reportError}
                </p>
              ) : null}
              <div className="mt-5 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsReportModalOpen(false)}
                  disabled={isReportSubmitting}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={isReportSubmitting || reportMessage.trim().length < 10}
                  className="rounded-lg bg-[#16327F] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#2B4FAE] focus:outline-none focus:ring-2 focus:ring-[#85A3E3] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isReportSubmitting ? "Enviando..." : "Enviar"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {reportSuccess ? (
        <div
          role="status"
          className="fixed bottom-20 right-4 z-50 rounded-lg bg-emerald-700 px-4 py-3 text-sm font-medium text-white shadow sm:right-6"
        >
          Problema reportado. Obrigado!
        </div>
      ) : null}
    </div>
  );
}
