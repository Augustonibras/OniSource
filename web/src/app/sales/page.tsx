"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Building2,
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
  MapPin,
  MessageSquare,
  RefreshCw,
  Search,
  SearchX,
  Settings,
  TrendingUp,
  Warehouse,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import {
  BRAZILIAN_REGIONS,
  CONTINENTS,
  ONIBRAS_CATALOG,
  type OnibrasProduct,
} from "@/data/onibras-catalog";

const SESSION_KEY = "onisource_session";

type LocationType = "brazil_region" | "country" | "continent";
type ProspectRole = "Mill/Plant" | "Distributor" | "Industry";
type ProspectConfidence = "Alta" | "Média" | "Baixa";
type ProspectStatus =
  | "new"
  | "contacted"
  | "proposal_sent"
  | "negotiating"
  | "closed"
  | "rejected";

interface Session {
  email: string;
  role: string;
}

interface ProspectResult {
  company: string;
  country: string;
  website: string;
  role: ProspectRole;
  confidence: ProspectConfidence;
  note: string;
}

interface SalesApiResponse {
  results?: ProspectResult[];
  salesSearchId?: string;
  cached?: boolean;
  resultCount?: number;
  createdAt?: string;
  error?: string;
}

interface SavedSalesResult {
  id: string;
  product_name: string;
  product_market: string;
  location_type: LocationType;
  location_value: string;
  results: ProspectResult[];
  created_at: string;
}

interface ProspectAnnotation {
  id: string;
  sales_search_id: string;
  prospect_name: string;
  prospect_url: string | null;
  product_name: string;
  status: ProspectStatus;
  note: string;
  user_email: string;
  created_at: string;
  updated_at: string;
}

interface AnnotationDraft {
  status: ProspectStatus;
  note: string;
}

interface LocationSelection {
  type: LocationType;
  value: string;
  description: string;
}

interface EmailDraft {
  prospectName: string;
  content: string;
}

const ROLE_SECTIONS: Array<{
  role: ProspectRole;
  title: string;
  icon: LucideIcon;
  iconClass: string;
  badgeClass: string;
}> = [
  {
    role: "Mill/Plant",
    title: "Usinas & Plantas",
    icon: Factory,
    iconClass: "text-emerald-600",
    badgeClass: "border border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  {
    role: "Distributor",
    title: "Distribuidores",
    icon: Warehouse,
    iconClass: "text-blue-600",
    badgeClass: "border border-blue-200 bg-blue-50 text-blue-700",
  },
  {
    role: "Industry",
    title: "Indústrias",
    icon: Building2,
    iconClass: "text-amber-600",
    badgeClass: "border border-amber-200 bg-amber-50 text-amber-700",
  },
];

const CONFIDENCE_STYLES: Record<
  ProspectConfidence,
  { className: string }
> = {
  Alta: { className: "border border-emerald-200 bg-emerald-50 text-emerald-700" },
  Média: { className: "border border-amber-200 bg-amber-50 text-amber-700" },
  Baixa: { className: "border border-gray-200 bg-gray-100 text-gray-500" },
};

const STATUS_OPTIONS: Array<{ value: ProspectStatus; label: string }> = [
  { value: "new", label: "Novo" },
  { value: "contacted", label: "Contatado" },
  { value: "proposal_sent", label: "Enviou proposta" },
  { value: "negotiating", label: "Negociando" },
  { value: "closed", label: "Fechado" },
  { value: "rejected", label: "Descartado" },
];

const STATUS_STYLES: Partial<
  Record<ProspectStatus, { label: string; className: string }>
> = {
  contacted: {
    label: "Contatado",
    className: "border border-amber-200 bg-amber-50 text-amber-700",
  },
  proposal_sent: {
    label: "Enviou proposta",
    className: "border border-blue-200 bg-blue-50 text-blue-700",
  },
  negotiating: {
    label: "Negociando",
    className: "border border-blue-200 bg-blue-50 text-blue-700",
  },
  closed: {
    label: "Fechado",
    className: "border border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  rejected: {
    label: "Descartado",
    className: "border border-red-200 bg-red-50 text-red-700",
  },
};

