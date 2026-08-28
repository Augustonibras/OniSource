import { apiError, authorizeAdmin } from "../../../../lib/admin";

export const runtime = "nodejs";

const PAGE_SIZE = 20;
const RAW_DATA_PAGE_SIZE = 1000;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

interface SearchHistoryRow {
  created_at?: unknown;
  user_email?: unknown;
  query?: unknown;
  filters?: unknown;
  results?: unknown;
  [key: string]: unknown;
}

interface SavedSearchLookup {
  id: string;
  created_at: string;
  user_email: string;
  query: string;
  filters: unknown;
  results: unknown;
}

function parsePage(value: string | null) {
  if (!value) {
    return 1;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

async function loadSearches(request: Request) {
  const searchParams = new URL(request.url).searchParams;
  const authorization = await authorizeAdmin(searchParams.get("userEmail"));
  if (!authorization.authorized) {
    return authorization.response;
  }

  const filterUser = searchParams.get("filterUser")?.trim().toLowerCase() ?? "";
  const dateFrom = searchParams.get("dateFrom")?.trim() ?? "";
  const dateTo = searchParams.get("dateTo")?.trim() ?? "";
  const page = parsePage(searchParams.get("page"));

  if (!page) {
    return apiError("page must be a positive integer.", 400);
  }
  if (
    (dateFrom && !DATE_PATTERN.test(dateFrom)) ||
    (dateTo && !DATE_PATTERN.test(dateTo)) ||
    (dateFrom && dateTo && dateFrom > dateTo)
  ) {
    return apiError("Invalid date range.", 400);
  }

  const from = (page - 1) * PAGE_SIZE;
  const to = from + PAGE_SIZE - 1;
  let searchesQuery = authorization.supabase
    .from("searches")
    .select("*", { count: "exact" })
    .order("created_at", { ascending: false })
    .range(from, to);

  if (filterUser) {
    searchesQuery = searchesQuery.eq("user_email", filterUser);
  }
  if (dateFrom) {
    searchesQuery = searchesQuery.gte(
      "created_at",
      `${dateFrom}T00:00:00.000Z`,
    );
  }
  if (dateTo) {
    searchesQuery = searchesQuery.lte(
      "created_at",
      `${dateTo}T23:59:59.999Z`,
    );
  }

  const { data, error, count } = await searchesQuery;

  if (error) {
    return apiError("Unable to load searches.", 500);
  }

  const searches = (data ?? []) as SearchHistoryRow[];
  let searchesWithResultIds = searches.map((search) => ({
    ...search,
    searchResultId: null as string | null,
  }));

  if (searches.length > 0) {
    const searchTimes = searches
      .map((search) => new Date(String(search.created_at ?? "")).getTime())
      .filter(Number.isFinite);
    const emails = [
      ...new Set(
        searches.map((search) => String(search.user_email ?? "")).filter(Boolean),
      ),
    ];

    if (searchTimes.length > 0 && emails.length > 0) {
      const earliest = new Date(
        Math.min(...searchTimes) - 7 * 24 * 60 * 60 * 1000,
      ).toISOString();
      const latest = new Date(Math.max(...searchTimes)).toISOString();
      const { data: savedRows, error: savedRowsError } =
        await authorization.supabase
          .from("search_results")
          .select("id,created_at,user_email,query,filters,results")
          .in("user_email", emails)
          .gte("created_at", earliest)
          .lte("created_at", latest)
          .order("created_at", { ascending: false });

      if (savedRowsError) {
        console.error(
          "Unable to associate saved results with search history.",
          savedRowsError,
        );
      } else {
        const savedResults = (savedRows ?? []) as SavedSearchLookup[];
        searchesWithResultIds = searches.map((search) => {
          const searchTime = new Date(
            String(search.created_at ?? ""),
          ).getTime();
          const matchingResult = savedResults.find(
            (saved) =>
              saved.user_email === String(search.user_email ?? "") &&
              saved.query.trim().toLocaleLowerCase("pt-BR") ===
                String(search.query ?? "").trim().toLocaleLowerCase("pt-BR") &&
              JSON.stringify(saved.filters) === JSON.stringify(search.filters) &&
              JSON.stringify(saved.results) === JSON.stringify(search.results) &&
              new Date(saved.created_at).getTime() <= searchTime,
          );

          return {
            ...search,
            searchResultId: matchingResult?.id ?? null,
          };
        });
      }
    }
  }

  const userEmails: string[] = [];
  for (let from = 0; ; from += RAW_DATA_PAGE_SIZE) {
    const { data: userRows, error: usersError } = await authorization.supabase
      .from("searches")
      .select("user_email")
      .order("user_email", { ascending: true })
      .range(from, from + RAW_DATA_PAGE_SIZE - 1);

    if (usersError) {
      return apiError("Unable to load search users.", 500);
    }

    userEmails.push(
      ...(userRows ?? [])
        .map((row) => String(row.user_email ?? ""))
        .filter(Boolean),
    );

    if ((userRows ?? []).length < RAW_DATA_PAGE_SIZE) {
      break;
    }
  }

  const users = [...new Set(userEmails)];

  return Response.json({
    searches: searchesWithResultIds,
    totalCount: count ?? 0,
    users,
    page,
    pageSize: PAGE_SIZE,
  });
}

export async function GET(request: Request) {
  try {
    return await loadSearches(request);
  } catch {
    return apiError("Unexpected error while loading searches.", 500);
  }
}
