import { createServerSupabaseClient } from "@/lib/supabase-server";

export const runtime = "nodejs";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const STATUSES = [
  "new",
  "contacted",
  "proposal_sent",
  "negotiating",
  "closed",
  "rejected",
] as const;

interface AnnotationRequest {
  sales_search_id?: string;
  prospect_name?: string;
  prospect_url?: string;
  product_name?: string;
  status?: string;
  note?: string;
  user_email?: string;
}

function errorResponse(error: string, status: number) {
  return Response.json({ error, code: status }, { status });
}

export async function GET(request: Request) {
  const salesSearchId = new URL(request.url).searchParams.get("sales_search_id");
  if (!salesSearchId || !UUID_PATTERN.test(salesSearchId)) {
    return errorResponse("A valid sales_search_id is required.", 400);
  }

  try {
    const supabase = createServerSupabaseClient();
    const { data, error } = await supabase
      .from("prospect_annotations")
      .select("*")
      .eq("sales_search_id", salesSearchId)
      .order("created_at", { ascending: true });
    if (error) {
      return errorResponse("Unable to load prospect annotations.", 500);
    }
    return Response.json({ annotations: data ?? [] });
  } catch {
    return errorResponse("Unable to load prospect annotations.", 500);
  }
}

export async function POST(request: Request) {
  let body: AnnotationRequest;
  try {
    body = (await request.json()) as AnnotationRequest;
  } catch {
    return errorResponse("Invalid JSON request body.", 400);
  }

  const salesSearchId = body.sales_search_id?.trim() ?? "";
  const prospectName = body.prospect_name?.trim() ?? "";
  const prospectUrl = body.prospect_url?.trim() ?? "";
  const productName = body.product_name?.trim() ?? "";
  const status = body.status?.trim() ?? "new";
  const note = body.note?.trim() ?? "";
  const userEmail = body.user_email?.trim().toLowerCase() ?? "";

  if (!UUID_PATTERN.test(salesSearchId)) {
    return errorResponse("A valid sales_search_id is required.", 400);
  }
  if (!prospectName || !productName || !userEmail) {
    return errorResponse(
      "prospect_name, product_name and user_email are required.",
      400,
    );
  }
  if (!STATUSES.includes(status as (typeof STATUSES)[number])) {
    return errorResponse("Invalid prospect annotation status.", 400);
  }

  try {
    const supabase = createServerSupabaseClient();
    const values = {
      sales_search_id: salesSearchId,
      prospect_name: prospectName,
      prospect_url: prospectUrl || null,
      product_name: productName,
      status,
      note,
      user_email: userEmail,
      updated_at: new Date().toISOString(),
    };
    const { data, error } = await supabase
      .from("prospect_annotations")
      .insert(values)
      .select("*")
      .single();
    if (error) {
      return errorResponse("Unable to save prospect annotation.", 500);
    }
    return Response.json({ annotation: data });
  } catch {
    return errorResponse("Unable to save prospect annotation.", 500);
  }
}