const MARKET_GROUPS = [...new Set(ONIBRAS_CATALOG.map((product) => product.market))];

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
  if (!value) return null;
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
  const value = website.trim();
  if (!value) return null;
  return /^https?:\/\//i.test(value) ? value : `https://${value}`;
}

function prospectKey(name: string) {
  return name.trim().toLowerCase();
}

function mergeCompanyNames(current: string[], additions: string[]) {
  const merged = [...current];
  const seen = new Set(current.map((name) => name.trim().toLowerCase()));
  for (const name of additions) {
    const normalized = name.trim().toLowerCase();
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized);
      merged.push(name.trim());
    }
  }
  return merged;
}

function formatSavedDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

function resolveLocation(
  searchScope: "brazil" | "international" | null,
  region: string,
  internationalMode: "country" | "continent" | null,
  country: string,
  continent: string,
): LocationSelection | null {
  if (searchScope === "brazil" && region) {
    const label =
      BRAZILIAN_REGIONS.find((item) => item.value === region)?.label ?? region;
    return { type: "brazil_region", value: region, description: `Brasil — ${label}` };
  }
  if (searchScope === "international" && internationalMode === "country") {
    const value = country.trim();
    return value ? { type: "country", value, description: `País: ${value}` } : null;
  }
  if (
    searchScope === "international" &&
    internationalMode === "continent" &&
    continent
  ) {
    const label =
      CONTINENTS.find((item) => item.value === continent)?.label ?? continent;
    return { type: "continent", value: continent, description: `Continente: ${label}` };
  }
  return null;
}

function locationFromSaved(result: SavedSalesResult): LocationSelection {
  if (result.location_type === "brazil_region") {
    const label =
      BRAZILIAN_REGIONS.find((item) => item.value === result.location_value)
        ?.label ?? result.location_value;
    return {
      type: result.location_type,
      value: result.location_value,
      description: `Brasil — ${label}`,
    };
  }
  if (result.location_type === "continent") {
    const label =
      CONTINENTS.find((item) => item.value === result.location_value)?.label ??
      result.location_value;
    return {
      type: result.location_type,
      value: result.location_value,
      description: `Continente: ${label}`,
    };
  }
  return {
    type: result.location_type,
    value: result.location_value,
    description: `País: ${result.location_value}`,
  };
}

function marketTargets(market: OnibrasProduct["market"]) {
  const targets: Record<OnibrasProduct["market"], string> = {
    sugar_ethanol: "sugar mills, ethanol plants, distilleries and chemical distributors",
    water_treatment:
      "water treatment plants, municipal water utilities, industrial effluent treatment companies and chemical distributors",
    paints_coatings:
      "paint manufacturers, coatings companies, ink producers and chemical distributors",
    industrial:
      "industrial plants, manufacturing facilities, maintenance companies and chemical distributors",
  };
  return targets[market];
}

function buildAdvancedPrompt(product: OnibrasProduct, location: string) {
  return `Find potential customers for ${product.name} by OniBras in ${location}.

${product.name}: ${product.description}. Application: ${product.application}.

Look for: ${marketTargets(product.market)}.

For each company found, provide: company name, country, website, type (mill/distributor/industry), and a brief description of why they are a potential buyer.`;
}

function buildEmailTemplate(product: OnibrasProduct, company: string) {
  return `Subject: OniBras — ${product.name} for ${product.application}

Dear ${company},

OniBras Produtos Químicos (Ribeirão Preto, Brazil) is a specialty chemical manufacturer serving the ${product.marketLabel} industry with high-performance process solutions.

We would like to introduce ${product.name}: ${product.description}.

Key advantages:
- Engineered for real operating conditions
- Full technical support and documentation (TDS, SDS, COA)
- Competitive cost-benefit
- Available for export with packaging aligned to destination requirements

We would be happy to provide technical specifications, samples or a commercial proposal tailored to your operation.

Could we schedule a brief call to discuss your requirements?

Best regards,
OniBras Produtos Químicos
International Sales
augusto@onibras.com.br
www.onibras.com.br`;
}

