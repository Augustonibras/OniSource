"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Check,
  ClipboardCopy,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Factory,
  Globe,
  LogOut,
  Mail,
  MessageSquare,
  RefreshCw,
  Search,
  SearchX,
  Settings,
  SlidersHorizontal,
  TrendingUp,
  Warehouse,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
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
  searchResultId?: string;
  cached?: boolean;
  createdAt?: string;
  error?: string;
}

interface SavedSearchResult {
  id: string;
  query: string;
  resolved_query: string | null;
  mp_code: number | null;
  filters: SearchFilters;
  results: SupplierResult[];
  created_at: string;
}

type AnnotationStatus =
  | "new"
  | "contacted"
  | "waiting"
  | "quoted"
  | "sample_requested"
  | "rejected";

interface SupplierAnnotation {
  id: string;
  search_result_id: string;
  supplier_name: string;
  supplier_url: string | null;
  product_query: string;
  status: AnnotationStatus;
  note: string;
  user_email: string;
  created_at: string;
  updated_at: string;
}

interface AnnotationDraft {
  status: AnnotationStatus;
  note: string;
}

interface RfqDraft {
  supplierName: string;
  content: string;
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

const ANNOTATION_STATUS_OPTIONS: Array<{
  value: AnnotationStatus;
  label: string;
}> = [
  { value: "new", label: "Novo" },
  { value: "contacted", label: "Contatado" },
  { value: "waiting", label: "Aguardando resposta" },
  { value: "quoted", label: "Cotação recebida" },
  { value: "sample_requested", label: "Amostra solicitada" },
  { value: "rejected", label: "Descartado" },
];

const ANNOTATION_STATUS_STYLES: Partial<
  Record<AnnotationStatus, { label: string; className: string }>
> = {
  contacted: {
    label: "Contatado",
    className: "border border-amber-200 bg-amber-50 text-amber-700",
  },
  waiting: {
    label: "Aguardando resposta",
    className: "border border-amber-200 bg-amber-50 text-amber-700",
  },
  quoted: {
    label: "Cotação recebida",
    className: "border border-blue-200 bg-blue-50 text-blue-700",
  },
  sample_requested: {
    label: "Amostra solicitada",
    className: "border border-blue-200 bg-blue-50 text-blue-700",
  },
  rejected: {
    label: "Descartado",
    className: "border border-red-200 bg-red-50 text-red-700",
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

function mergeCompanyNames(current: string[], additions: string[]) {
  const merged = [...current];
  const seen = new Set(current.map((company) => company.trim().toLowerCase()));

  for (const company of additions) {
    const normalized = company.trim().toLowerCase();
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized);
      merged.push(company.trim());
    }
  }

  return merged;
}

function supplierKey(name: string) {
  return name.trim().toLowerCase();
}

function formatSavedDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

function buildRfqTemplate(companyName: string, productQuery: string) {
  return `Subject: RFQ — ${productQuery} — Onibras Produtos Químicos

Dear ${companyName},

Onibras Produtos Químicos (Ribeirão Preto, Brazil) is sourcing ${productQuery} for industrial application. We kindly request a quotation with the following information:

1. Product specification (TDS and CoA)
2. Price per MT — FOB and CFR Santos (Brazil)
3. Minimum Order Quantity (MOQ)
4. Lead time from order confirmation
5. Packaging options
6. Country of origin / manufacturing plant location
7. Sample availability (quantity and shipping cost)

We look forward to your reply.

Best regards,
Onibras Produtos Químicos
International Sourcing`;
}

function parseRfqContent(content: string) {
  const [firstLine = "", ...remainingLines] = content.split(/\r?\n/);
  return {
    subject: firstLine.replace(/^Subject:\s*/i, "").trim(),
    body: remainingLines.join("\n").replace(/^\s*\n/, ""),
  };
}

function normalizeSavedFilters(value: unknown): SearchFilters {
  if (!value || typeof value !== "object") {
    return { brazilOnly: false, onlyCountries: [], excludeCountries: [] };
  }

  const filters = value as Record<string, unknown>;
  return {
    brazilOnly: filters.brazilOnly === true,
    onlyCountries: Array.isArray(filters.onlyCountries)
      ? filters.onlyCountries.filter(
          (country): country is string => typeof country === "string",
        )
      : [],
    excludeCountries: Array.isArray(filters.excludeCountries)
      ? filters.excludeCountries.filter(
          (country): country is string => typeof country === "string",
        )
      : [],
  };
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
  const loadedResultIdRef = useRef<string | null>(null);
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
  const [excludedCompanies, setExcludedCompanies] = useState<string[]>([]);
  const [searchResultId, setSearchResultId] = useState<string | null>(null);
  const [isCachedResult, setIsCachedResult] = useState(false);
  const [savedResultCreatedAt, setSavedResultCreatedAt] = useState("");
  const [annotations, setAnnotations] = useState<
    Record<string, SupplierAnnotation>
  >({});
  const [annotationDrafts, setAnnotationDrafts] = useState<
    Record<string, AnnotationDraft>
  >({});
  const [expandedAnnotation, setExpandedAnnotation] = useState<string | null>(
    null,
  );
  const [savingAnnotation, setSavingAnnotation] = useState<string | null>(null);
  const [rfqDraft, setRfqDraft] = useState<RfqDraft | null>(null);
  const [rfqCopied, setRfqCopied] = useState(false);
  const [copied, setCopied] = useState(false);
  const [promptFallbackVisible, setPromptFallbackVisible] = useState(false);
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [reportMessage, setReportMessage] = useState("");
  const [reportError, setReportError] = useState("");
  const [isReportSubmitting, setIsReportSubmitting] = useState(false);
  const [reportSuccess, setReportSuccess] = useState(false);

  async function loadAnnotations(resultId: string) {
    try {
      const response = await fetch(
        `/api/annotations?search_result_id=${encodeURIComponent(resultId)}`,
      );
      const data = (await response.json()) as {
        annotations?: SupplierAnnotation[];
      };
      if (!response.ok) {
        setAnnotations({});
        return;
      }

      const nextAnnotations: Record<string, SupplierAnnotation> = {};
      for (const annotation of data.annotations ?? []) {
        nextAnnotations[supplierKey(annotation.supplier_name)] = annotation;
      }
      setAnnotations(nextAnnotations);
    } catch {
      setAnnotations({});
    }
  }

  useEffect(() => {
    if (!session) {
      router.replace("/");
    }
  }, [router, session]);

  useEffect(() => {
    if (!session) {
      return;
    }

    const resultId = new URLSearchParams(window.location.search).get("resultId");
    if (!resultId || loadedResultIdRef.current === resultId) {
      return;
    }
    loadedResultIdRef.current = resultId;

    async function loadSavedResult() {
      setIsLoading(true);
      setErrorMessage("");
      try {
        const response = await fetch(
          `/api/search/results/${encodeURIComponent(resultId!)}`,
        );
        const data = (await response.json()) as {
          result?: SavedSearchResult;
          error?: string;
        };
        if (!response.ok || !data.result || !Array.isArray(data.result.results)) {
          setErrorMessage(
            data.error ?? "Não foi possível carregar o resultado salvo.",
          );
          return;
        }

        const savedResult = data.result;
        const savedFilters = normalizeSavedFilters(savedResult.filters);
        setQuery(savedResult.query);
        setBrazilOnly(savedFilters.brazilOnly);
        setOnlyCountries(savedFilters.onlyCountries);
        setExcludeCountries(savedFilters.excludeCountries);
        setSubmittedQuery(savedResult.query);
        setResolvedQuery(savedResult.resolved_query ?? savedResult.query);
        setSubmittedMpCode(savedResult.mp_code);
        setSubmittedFilters(savedFilters);
        setResults(savedResult.results);
        setSearchResultId(savedResult.id);
        setIsCachedResult(true);
        setSavedResultCreatedAt(savedResult.created_at);
        setExcludedCompanies([]);
        setExpandedAnnotation(null);
        setAnnotationDrafts({});
        await loadAnnotations(savedResult.id);
      } catch {
        setErrorMessage("Não foi possível carregar o resultado salvo.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadSavedResult();
  }, [session]);

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

  async function performSearch(
    searchQuery: string,
    filters: SearchFilters,
    exclusions: string[],
    forceRefresh = false,
  ) {
    if (!session?.email) {
      return;
    }

    setIsLoading(true);
    setErrorMessage("");
    setResults(null);
    setSearchResultId(null);
    setIsCachedResult(false);
    setSavedResultCreatedAt("");
    setAnnotations({});
    setAnnotationDrafts({});
    setExpandedAnnotation(null);

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: searchQuery,
          filters,
          userEmail: session.email,
          exclude: exclusions,
          forceRefresh,
        }),
      });
      const data = (await response.json()) as SearchApiResponse;

      if (!response.ok || !data.results) {
        setErrorMessage(data.error ?? "Não foi possível concluir a pesquisa.");
        return;
      }

      setSubmittedQuery(searchQuery);
      setResolvedQuery(data.resolvedQuery ?? searchQuery);
      setSubmittedMpCode(data.mpCode ?? null);
      setSubmittedFilters(filters);
      setResults(data.results);
      const nextSearchResultId = data.searchResultId ?? null;
      setSearchResultId(nextSearchResultId);
      setIsCachedResult(data.cached === true);
      setSavedResultCreatedAt(data.createdAt ?? "");
      if (nextSearchResultId) {
        window.history.replaceState(
          null,
          "",
          `/search?resultId=${encodeURIComponent(nextSearchResultId)}`,
        );
        await loadAnnotations(nextSearchResultId);
      } else {
        window.history.replaceState(null, "", "/search");
      }
    } catch {
      setErrorMessage("Não foi possível conectar ao serviço de pesquisa.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      return;
    }

    const filters: SearchFilters = {
      brazilOnly,
      onlyCountries,
      excludeCountries,
    };

    setExcludedCompanies([]);
    await performSearch(normalizedQuery, filters, []);
  }

