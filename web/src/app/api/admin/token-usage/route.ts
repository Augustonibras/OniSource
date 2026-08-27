import { apiError, authorizeAdmin } from "../../../../lib/admin";

export const runtime = "nodejs";

interface UsageAggregateRow {
  user_email?: unknown;
  total_searches?: unknown;
  total_tokens?: unknown;
  last_search?: unknown;
}

interface GlobalAggregateRow {
  total_searches?: unknown;
  total_tokens?: unknown;
}

export async function GET(request: Request) {
  const searchParams = new URL(request.url).searchParams;
  const authorization = await authorizeAdmin(searchParams.get("userEmail"));
  if (!authorization.authorized) {
    return authorization.response;
  }

  const [usageResult, totalsResult] = await Promise.all([
    authorization.supabase
      .from("searches")
      .select(
        "user_email,total_searches:id.count(),total_tokens:tokens_used.sum(),last_search:created_at.max()",
      )
      .order("total_tokens", { ascending: false }),
    authorization.supabase
      .from("searches")
      .select("total_searches:id.count(),total_tokens:tokens_used.sum()")
      .maybeSingle(),
  ]);

  if (usageResult.error || totalsResult.error) {
    return apiError(
      "Unable to aggregate token usage. Confirm that PostgREST aggregates are enabled.",
      500,
    );
  }

  const usage = ((usageResult.data ?? []) as UsageAggregateRow[]).map((row) => ({
    user_email: String(row.user_email ?? ""),
    total_searches: Number(row.total_searches ?? 0),
    total_tokens: Number(row.total_tokens ?? 0),
    last_search: row.last_search ? String(row.last_search) : null,
  }));
  const totals = (totalsResult.data ?? {}) as GlobalAggregateRow;

  return Response.json({
    usage,
    totals: {
      total_searches: Number(totals.total_searches ?? 0),
      total_tokens: Number(totals.total_tokens ?? 0),
      active_users: usage.length,
    },
  });
}