function parseEmailContent(content: string) {
  const [firstLine = "", ...remainingLines] = content.split(/\r?\n/);
  return {
    subject: firstLine.replace(/^Subject:\s*/i, "").trim(),
    body: remainingLines.join("\n").replace(/^\s*\n/, ""),
  };
}

export default function SalesPage() {
  const router = useRouter();
  const loadedResultIdRef = useRef<string | null>(null);
  const sessionValue = useSyncExternalStore(
    subscribeToSession,
    getSessionSnapshot,
    getServerSessionSnapshot,
  );
  const session = useMemo(() => parseSession(sessionValue), [sessionValue]);

  const [searchScope, setSearchScope] = useState<
    "brazil" | "international" | null
  >(null);
  const [region, setRegion] = useState("");
  const [internationalMode, setInternationalMode] = useState<
    "country" | "continent" | null
  >(null);
  const [country, setCountry] = useState("");
  const [continent, setContinent] = useState("");
  const [selectedProductName, setSelectedProductName] = useState("");
  const [submittedProduct, setSubmittedProduct] = useState<OnibrasProduct | null>(
    null,
  );
  const [submittedLocation, setSubmittedLocation] =
    useState<LocationSelection | null>(null);
  const [results, setResults] = useState<ProspectResult[] | null>(null);
  const [salesSearchId, setSalesSearchId] = useState<string | null>(null);
  const [isCachedResult, setIsCachedResult] = useState(false);
  const [savedResultCreatedAt, setSavedResultCreatedAt] = useState("");
  const [isDirectResultView, setIsDirectResultView] = useState(false);
  const [excludedCompanies, setExcludedCompanies] = useState<string[]>([]);
  const [annotations, setAnnotations] = useState<
    Record<string, ProspectAnnotation>
  >({});
  const [annotationDrafts, setAnnotationDrafts] = useState<
    Record<string, AnnotationDraft>
  >({});
  const [expandedAnnotation, setExpandedAnnotation] = useState<string | null>(
    null,
  );
  const [savingAnnotation, setSavingAnnotation] = useState<string | null>(null);
  const [emailDraft, setEmailDraft] = useState<EmailDraft | null>(null);
  const [emailCopied, setEmailCopied] = useState(false);
  const [promptCopied, setPromptCopied] = useState(false);
  const [promptFallbackVisible, setPromptFallbackVisible] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const selectedProduct = useMemo(
    () => ONIBRAS_CATALOG.find((product) => product.name === selectedProductName),
    [selectedProductName],
  );
  const location = resolveLocation(
    searchScope,
    region,
    internationalMode,
    country,
    continent,
  );
  const advancedPrompt =
    submittedProduct && submittedLocation
      ? buildAdvancedPrompt(submittedProduct, submittedLocation.description)
      : "";

  async function loadAnnotations(resultId: string) {
    try {
      const response = await fetch(
        `/api/sales/annotations?sales_search_id=${encodeURIComponent(resultId)}`,
      );
      const data = (await response.json()) as {
        annotations?: ProspectAnnotation[];
      };
      if (!response.ok) {
        setAnnotations({});
        return;
      }
      const next: Record<string, ProspectAnnotation> = {};
      for (const annotation of data.annotations ?? []) {
        next[prospectKey(annotation.prospect_name)] = annotation;
      }
      setAnnotations(next);
    } catch {
      setAnnotations({});
    }
  }

  useEffect(() => {
    if (!session) router.replace("/");
  }, [router, session]);

  useEffect(() => {
    if (!session) return;
    const resultId = new URLSearchParams(window.location.search).get(
      "salesResultId",
    );
    if (!resultId || loadedResultIdRef.current === resultId) return;
    loadedResultIdRef.current = resultId;

    async function loadSavedResult() {
      setIsLoading(true);
      setErrorMessage("");
      try {
        const response = await fetch(
          `/api/sales/results/${encodeURIComponent(resultId!)}`,
        );
        const data = (await response.json()) as {
          result?: SavedSalesResult;
          error?: string;
        };
        if (!response.ok || !data.result || !Array.isArray(data.result.results)) {
          setErrorMessage(
            data.error ?? "Não foi possível carregar o resultado salvo.",
          );
          return;
        }
        const product = ONIBRAS_CATALOG.find(
          (item) => item.name === data.result!.product_name,
        );
        if (!product) {
          setErrorMessage("O produto deste resultado não existe no catálogo atual.");
          return;
        }
        const savedLocation = locationFromSaved(data.result);
        setSubmittedProduct(product);
        setSelectedProductName(product.name);
        setSubmittedLocation(savedLocation);
        setResults(data.result.results);
        setSalesSearchId(data.result.id);
        setIsCachedResult(true);
        setSavedResultCreatedAt(data.result.created_at);
        setIsDirectResultView(true);
        setExcludedCompanies([]);
        await loadAnnotations(data.result.id);
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

  function resetLocation() {
    setSearchScope(null);
    setRegion("");
    setInternationalMode(null);
    setCountry("");
    setContinent("");
    setSelectedProductName("");
  }

  function resetInternationalMode() {
    setInternationalMode(null);
    setCountry("");
    setContinent("");
    setSelectedProductName("");
  }

  function returnToLocationSelection() {
    setSelectedProductName("");
    if (searchScope === "brazil") {
      setRegion("");
    } else if (internationalMode === "country") {
      setCountry("");
    } else if (internationalMode === "continent") {
      setContinent("");
    }
  }

  async function performSearch(
    product: OnibrasProduct,
    selectedLocation: LocationSelection,
    exclusions: string[],
    forceRefresh = false,
  ) {
    if (!session) return;
    setIsLoading(true);
    setErrorMessage("");
    setResults(null);
    setSalesSearchId(null);
    setAnnotations({});
    setAnnotationDrafts({});
    setExpandedAnnotation(null);
    setIsCachedResult(false);
    setSavedResultCreatedAt("");
    setIsDirectResultView(false);

    try {
      const response = await fetch("/api/sales", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product: product.name,
          productDescription: product.description,
          productApplication: product.application,
          productMarket: product.marketLabel,
          locationType: selectedLocation.type,
          locationValue: selectedLocation.value,
          userEmail: session.email,
          exclude: exclusions,
          forceRefresh,
        }),
      });
      const data = (await response.json()) as SalesApiResponse;
      if (!response.ok || !data.results) {
        setErrorMessage(data.error ?? "Não foi possível concluir a prospecção.");
        return;
      }
      setSubmittedProduct(product);
      setSubmittedLocation(selectedLocation);
      setResults(data.results);
      setSalesSearchId(data.salesSearchId ?? null);
      setIsCachedResult(data.cached === true);
      setSavedResultCreatedAt(data.createdAt ?? "");
      if (data.salesSearchId) {
        window.history.replaceState(
          null,
          "",
          `/sales?salesResultId=${encodeURIComponent(data.salesSearchId)}`,
        );
        await loadAnnotations(data.salesSearchId);
      } else {
        window.history.replaceState(null, "", "/sales");
      }
    } catch {
      setErrorMessage("Não foi possível conectar ao serviço de prospecção.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSearch() {
    if (!selectedProduct || !location) return;
    setExcludedCompanies([]);
    await performSearch(selectedProduct, location, []);
  }

  async function handleRetrySearch() {
    if (!results || !submittedProduct || !submittedLocation) return;
    const nextExcluded = mergeCompanyNames(
      excludedCompanies,
      results.map((result) => result.company),
    );
    setExcludedCompanies(nextExcluded);
    await performSearch(
      submittedProduct,
      submittedLocation,
      nextExcluded,
      false,
    );
  }

  async function handleForceRefresh() {
    if (!submittedProduct || !submittedLocation) return;
    setExcludedCompanies([]);
    await performSearch(submittedProduct, submittedLocation, [], true);
  }

  function handleAnnotationToggle(result: ProspectResult) {
    const key = prospectKey(result.company);
    setExpandedAnnotation((current) => (current === key ? null : key));
    setAnnotationDrafts((current) => {
      if (current[key]) return current;
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

  async function handleSaveAnnotation(result: ProspectResult) {
    if (!salesSearchId || !session || !submittedProduct) {
      setErrorMessage("Este resultado ainda não foi salvo.");
      return;
    }
    const key = prospectKey(result.company);
    const draft = annotationDrafts[key] ?? { status: "new", note: "" };
    setSavingAnnotation(key);
    setErrorMessage("");
    try {
      const response = await fetch("/api/sales/annotations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sales_search_id: salesSearchId,
          prospect_name: result.company,
          prospect_url: result.website,
          product_name: submittedProduct.name,
          status: draft.status,
          note: draft.note,
          user_email: session.email,
        }),
      });
      const data = (await response.json()) as {
        annotation?: ProspectAnnotation;
        error?: string;
      };
      if (!response.ok || !data.annotation) {
        setErrorMessage(data.error ?? "Não foi possível salvar a anotação.");
        return;
      }
      setAnnotations((current) => ({ ...current, [key]: data.annotation! }));
    } catch {
      setErrorMessage("Não foi possível salvar a anotação.");
    } finally {
      setSavingAnnotation(null);
    }
  }

  function handleOpenEmail(result: ProspectResult) {
    if (!submittedProduct) return;
    setEmailCopied(false);
    setEmailDraft({
      prospectName: result.company,
      content: buildEmailTemplate(submittedProduct, result.company),
    });
  }

  async function handleCopyEmail() {
    if (!emailDraft) return;
    try {
      await navigator.clipboard.writeText(emailDraft.content);
      setEmailCopied(true);
      window.setTimeout(() => setEmailCopied(false), 2000);
    } catch {
      setErrorMessage("Não foi possível copiar o e-mail.");
    }
  }

  function handleOpenGmail() {
    if (!emailDraft) return;
    const { subject, body } = parseEmailContent(emailDraft.content);
    const url = new URL("https://mail.google.com/mail/");
    url.searchParams.set("view", "cm");
    url.searchParams.set("su", subject);
    url.searchParams.set("body", body);
    window.open(url.toString(), "_blank");
  }

  async function handleCopyPrompt() {
    if (!advancedPrompt) return;
    try {
      await navigator.clipboard.writeText(advancedPrompt);
      setPromptCopied(true);
      window.setTimeout(() => setPromptCopied(false), 2000);
    } catch {
      setErrorMessage("Não foi possível copiar o prompt.");
    }
  }

  async function handleExternalPrompt(baseUrl: string) {
    if (!advancedPrompt) return;
    const openedWindow = window.open(
      `${baseUrl}?q=${encodeURIComponent(advancedPrompt)}`,
      "_blank",
    );
    if (openedWindow) return;
    try {
      await navigator.clipboard.writeText(advancedPrompt);
      window.open(baseUrl, "_blank");
      setPromptFallbackVisible(true);
      window.setTimeout(() => setPromptFallbackVisible(false), 2000);
    } catch {
      setErrorMessage("Não foi possível copiar o prompt.");
    }
  }

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
          <Link href="/search" className="flex items-center gap-2.5">
            <Image
              src="/onisource-symbol.svg"
              alt="Símbolo OniSource"
              width={28}
              height={28}
              priority
            />
            <span className="text-lg font-semibold text-[#16327F]">OniSource</span>
          </Link>
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
            className="inline-flex h-10 items-center gap-1.5 border-b-2 border-transparent text-sm text-gray-500 transition hover:text-gray-700"
          >
            <Search className="h-4 w-4" aria-hidden="true" />
            Sourcing
          </Link>
          <Link
            href="/sales"
            className="inline-flex h-10 items-center gap-1.5 border-b-2 border-[#16327F] text-sm font-medium text-[#16327F]"
          >
            <TrendingUp className="h-4 w-4" aria-hidden="true" />
            Vendas
          </Link>
        </nav>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-9 sm:px-6 lg:px-8 lg:py-12">
        {!isDirectResultView ? (
          <section>
            <h1 className="text-xl font-semibold text-gray-800">
              Prospecção de clientes
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              Encontre potenciais compradores para produtos Onibras
            </p>

            <div className="mt-8 rounded-lg border border-gray-200 bg-white p-5 sm:p-6">
              <p className="text-sm font-semibold text-gray-800">Buscar no Brasil?</p>
              <div className="mt-3 flex flex-wrap gap-3">
                {[
                  { value: "brazil" as const, label: "Brasil", icon: MapPin },
                  {
                    value: "international" as const,
                    label: "Internacional",
                    icon: Globe,
                  },
                ].map((option) => {
                  const Icon = option.icon;
                  const selected = searchScope === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => {
                        resetLocation();
                        setSearchScope(option.value);
                      }}
                      className={`inline-flex items-center gap-2 rounded-lg border px-6 py-3 text-sm font-medium transition ${
                        selected
                          ? "border-[#16327F] bg-[#16327F] text-white"
                          : "border-gray-200 text-gray-700 hover:bg-gray-50"
                      }`}
                    >
                      <Icon className="h-4 w-4" aria-hidden="true" />
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {searchScope === "brazil" ? (
              <div className="mt-5 rounded-lg border border-gray-200 bg-white p-5 sm:p-6">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-gray-800">
                    Selecione a região
                  </h2>
                  <button
                    type="button"
                    onClick={resetLocation}
                    className="text-xs text-gray-500 hover:text-[#16327F]"
                  >
                    Voltar
                  </button>
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {BRAZILIAN_REGIONS.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      onClick={() => {
                        setRegion(item.value);
                        setSelectedProductName("");
                      }}
                      className={`rounded-lg border px-4 py-3 text-left text-sm font-medium transition ${
                        region === item.value
                          ? "border-[#16327F] bg-blue-50 text-[#16327F]"
                          : "border-gray-200 text-gray-700 hover:bg-gray-50"
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {searchScope === "international" ? (
              <div className="mt-5 rounded-lg border border-gray-200 bg-white p-5 sm:p-6">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-gray-800">
                    Buscar por país ou continente?
                  </h2>
                  <button
                    type="button"
                    onClick={resetLocation}
                    className="text-xs text-gray-500 hover:text-[#16327F]"
                  >
                    Voltar
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-3">
                  {[
                    { value: "country" as const, label: "País específico" },
                    { value: "continent" as const, label: "Continente" },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => {
                        resetInternationalMode();
                        setInternationalMode(option.value);
                      }}
                      className={`rounded-lg border px-6 py-3 text-sm font-medium transition ${
                        internationalMode === option.value
                          ? "border-[#16327F] bg-[#16327F] text-white"
                          : "border-gray-200 text-gray-700 hover:bg-gray-50"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {internationalMode === "country" ? (
                  <div className="mt-4">
                    <label className="text-sm text-gray-700" htmlFor="sales-country">
                      País
                    </label>
                    <input
                      id="sales-country"
                      value={country}
                      onChange={(event) => {
                        setCountry(event.target.value);
                        setSelectedProductName("");
                      }}
                      placeholder="Digite o país"
                      className="mt-1 h-10 w-full max-w-lg rounded-lg border border-gray-300 bg-white px-3 text-sm outline-none focus:border-[#16327F] focus:ring-1 focus:ring-[#16327F]"
                    />
                  </div>
                ) : null}
                {internationalMode === "continent" ? (
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {CONTINENTS.map((item) => (
                      <button
                        key={item.value}
                        type="button"
                        onClick={() => {
                          setContinent(item.value);
                          setSelectedProductName("");
                        }}
                        className={`rounded-lg border px-4 py-3 text-left text-sm font-medium transition ${
                          continent === item.value
                            ? "border-[#16327F] bg-blue-50 text-[#16327F]"
                            : "border-gray-200 text-gray-700 hover:bg-gray-50"
                        }`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            {location ? (
              <div className="mt-5 rounded-lg border border-gray-200 bg-white p-5 sm:p-6">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-gray-800">
                    Selecione o produto
                  </h2>
                  <button
                    type="button"
                    onClick={returnToLocationSelection}
                    className="text-xs text-gray-500 hover:text-[#16327F]"
                  >
                    Voltar
                  </button>
                </div>
                <div className="mt-5 space-y-6">
                  {MARKET_GROUPS.map((market) => {
                    const products = ONIBRAS_CATALOG.filter(
                      (product) => product.market === market,
                    );
                    return (
                      <div key={market}>
                        <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-700">
                          {products[0].marketLabel}
                        </h3>
                        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                          {products.map((product) => (
                            <button
                              key={product.name}
                              type="button"
                              onClick={() => setSelectedProductName(product.name)}
                              className={`rounded-lg border p-4 text-left transition ${
                                selectedProductName === product.name
                                  ? "border-[#16327F] bg-blue-50"
                                  : "border-gray-200 hover:bg-gray-50"
                              }`}
                            >
                              <span className="block text-sm font-medium text-gray-800">
                                {product.name}
                              </span>
                              <span className="mt-1 block text-xs leading-5 text-gray-500">
                                {product.description}
                              </span>
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
                {selectedProduct ? (
                  <div className="mt-6 flex justify-end">
                    <button
                      type="button"
                      onClick={handleSearch}
                      disabled={isLoading}
                      className="inline-flex h-12 items-center gap-2 rounded-lg bg-[#16327F] px-6 font-medium text-white transition hover:bg-[#2B4FAE] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <TrendingUp className="h-5 w-5" aria-hidden="true" />
                      Buscar clientes potenciais
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}

        {isLoading ? (
          <section className="flex flex-col items-center justify-center py-24">
            <span className="h-9 w-9 animate-spin rounded-full border-4 border-gray-200 border-t-[#16327F]" />
            <p className="mt-4 text-sm text-gray-500">
              Analisando potenciais clientes...
            </p>
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

        {!isLoading && results && submittedProduct && submittedLocation ? (
          <section className="mt-12 space-y-10">
            <div className="border-b border-gray-200 pb-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-gray-700">
                    {submittedProduct.name} · {submittedLocation.description}
                  </p>
                  <p className="mt-1 text-sm text-gray-500">
                    {results.length} potenciais clientes encontrados
                  </p>
                </div>
                {salesSearchId ? (
                  <button
                    type="button"
                    onClick={() =>
                      window.open(
                        `/api/sales/export/${encodeURIComponent(salesSearchId)}`,
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
                  Nenhum potencial cliente encontrado. Tente outra localização.
                </p>
              </div>
            ) : (
              ROLE_SECTIONS.map((section) => {
                const sectionResults = results.filter(
                  (result) => result.role === section.role,
                );
                if (sectionResults.length === 0) return null;
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
                        const key = prospectKey(result.company);
                        const annotation = annotations[key];
                        const draft = annotationDrafts[key] ?? {
                          status: annotation?.status ?? "new",
                          note: annotation?.note ?? "",
                        };
                        const statusStyle = annotation
                          ? STATUS_STYLES[annotation.status]
                          : undefined;
                        const link = websiteUrl(result.website);
                        const expanded = expandedAnnotation === key;
                        return (
                          <article
                            key={`${result.company}-${index}`}
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
                                    {result.company}
                                  </a>
                                ) : (
                                  <h3 className="text-base font-medium text-gray-900">
                                    {result.company}
                                  </h3>
                                )}
                                <p className="mt-1 text-sm text-gray-500">
                                  {result.country}
                                </p>
                              </div>
                              <div className="flex flex-wrap justify-end gap-2">
                                {statusStyle ? (
                                  <span
                                    className={`rounded-md px-2 py-0.5 text-xs font-medium ${statusStyle.className}`}
                                  >
                                    {statusStyle.label}
                                  </span>
                                ) : null}
                                <span
                                  className={`rounded-md px-2 py-0.5 text-xs font-medium ${CONFIDENCE_STYLES[result.confidence].className}`}
                                >
                                  {result.confidence}
                                </span>
                              </div>
                            </div>
                            <p className="mt-2 text-sm leading-6 text-gray-500">
                              {result.note}
                            </p>
                            <div className="mt-3 flex justify-end gap-3">
                              <button
                                type="button"
                                onClick={() => handleOpenEmail(result)}
                                className="inline-flex items-center gap-1 text-xs text-gray-400 transition hover:text-gray-600"
                              >
                                <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                                E-mail
                              </button>
                              <button
                                type="button"
                                onClick={() => handleAnnotationToggle(result)}
                                aria-expanded={expanded}
                                className="inline-flex items-center gap-1 text-xs text-gray-400 transition hover:text-gray-600"
                              >
                                <MessageSquare
                                  className="h-3.5 w-3.5"
                                  aria-hidden="true"
                                />
                                Anotação
                              </button>
                            </div>
                            {expanded ? (
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
                                              .value as ProspectStatus,
                                          },
                                        }))
                                      }
                                      className="mt-1 h-8 w-full rounded-md border border-gray-200 bg-white px-2 text-xs text-gray-700 outline-none focus:border-[#16327F]"
                                    >
                                      {STATUS_OPTIONS.map((option) => (
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
                                          [key]: { ...draft, note: event.target.value },
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
                                    className="h-8 rounded-md bg-[#16327F] px-3 text-xs font-medium text-white transition hover:bg-[#2B4FAE] disabled:opacity-60"
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
                  className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-50"
                >
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Não estou satisfeito, buscar novamente
                </button>
                {excludedCompanies.length > 0 ? (
                  <p className="mt-2 text-xs text-gray-400">
                    {excludedCompanies.length} empresas excluídas desta sessão
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
                      className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-600 transition hover:bg-gray-50"
                    >
                      {promptCopied ? (
                        <Check className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <ClipboardCopy className="h-4 w-4" aria-hidden="true" />
                      )}
                      {promptCopied ? "Copiado" : "Copiar"}
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
                          className="h-4 w-4 shrink-0"
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
                          className="h-4 w-4 shrink-0"
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
                  aria-label="Prompt de prospecção avançada"
                  className="mt-4 h-56 w-full resize-none rounded-md border border-gray-200 bg-white p-4 font-mono text-sm leading-6 text-gray-600 outline-none"
                />
              </div>
            ) : null}
          </section>
        ) : null}
      </main>

      {emailDraft ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setEmailDraft(null);
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="sales-email-dialog-title"
            className="w-full max-w-3xl rounded-xl bg-white p-6 shadow"
          >
            <div className="flex items-start justify-between gap-4">
              <h2
                id="sales-email-dialog-title"
                className="flex items-center gap-2 text-xl font-semibold text-gray-800"
              >
                <Mail className="h-5 w-5 text-gray-500" aria-hidden="true" />
                E-mail — {emailDraft.prospectName}
              </h2>
              <button
                type="button"
                onClick={() => setEmailDraft(null)}
                aria-label="Fechar e-mail"
                className="rounded-md p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <textarea
              value={emailDraft.content}
              onChange={(event) =>
                setEmailDraft((current) =>
                  current ? { ...current, content: event.target.value } : null,
                )
              }
              aria-label="Conteúdo do e-mail comercial"
              className="mt-5 h-96 w-full resize-y rounded-lg border border-gray-200 p-4 font-mono text-sm leading-6 text-gray-700 outline-none focus:border-[#16327F] focus:ring-1 focus:ring-[#16327F]"
            />
            <div className="mt-4 flex flex-wrap justify-end gap-3">
              <button
                type="button"
                onClick={handleCopyEmail}
                className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-600 transition hover:bg-gray-50"
              >
                {emailCopied ? (
                  <Check className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <ClipboardCopy className="h-4 w-4" aria-hidden="true" />
                )}
                {emailCopied ? "Copiado" : "Copiar"}
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

      {promptFallbackVisible ? (
        <div
          role="status"
          className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-700 shadow"
        >
          Prompt copiado — cole na conversa
        </div>
      ) : null}
    </div>
  );
}