  async function handleRetrySearch() {
    if (!results || !submittedFilters || !submittedQuery) {
      return;
    }

    const nextExcludedCompanies = mergeCompanyNames(
      excludedCompanies,
      results.map((result) => result.company_name),
    );
    setExcludedCompanies(nextExcludedCompanies);
    await performSearch(
      submittedQuery,
      submittedFilters,
      nextExcludedCompanies,
    );
  }

  async function handleForceRefresh() {
    if (!submittedFilters || !submittedQuery) {
      return;
    }
    setExcludedCompanies([]);
    await performSearch(submittedQuery, submittedFilters, [], true);
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

  async function handleExternalPrompt(baseUrl: string) {
    if (!advancedPrompt) {
      return;
    }

    const promptUrl = `${baseUrl}?q=${encodeURIComponent(advancedPrompt)}`;
    const openedWindow = window.open(promptUrl, "_blank");
    if (openedWindow) {
      return;
    }

    try {
      await navigator.clipboard.writeText(advancedPrompt);
      window.open(baseUrl, "_blank");
      setPromptFallbackVisible(true);
      window.setTimeout(() => setPromptFallbackVisible(false), 2000);
    } catch {
      setErrorMessage("Não foi possível copiar o prompt.");
    }
  }

  function handleAnnotationToggle(result: SupplierResult) {
    const key = supplierKey(result.company_name);
    setExpandedAnnotation((current) => (current === key ? null : key));
    setAnnotationDrafts((current) => {
      if (current[key]) {
        return current;
      }
      const annotation = annotations[key];
      return {
        ...current,
        [key]: {
          status: annotation?.status ?? "new",
          note: annotation?.note ?? "",
        },
      };
    });
  }

  async function handleSaveAnnotation(result: SupplierResult) {
    if (!searchResultId || !session) {
      setErrorMessage("Este resultado ainda não foi salvo.");
      return;
    }

    const key = supplierKey(result.company_name);
    const draft = annotationDrafts[key] ?? { status: "new", note: "" };
    setSavingAnnotation(key);
    setErrorMessage("");

    try {
      const response = await fetch("/api/annotations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          search_result_id: searchResultId,
          supplier_name: result.company_name,
          supplier_url: result.website,
          product_query: resolvedQuery || submittedQuery,
          status: draft.status,
          note: draft.note,
          user_email: session.email,
        }),
      });
      const data = (await response.json()) as {
        annotation?: SupplierAnnotation;
        error?: string;
      };
      if (!response.ok || !data.annotation) {
        setErrorMessage(data.error ?? "Não foi possível salvar a anotação.");
        return;
      }

