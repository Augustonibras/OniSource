import { apiError, authorizeAdmin } from "../../../../lib/admin";

export const runtime = "nodejs";

const PAGE_SIZE = 20;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function parsePage(value: string | null) {
  if (!value) {
    return 1;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export async function GET(request: Request) {
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

  const [{ data, error, count }, usersResult] = await Promise.all([
    searchesQuery,
    authorization.supabase
      .from("searches")
      .select("user_email,total_searches:id.count()")
      .order("user_email", { ascending: true }),
  ]);

  if (error) {
    return apiError("Unable to load searches.", 500);
  }
  if (usersResult.error) {
    return apiError("Unable to load search users.", 500);
  }

  const users = (usersResult.data ?? [])
    .map((row) => String(row.user_email ?? ""))
    .filter(Boolean);

  return Response.json({
    searches: data ?? [],
    totalCount: count ?? 0,
    users,
    page,
    pageSize: PAGE_SIZE,
  });
}
