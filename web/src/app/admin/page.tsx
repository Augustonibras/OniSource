"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  History,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";

const SESSION_KEY = "onisource_session";

type AdminTab = "searches" | "tokens" | "reports";
type ReportStatusFilter = "" | "open" | "resolved";

interface Session {
  email: string;
  role: string;
}

interface SearchRecord {
  id: number;
  created_at: string;
  user_email: string;
  query: string;
  filters: unknown;
  results: unknown;
  tokens_used: number | null;
  searchResultId: string | null;
}

interface SearchesResponse {
  searches?: SearchRecord[];
  totalCount?: number;
  users?: string[];
  page?: number;
  pageSize?: number;
  error?: string;
}

interface TokenUsageRecord {
  user_email: string;
  total_searches: number;
  total_tokens: number;
  last_search: string | null;
}

interface TokenUsageResponse {
  usage?: TokenUsageRecord[];
  totals?: {
    total_searches: number;
    total_tokens: number;
    active_users: number;
  };
  error?: string;
}

interface ReportRecord {
  id: number;
  created_at: string;
  user_email: string;
  message: string;
  status: string | null;
}

interface ReportsResponse {
  reports?: ReportRecord[];
  error?: string;
}

const TABS: Array<{ id: AdminTab; label: string; icon: LucideIcon }> = [
  { id: "searches", label: "Histórico de Buscas", icon: History },
  { id: "tokens", label: "Uso de Tokens", icon: BarChart3 },
  { id: "reports", label: "Problemas Reportados", icon: AlertTriangle },
];

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

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

function formatNumber(value: number | null | undefined) {
  return Number(value ?? 0).toLocaleString("pt-BR");
}

function countResults(results: unknown) {
  return Array.isArray(results) ? results.length : 0;
}

function formatFilters(filters: unknown) {
  if (!filters || typeof filters !== "object") {
    return "Sem filtros";
  }

  const value = filters as Record<string, unknown>;
  if (value.brazilOnly === true) {
    return "Somente Brasil";
  }

  const onlyCountries = Array.isArray(value.onlyCountries)
    ? value.onlyCountries.filter((country): country is string => typeof country === "string")
    : [];
  const excludeCountries = Array.isArray(value.excludeCountries)
    ? value.excludeCountries.filter(
        (country): country is string => typeof country === "string",
      )
    : [];

  if (onlyCountries.length > 0) {
    return `Somente: ${onlyCountries.join(", ")}`;
  }
  if (excludeCountries.length > 0) {
    return `Excluir: ${excludeCountries.join(", ")}`;
  }
  return "Sem filtros";
}