      setAnnotations((current) => ({
        ...current,
        [key]: data.annotation!,
      }));
    } catch {
      setErrorMessage("Não foi possível salvar a anotação.");
    } finally {
      setSavingAnnotation(null);
    }
  }

  function handleOpenRfq(result: SupplierResult) {
    const productQuery =
      submittedMpCode !== null ? resolvedQuery : submittedQuery;
    setRfqCopied(false);
    setRfqDraft({
      supplierName: result.company_name,
      content: buildRfqTemplate(result.company_name, productQuery),
    });
  }

  async function handleCopyRfq() {
    if (!rfqDraft) {
      return;
    }
    try {
      await navigator.clipboard.writeText(rfqDraft.content);
      setRfqCopied(true);
      window.setTimeout(() => setRfqCopied(false), 2000);
    } catch {
      setErrorMessage("Não foi possível copiar a RFQ.");
    }
  }

  function handleOpenGmail() {
    if (!rfqDraft) {
      return;
    }
    const { subject, body } = parseRfqContent(rfqDraft.content);
    const gmailUrl = new URL("https://mail.google.com/mail/");
    gmailUrl.searchParams.set("view", "cm");
    gmailUrl.searchParams.set("su", subject);
    gmailUrl.searchParams.set("body", body);
    window.open(gmailUrl.toString(), "_blank");
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
        <nav
          className="mx-auto flex h-10 max-w-7xl items-end gap-6 px-4 sm:px-6 lg:px-8"
          aria-label="Áreas do OniSource"
        >
          <Link
            href="/search"
            className="inline-flex h-10 items-center gap-1.5 border-b-2 border-[#16327F] text-sm font-medium text-[#16327F]"
          >
            <Search className="h-4 w-4" aria-hidden="true" />
            Sourcing
          </Link>
          <Link
            href="/sales"
            className="inline-flex h-10 items-center gap-1.5 border-b-2 border-transparent text-sm text-gray-500 transition hover:text-gray-700"
          >
            <TrendingUp className="h-4 w-4" aria-hidden="true" />
            Vendas
          </Link>
        </nav>
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
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-gray-500">
                  {results.length} fornecedores encontrados
                </p>
                {searchResultId ? (
                  <button
                    type="button"
                    onClick={() =>
                      window.open(
                        `/api/search/export/${encodeURIComponent(searchResultId)}`,
                        "_blank",
                      )
                    }
                    className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-3 py-1.5 text-xs text-gray-500 transition hover:text-gray-700"
                  >
                    <Download className="h-4 w-4" aria-hidden="true" />
                    Exportar planilha
                  </button>
                ) : null}
              </div>
              {isCachedResult && savedResultCreatedAt ? (
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-400">
                  <span className="inline-flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                    Resultados salvos de {formatSavedDate(savedResultCreatedAt)}
                  </span>
                  <button
                    type="button"
                    onClick={handleForceRefresh}
                    className="inline-flex items-center gap-1 text-gray-400 transition hover:text-gray-600"
                  >
                    <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                    Forçar nova busca
                  </button>
                </div>
              ) : null}
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
                        const key = supplierKey(result.company_name);
                        const annotation = annotations[key];
                        const statusStyle = annotation
                          ? ANNOTATION_STATUS_STYLES[annotation.status]
                          : undefined;
                        const draft = annotationDrafts[key] ?? {
                          status: annotation?.status ?? "new",
                          note: annotation?.note ?? "",
                        };
                        const isAnnotationExpanded = expandedAnnotation === key;

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
                              <div className="flex flex-wrap justify-end gap-2">
                                {statusStyle ? (
                                  <span
                                    className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-medium ${statusStyle.className}`}
                                  >
                                    {statusStyle.label}
                                  </span>
                                ) : null}
                                <span
                                  className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-medium ${confidence.className}`}
                                >
                                  {confidence.label}
                                </span>
                              </div>
                            </div>
                            <p className="mt-1 text-sm leading-6 text-gray-500">
                              {result.notes}
                            </p>
                            <div className="mt-3 flex justify-end gap-3">
                              <button
                                type="button"
                                onClick={() => handleOpenRfq(result)}
                                className="inline-flex items-center gap-1 text-xs text-gray-400 transition hover:text-gray-600"
                              >
                                <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                                RFQ
                              </button>
                              <button
                                type="button"
                                onClick={() => handleAnnotationToggle(result)}
                                aria-expanded={isAnnotationExpanded}
                                className="inline-flex items-center gap-1 text-xs text-gray-400 transition hover:text-gray-600"
                              >
                                <MessageSquare
                                  className="h-3.5 w-3.5"
                                  aria-hidden="true"
                                />
                                Anotação
                              </button>
                            </div>
                            {isAnnotationExpanded ? (
                              <div className="mt-3 border-t border-gray-100 pt-3">
                                <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto] sm:items-end">
                                  <label className="text-xs text-gray-500">
                                    Status
                                    <select
                                      value={draft.status}
                                      onChange={(event) =>
                                        setAnnotationDrafts((current) => ({
                                          ...current,
                                          [key]: {
                                            ...draft,
                                            status: event.target
                                              .value as AnnotationStatus,
                                          },
                                        }))
                                      }
                                      className="mt-1 h-8 w-full rounded-md border border-gray-200 bg-white px-2 text-xs text-gray-700 outline-none focus:border-[#16327F]"
                                    >
                                      {ANNOTATION_STATUS_OPTIONS.map((option) => (
                                        <option key={option.value} value={option.value}>
                                          {option.label}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <label className="text-xs text-gray-500">
                                    Observação
                                    <textarea
                                      rows={2}
                                      value={draft.note}
                                      onChange={(event) =>
                                        setAnnotationDrafts((current) => ({
                                          ...current,
                                          [key]: {
                                            ...draft,
                                            note: event.target.value,
                                          },
                                        }))
                                      }
                                      placeholder="Observação..."
                                      className="mt-1 w-full resize-none rounded-md border border-gray-200 px-2 py-1.5 text-xs text-gray-700 outline-none placeholder:text-gray-400 focus:border-[#16327F]"
                                    />
                                  </label>
                                  <button
                                    type="button"
                                    onClick={() => handleSaveAnnotation(result)}
                                    disabled={savingAnnotation === key}
                                    className="h-8 rounded-md bg-[#16327F] px-3 text-xs font-medium text-white transition hover:bg-[#2B4FAE] disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                    {savingAnnotation === key
                                      ? "Salvando..."
                                      : "Salvar"}
                                  </button>
                                </div>
                              </div>
                            ) : null}
                          </article>
                        );
                      })}
                    </div>
                  </div>
                );
              })
            )}

            {results.length > 0 ? (
              <div className="flex flex-col items-center">
                <button
                  type="button"
                  onClick={handleRetrySearch}
                  className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-300"
                >
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Não estou satisfeito, buscar novamente
                </button>
                {excludedCompanies.length > 0 ? (
                  <p className="mt-2 text-xs text-gray-400">
                    {excludedCompanies.length} fornecedores excluídos desta sessão
                  </p>
                ) : null}
              </div>
            ) : null}

            {advancedPrompt ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                  <h2 className="flex items-center gap-2 text-sm font-medium text-gray-700">
                    <Copy className="h-4 w-4" aria-hidden="true" />
                    Prompt de pesquisa avançada
                  </h2>
                  <div className="flex flex-col items-start gap-2 sm:items-end">
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
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => handleExternalPrompt("https://claude.ai/new")}
                        className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-50"
                      >
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 256 256"
                          fill="currentColor"
                          className="w-4 h-4 shrink-0"
                        >
                          <path d="M169.22 79.8l-53.83 133.5h-33.6L135.6 79.8h33.62zM86.78 79.8L33.17 213.3H0l53.6-133.5h33.18zm124.44 0l53.61 133.5h-33.17l-53.83-133.5h33.39z" />
                        </svg>
                        Pesquisar no Claude
                      </button>
                      <button
                        type="button"
                        onClick={() => handleExternalPrompt("https://chatgpt.com/")}
                        className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-50"
                      >
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 24 24"
                          fill="currentColor"
                          className="w-4 h-4 shrink-0"
                        >
                          <path d="M22.28 9.37a5.93 5.93 0 00-.51-4.87 6.01 6.01 0 00-6.47-2.87A5.93 5.93 0 0010.84 0a6.01 6.01 0 00-5.73 4.13 5.93 5.93 0 00-3.97 2.88 6.01 6.01 0 00.74 7.04 5.93 5.93 0 00.51 4.87 6.01 6.01 0 006.47 2.87A5.93 5.93 0 0013.32 24a6.01 6.01 0 005.73-4.13 5.93 5.93 0 003.97-2.88 6.01 6.01 0 00-.74-7.62zM13.32 22.34a4.47 4.47 0 01-2.88-1.05l.14-.08 4.79-2.76a.78.78 0 00.39-.68v-6.74l2.02 1.17a.07.07 0 01.04.06v5.58a4.49 4.49 0 01-4.5 4.5zM3.97 18.21a4.47 4.47 0 01-.54-3.01l.14.09 4.79 2.76a.78.78 0 00.78 0l5.85-3.38v2.34a.07.07 0 01-.03.06l-4.84 2.8a4.49 4.49 0 01-6.15-1.66zM2.68 7.88A4.47 4.47 0 014.9 5.92v5.69a.78.78 0 00.39.68l5.85 3.38-2.02 1.17a.07.07 0 01-.07 0l-4.84-2.8a4.49 4.49 0 01-1.53-6.16zm16.4 3.81l-5.85-3.38 2.02-1.17a.07.07 0 01.07 0l4.84 2.8a4.49 4.49 0 01-.69 8.1v-5.67a.78.78 0 00-.39-.68zm2.01-3.03l-.14-.09-4.79-2.76a.78.78 0 00-.78 0L9.53 9.19V6.85a.07.07 0 01.03-.06l4.84-2.8a4.49 4.49 0 016.69 4.67zM8.43 13.46l-2.02-1.17a.07.07 0 01-.04-.06V6.65a4.49 4.49 0 017.38-3.45l-.14.08-4.79 2.76a.78.78 0 00-.39.68v6.74zm1.1-2.37l2.6-1.5 2.6 1.5v3l-2.6 1.5-2.6-1.5v-3z" />
                        </svg>
                        Pesquisar no ChatGPT
                      </button>
                    </div>
                  </div>
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

      {rfqDraft ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) {
              setRfqDraft(null);
            }
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="rfq-dialog-title"
            className="w-full max-w-3xl rounded-xl bg-white p-6 shadow"
          >
            <div className="flex items-start justify-between gap-4">
              <h2
                id="rfq-dialog-title"
                className="flex items-center gap-2 text-xl font-semibold text-gray-800"
              >
                <Mail className="h-5 w-5 text-gray-500" aria-hidden="true" />
                RFQ — {rfqDraft.supplierName}
              </h2>
              <button
                type="button"
                onClick={() => setRfqDraft(null)}
                aria-label="Fechar RFQ"
                className="rounded-md p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <textarea
              value={rfqDraft.content}
              onChange={(event) =>
                setRfqDraft((current) =>
                  current ? { ...current, content: event.target.value } : null,
                )
              }
              aria-label="Conteúdo da solicitação de cotação"
              className="mt-5 h-96 w-full resize-y rounded-lg border border-gray-200 p-4 font-mono text-sm leading-6 text-gray-700 outline-none focus:border-[#16327F] focus:ring-1 focus:ring-[#16327F]"
            />
            <div className="mt-4 flex flex-wrap justify-end gap-3">
              <button
                type="button"
                onClick={handleCopyRfq}
                className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-600 transition hover:bg-gray-50"
              >
                {rfqCopied ? (
                  <Check className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <ClipboardCopy className="h-4 w-4" aria-hidden="true" />
                )}
                {rfqCopied ? "Copiado" : "Copiar"}
              </button>
              <button
                type="button"
                onClick={handleOpenGmail}
                className="inline-flex items-center gap-2 rounded-md bg-[#16327F] px-3 py-2 text-sm font-medium text-white transition hover:bg-[#2B4FAE]"
              >
                <ExternalLink className="h-4 w-4" aria-hidden="true" />
                Abrir no Gmail
              </button>
            </div>
          </section>
        </div>
      ) : null}

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

      {promptFallbackVisible ? (
        <div
          role="status"
          className="fixed bottom-20 right-4 z-50 rounded-lg bg-gray-800 px-4 py-3 text-sm font-medium text-white shadow sm:right-6"
        >
          Prompt copiado — cole na conversa
        </div>
      ) : null}
    </div>
  );
}
