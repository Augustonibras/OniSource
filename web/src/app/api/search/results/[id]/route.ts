import { createServerSupabaseClient } from "../../../../../lib/supabase-server";

export const runtime = "nodejs";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function errorResponse(error: string, status: number) {
  return Response.json({ error, code: status }, { status });
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!UUID_PATTERN.test(id)) {
    return errorResponse("Invalid search result id.", 400);
  }

  try {
    const supabase = createServerSupabaseClient();
    const { data, error } = await supabase
      .from("search_results")
      .select("*")
      .eq("id", id)
      .maybeSingle();

    if (error) {
      return errorResponse("Unable to load the saved search result.", 500);
    }
    if (!data) {
      return errorResponse("Search result not found.", 404);
    }

    return Response.json({ result: data });
  } catch {
    return errorResponse("Unable to load the saved search result.", 500);
  }
}