export default function AdminPage() {
  const router = useRouter();
  const sessionValue = useSyncExternalStore(
    subscribeToSession,
    getSessionSnapshot,
    getServerSessionSnapshot,
  );
  const session = useMemo(() => parseSession(sessionValue), [sessionValue]);
  const isAdmin = session?.role === "admin";
  const adminEmail = isAdmin ? (session?.email ?? "") : "";
  const [activeTab, setActiveTab] = useState<AdminTab>("searches");
  const [searches, setSearches] = useState<SearchRecord[]>([]);
  const [searchUsers, setSearchUsers] = useState<string[]>([]);
  const [filterUser, setFilterUser] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [searchPage, setSearchPage] = useState(1);
  const [searchTotalCount, setSearchTotalCount] = useState(0);
  const [searchPageSize, setSearchPageSize] = useState(20);
  const [usage, setUsage] = useState<TokenUsageRecord[]>([]);
  const [totals, setTotals] = useState({
    total_searches: 0,
    total_tokens: 0,
    active_users: 0,
  });
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [reportStatus, setReportStatus] = useState<ReportStatusFilter>("");
  const [resolvingReportId, setResolvingReportId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!session) {
      router.replace("/");
    } else if (session.role !== "admin") {
      router.replace("/search");
    }
  }, [router, session]);

  useEffect(() => {
    if (!adminEmail || activeTab !== "searches") {
      return;
    }

    const controller = new AbortController();
    async function loadSearches() {
      setIsLoading(true);
      setErrorMessage("");
      const params = new URLSearchParams({
        userEmail: adminEmail,
        page: String(searchPage),
      });
      if (filterUser) params.set("filterUser", filterUser);
      if (dateFrom) params.set("dateFrom", dateFrom);
      if (dateTo) params.set("dateTo", dateTo);

      try {
        const response = await fetch(`/api/admin/searches?${params}`, {
          signal: controller.signal,
        });
        const data = (await response.json()) as SearchesResponse;
        if (!response.ok) {
          setErrorMessage(data.error ?? "Não foi possível carregar as buscas.");
          return;
        }
        setSearches(data.searches ?? []);
        setSearchUsers(data.users ?? []);
        setSearchTotalCount(data.totalCount ?? 0);
        setSearchPageSize(data.pageSize ?? 20);
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setErrorMessage("Não foi possível carregar as buscas.");
        }
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    }

    void loadSearches();
    return () => controller.abort();
  }, [activeTab, adminEmail, dateFrom, dateTo, filterUser, searchPage]);

  useEffect(() => {
    if (!adminEmail || activeTab !== "tokens") {
      return;
    }

    const controller = new AbortController();
    async function loadUsage() {
      setIsLoading(true);
      setErrorMessage("");
      try {
        const params = new URLSearchParams({ userEmail: adminEmail });
        const response = await fetch(`/api/admin/token-usage?${params}`, {
          signal: controller.signal,
        });
        const data = (await response.json()) as TokenUsageResponse;
        if (!response.ok) {
          setErrorMessage(data.error ?? "Não foi possível carregar o uso de tokens.");
          return;
        }
        setUsage(data.usage ?? []);
        setTotals(
          data.totals ?? {
            total_searches: 0,
            total_tokens: 0,
            active_users: 0,
          },
        );
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setErrorMessage("Não foi possível carregar o uso de tokens.");
        }
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    }

    void loadUsage();
    return () => controller.abort();
  }, [activeTab, adminEmail]);

  useEffect(() => {
    if (!adminEmail || activeTab !== "reports") {
      return;
    }

    const controller = new AbortController();
    async function loadReports() {
      setIsLoading(true);
      setErrorMessage("");
      const params = new URLSearchParams({ userEmail: adminEmail });
      if (reportStatus) params.set("status", reportStatus);

      try {
        const response = await fetch(`/api/admin/reports?${params}`, {
          signal: controller.signal,
        });
        const data = (await response.json()) as ReportsResponse;
        if (!response.ok) {
          setErrorMessage(data.error ?? "Não foi possível carregar os problemas.");
          return;
        }
        setReports(data.reports ?? []);
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setErrorMessage("Não foi possível carregar os problemas.");
        }
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    }

    void loadReports();
    return () => controller.abort();
  }, [activeTab, adminEmail, reportStatus]);

  function handleSignOut() {
    localStorage.removeItem(SESSION_KEY);
    router.replace("/");
  }

  async function handleResolveReport(reportId: number) {
    if (!session) {
      return;
    }
    setResolvingReportId(reportId);
    setErrorMessage("");

    try {
      const response = await fetch("/api/admin/resolve-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reportId, userEmail: session.email }),
      });
      const data = (await response.json()) as { error?: string };
      if (!response.ok) {
        setErrorMessage(data.error ?? "Não foi possível resolver o problema.");
        return;
      }
      setReports((current) =>
        current.map((report) =>
          report.id === reportId ? { ...report, status: "resolved" } : report,
        ),
      );
    } catch {
      setErrorMessage("Não foi possível resolver o problema.");
    } finally {
      setResolvingReportId(null);
    }
  }

  const totalPages = Math.max(
    1,
    Math.ceil(searchTotalCount / searchPageSize),
  );

  if (!isAdmin || !session) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#F8F9FC]">
        <p className="text-sm text-gray-500">Verificando acesso...</p>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-[#F8F9FC] text-gray-800">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <Link href="/search" className="flex items-center gap-2.5">
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
          </Link>
          <div className="flex items-center gap-3 sm:gap-4">
            <span className="hidden text-sm text-gray-500 sm:inline">
              {session.email}
            </span>
            <span className="rounded-md bg-[#16327F]/10 px-2 py-0.5 text-xs font-medium text-[#16327F]">
              Admin
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

      <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
        <div className="mb-7">
          <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
            Administração
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-gray-800">
            Painel OniSource
          </h1>
        </div>

        <div className="overflow-x-auto border-b border-gray-200">
          <nav className="flex min-w-max gap-1" aria-label="Seções administrativas">
            {TABS.map((tab) => {
              const TabIcon = tab.icon;
              return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTab(tab.id);
                  setErrorMessage("");
                }}
                className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition ${
                  activeTab === tab.id
                    ? "border-[#16327F] text-[#16327F]"
                    : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
                }`}
              >
                <TabIcon className="h-4 w-4" aria-hidden="true" />
                {tab.label}
              </button>
              );
            })}
          </nav>
        </div>

        {errorMessage ? (
          <div
            role="alert"
            className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {errorMessage}
          </div>
        ) : null}

        {activeTab === "searches" ? (
          <section className="mt-6">
            <div className="mb-5 grid gap-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm sm:grid-cols-3">
              <label className="text-sm font-medium text-gray-700">
                Usuário
                <select
                  value={filterUser}
                  onChange={(event) => {
                    setFilterUser(event.target.value);
                    setSearchPage(1);
                  }}
                  className="mt-2 h-11 w-full rounded-lg border border-gray-300 bg-white px-3 font-normal outline-none focus:border-[#16327F] focus:ring-1 focus:ring-[#16327F]"
                >
                  <option value="">Todos os usuários</option>
                  {searchUsers.map((email) => (
                    <option key={email} value={email}>
                      {email}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm font-medium text-gray-700">
                Data inicial
                <input
                  type="date"
                  value={dateFrom}
                  max={dateTo || undefined}
                  onChange={(event) => {
                    setDateFrom(event.target.value);
                    setSearchPage(1);
                  }}
                  className="mt-2 h-11 w-full rounded-lg border border-gray-300 bg-white px-3 font-normal outline-none focus:border-[#16327F] focus:ring-1 focus:ring-[#16327F]"
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Data final
                <input
                  type="date"
                  value={dateTo}
                  min={dateFrom || undefined}
                  onChange={(event) => {
                    setDateTo(event.target.value);
                    setSearchPage(1);
                  }}
                  className="mt-2 h-11 w-full rounded-lg border border-gray-300 bg-white px-3 font-normal outline-none focus:border-[#16327F] focus:ring-1 focus:ring-[#16327F]"
                />
              </label>
            </div>

            <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
                  <thead className="bg-gray-50 text-xs font-medium uppercase tracking-wider text-gray-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">Data/Hora</th>
                      <th className="px-4 py-3 font-medium">Usuário</th>
                      <th className="px-4 py-3 font-medium">Busca</th>
                      <th className="px-4 py-3 font-medium">Filtros aplicados</th>
                      <th className="px-4 py-3 text-right font-medium">Resultados</th>
                      <th className="px-4 py-3 text-right font-medium">Tokens</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {searches.map((search) => (
                      <tr key={search.id} className="hover:bg-gray-50">
                        <td className="whitespace-nowrap px-4 py-3 text-gray-500">
                          {formatDate(search.created_at)}
                        </td>
                        <td className="px-4 py-3 text-gray-600">{search.user_email}</td>
                        <td className="max-w-72 px-4 py-3 font-medium text-gray-900">
                          {search.searchResultId ? (
                            <Link
                              href={`/search?resultId=${encodeURIComponent(search.searchResultId)}`}
                              target="_blank"
                              rel="noreferrer"
                              className="transition hover:text-[#16327F] hover:underline"
                            >
                              {search.query}
                            </Link>
                          ) : (
                            search.query
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-500">
                          {formatFilters(search.filters)}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-600">
                          {countResults(search.results)}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-600">
                          {formatNumber(search.tokens_used)}
                        </td>
                      </tr>
                    ))}
                    {!isLoading && searches.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-10 text-center text-gray-500">
                          Nenhuma busca encontrada para os filtros selecionados.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-600">
                <span>
                  Página {searchPage} de {totalPages} · {searchTotalCount} registros
                </span>
                <div className="flex gap-1">
                  <button
                    type="button"
                    disabled={searchPage <= 1 || isLoading}
                    onClick={() => setSearchPage((page) => Math.max(1, page - 1))}
                    className="rounded-md p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-800 disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label="Página anterior"
                    title="Página anterior"
                  >
                    <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    disabled={searchPage >= totalPages || isLoading}
                    onClick={() => setSearchPage((page) => page + 1)}
                    className="rounded-md p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-800 disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label="Próxima página"
                    title="Próxima página"
                  >
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              </div>
            </div>
          </section>
        ) : null}

        {activeTab === "tokens" ? (
          <section className="mt-6">
            <div className="grid gap-4 sm:grid-cols-3">
              {[
                { label: "Total de buscas", value: totals.total_searches },
                { label: "Total de tokens", value: totals.total_tokens },
                { label: "Usuários ativos", value: totals.active_users },
              ].map((card) => (
                <article
                  key={card.label}
                  className="rounded-lg border border-gray-200 bg-white p-4"
                >
                  <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
                    {card.label}
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-gray-900">
                    {formatNumber(card.value)}
                  </p>
                </article>
              ))}
            </div>

            <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
                  <thead className="bg-gray-50 text-xs font-medium uppercase tracking-wider text-gray-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">Email</th>
                      <th className="px-4 py-3 text-right font-medium">Total de Buscas</th>
                      <th className="px-4 py-3 text-right font-medium">Total de Tokens</th>
                      <th className="px-4 py-3 font-medium">Última Busca</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {usage.map((record) => (
                      <tr key={record.user_email} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">
                          {record.user_email}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-600">
                          {formatNumber(record.total_searches)}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-600">
                          {formatNumber(record.total_tokens)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-gray-500">
                          {formatDate(record.last_search)}
                        </td>
                      </tr>
                    ))}
                    {!isLoading && usage.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-4 py-10 text-center text-gray-500">
                          Nenhum uso de tokens registrado.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {activeTab === "reports" ? (
          <section className="mt-6">
            <div className="mb-5 flex justify-end">
              <label className="w-full max-w-xs text-sm font-medium text-gray-700">
                Status
                <select
                  value={reportStatus}
                  onChange={(event) =>
                    setReportStatus(event.target.value as ReportStatusFilter)
                  }
                  className="mt-2 h-11 w-full rounded-lg border border-gray-300 bg-white px-3 font-normal outline-none focus:border-[#16327F] focus:ring-1 focus:ring-[#16327F]"
                >
                  <option value="">Todos</option>
                  <option value="open">Abertos</option>
                  <option value="resolved">Resolvidos</option>
                </select>
              </label>
            </div>

            <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
                  <thead className="bg-gray-50 text-xs font-medium uppercase tracking-wider text-gray-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">Data/Hora</th>
                      <th className="px-4 py-3 font-medium">Usuário</th>
                      <th className="px-4 py-3 font-medium">Mensagem</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 text-right font-medium">Ação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {reports.map((report) => {
                      const isResolved = report.status === "resolved";
                      return (
                        <tr key={report.id} className="hover:bg-gray-50">
                          <td className="whitespace-nowrap px-4 py-3 text-gray-500">
                            {formatDate(report.created_at)}
                          </td>
                          <td className="px-4 py-3 text-gray-600">
                            {report.user_email}
                          </td>
                          <td className="min-w-72 px-4 py-3 text-gray-800">
                            {report.message}
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`rounded-md border px-2 py-0.5 text-xs font-medium ${
                                isResolved
                                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                  : "border-red-200 bg-red-50 text-red-700"
                              }`}
                            >
                              {isResolved ? "Resolvido" : "Aberto"}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button
                              type="button"
                              disabled={isResolved || resolvingReportId === report.id}
                              onClick={() => handleResolveReport(report.id)}
                              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-50 hover:text-[#16327F] disabled:cursor-not-allowed disabled:opacity-40"
                            >
                              {resolvingReportId === report.id
                                ? "Salvando..."
                                : "Marcar como Resolvido"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                    {!isLoading && reports.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-4 py-10 text-center text-gray-500">
                          Nenhum problema encontrado para o filtro selecionado.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {isLoading ? (
          <div className="flex items-center justify-center gap-3 py-8 text-sm text-gray-500">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-gray-200 border-t-[#16327F]" />
            Carregando dados...
          </div>
        ) : null}
      </main>
    </div>
  );
}
