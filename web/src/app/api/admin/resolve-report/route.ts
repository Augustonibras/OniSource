import { apiError, authorizeAdmin } from "../../../../lib/admin";

export const runtime = "nodejs";

interface ResolveReportRequest {
  reportId?: number;
  userEmail?: string;
}

export async function POST(request: Request) {
  let body: ResolveReportRequest;
  try {
    body = (await request.json()) as ResolveReportRequest;
  } catch {
    return apiError("Invalid JSON request body.", 400);
  }

  if (!Number.isInteger(body.reportId) || (body.reportId ?? 0) <= 0) {
    return apiError("A valid reportId is required.", 400);
  }

  const authorization = await authorizeAdmin(body.userEmail);
  if (!authorization.authorized) {
    return authorization.response;
  }

  const { data, error } = await authorization.supabase
    .from("reports")
    .update({ status: "resolved" })
    .eq("id", body.reportId)
    .select("id,status")
    .maybeSingle();

  if (error) {
    return apiError("Unable to resolve the report.", 500);
  }
  if (!data) {
    return apiError("Report not found.", 404);
  }

  return Response.json({ report: data });
}
