import { apiError, authorizeAdmin } from "../../../../lib/admin";

export const runtime = "nodejs";

const RAW_DATA_PAGE_SIZE = 1000;

interface SearchUsageRow {
  user_email: string | null;
  tokens_used: number | null;
  created_at: string | null;
}

export async function GET(request: Request) {
  const searchParams = new URL(request.url).searchParams;
  const authorization = await authorizeAdmin(searchParams.get("userEmail"));
  if (!authorization.authorized) {
    return authorization.response;
  }

  const rows: SearchUsageRow[] = [];
  for (let from = 0; ; from += RAW_DATA_PAGE_SIZE) {
    const { data, error } = await authorization.supabase
      .from("searches")
      .select("user_email,tokens_used,created_at")
      .order("created_at", { ascending: false })
      .range(from, from + RAW_DATA_PAGE_SIZE - 1);

    if (error) {
      return apiError("Unable to load token usage.", 500);
    }

    rows.push(...((data ?? []) as SearchUsageRow[]));

    if ((data ?? []).length < RAW_DATA_PAGE_SIZE) {
      break;
    }
  }

  const usageByUser = new Map<
    string,
    {
      user_email: string;
      total_searches: number;
      total_tokens: number;
      last_search: string | null;
    }
  >();

  for (const row of rows) {
    const userEmail = String(row.user_email ?? "");
    if (!userEmail) {
      continue;
    }

    const current = usageByUser.get(userEmail) ?? {
      user_email: userEmail,
      total_searches: 0,
      total_tokens: 0,
      last_search: null,
    };
    current.total_searches += 1;
    current.total_tokens += Number(row.tokens_used ?? 0);
    if (
      row.created_at &&
      (!current.last_search || row.created_at > current.last_search)
    ) {
      current.last_search = row.created_at;
    }
    usageByUser.set(userEmail, current);
  }

  const usage = [...usageByUser.values()].sort(
    (left, right) => right.total_tokens - left.total_tokens,
  );
  const totalTokens = rows.reduce(
    (total, row) => total + Number(row.tokens_used ?? 0),
    0,
  );

  return Response.json({
    usage,
    totals: {
      total_searches: rows.length,
      total_tokens: totalTokens,
      active_users: usage.length,
    },
  });
}
