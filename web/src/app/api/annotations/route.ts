import { createServerSupabaseClient } from "../../../lib/supabase-server";

export const runtime = "nodejs";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ANNOTATION_STATUSES = [
  "new",
  "contacted",
  "waiting",
  "quoted",
  "sample_requested",
  "rejected",
] as const;

interface AnnotationRequest {
  search_result_id?: string;
  supplier_name?: string;
  supplier_url?: string;
  product_query?: string;
  status?: string;
  note?: string;
  user_email?: string;
}

function errorResponse(error: string, status: number) {
  return Response.json({ error, code: status }, { status });
}

export async function GET(request: Request) {
  const searchResultId = new URL(request.url).searchParams.get(
    "search_result_id",
  );
  if (!searchResultId || !UUID_PATTERN.test(searchResultId)) {
    return errorResponse("A valid search_result_id is required.", 400);
  }

  try {
    const supabase = createServerSupabaseClient();
    const { data, error } = await supabase
      .from("supplier_annotations")
      .select("*")
      .eq("search_result_id", searchResultId)
      .order("created_at", { ascending: true });

    if (error) {
      return errorResponse("Unable to load supplier annotations.", 500);
    }

    return Response.json({ annotations: data ?? [] });
  } catch {
    return errorResponse("Unable to load supplier annotations.", 500);
  }
}

export async function POST(request: Request) {
  let body: AnnotationRequest;
  try {
    body = (await request.json()) as AnnotationRequest;
  } catch {
    return errorResponse("Invalid JSON request body.", 400);
  }

  const searchResultId = body.search_result_id?.trim() ?? "";
  const supplierName = body.supplier_name?.trim() ?? "";
  const supplierUrl = body.supplier_url?.trim() ?? "";
  const productQuery = body.product_query?.trim() ?? "";
  const status = body.status?.trim() ?? "new";
  const note = body.note?.trim() ?? "";
  const userEmail = body.user_email?.trim().toLowerCase() ?? "";

  if (!UUID_PATTERN.test(searchResultId)) {
    return errorResponse("A valid search_result_id is required.", 400);
  }
  if (!supplierName || !productQuery || !userEmail) {
    return errorResponse(
      "supplier_name, product_query and user_email are required.",
      400,
    );
  }
  if (!ANNOTATION_STATUSES.includes(status as (typeof ANNOTATION_STATUSES)[number])) {
    return errorResponse("Invalid annotation status.", 400);
  }

  try {
    const supabase = createServerSupabaseClient();
    const values = {
      search_result_id: searchResultId,
      supplier_name: supplierName,
      supplier_url: supplierUrl || null,
      product_query: productQuery,
      status,
      note,
      user_email: userEmail,
      updated_at: new Date().toISOString(),
    };

    const { data, error } = await supabase
      .from("supplier_annotations")
      .insert(values)
      .select("*")
      .single();

    if (error) {
      return errorResponse("Unable to save supplier annotation.", 500);
    }

    return Response.json({ annotation: data });
  } catch {
    return errorResponse("Unable to save supplier annotation.", 500);
  }
}
