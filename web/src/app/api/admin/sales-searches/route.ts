import { apiError, authorizeAdmin } from "@/lib/admin";

export const runtime = "nodejs";

const PAGE_SIZE = 20;

function parsePage(value: string | null) {
  if (!value) {
    return 1;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export async function GET(request: Request) {
  try {
    const searchParams = new URL(request.url).searchParams;
    const authorization = await authorizeAdmin(searchParams.get("userEmail"));
    if (!authorization.authorized) {
      return authorization.response;
    }

    const page = parsePage(searchParams.get("page"));
    if (!page) {
      return apiError("page must be a positive integer.", 400);
    }
    const from = (page - 1) * PAGE_SIZE;
    const to = from + PAGE_SIZE - 1;
    const { data, error, count } = await authorization.supabase
      .from("sales_searches")
      .select("*", { count: "exact" })
      .order("created_at", { ascending: false })
      .range(from, to);
    if (error) {
      return apiError("Unable to load sales searches.", 500);
    }

    return Response.json({
      searches: data ?? [],
      totalCount: count ?? 0,
      page,
      pageSize: PAGE_SIZE,
    });
  } catch {
    return apiError("Unexpected error while loading sales searches.", 500);
  }
}
