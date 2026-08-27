import { apiError, authorizeAdmin } from "../../../../lib/admin";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const searchParams = new URL(request.url).searchParams;
  const authorization = await authorizeAdmin(searchParams.get("userEmail"));
  if (!authorization.authorized) {
    return authorization.response;
  }

  const status = searchParams.get("status")?.trim().toLowerCase() ?? "";
  if (status && !["open", "resolved"].includes(status)) {
    return apiError("status must be open or resolved.", 400);
  }

  let reportsQuery = authorization.supabase
    .from("reports")
    .select("*")
    .order("created_at", { ascending: false });

  if (status) {
    reportsQuery = reportsQuery.eq("status", status);
  }

  const { data, error } = await reportsQuery;
  if (error) {
    return apiError("Unable to load reports.", 500);
  }

  return Response.json({ reports: data ?? [] });
}
