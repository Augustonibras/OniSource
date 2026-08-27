import type { SupabaseClient } from "@supabase/supabase-js";

import { createServerSupabaseClient } from "./supabase-server";

type AdminAuthorization =
  | { authorized: true; supabase: SupabaseClient }
  | { authorized: false; response: Response };

export function apiError(error: string, status: number) {
  return Response.json({ error, code: status }, { status });
}

export async function authorizeAdmin(
  rawUserEmail: string | null | undefined,
): Promise<AdminAuthorization> {
  const userEmail = rawUserEmail?.trim().toLowerCase() ?? "";
  if (!userEmail) {
    return {
      authorized: false,
      response: apiError("userEmail is required.", 400),
    };
  }

  let supabase: SupabaseClient;
  try {
    supabase = createServerSupabaseClient();
  } catch {
    return {
      authorized: false,
      response: apiError("Supabase server is not configured.", 500),
    };
  }

  const { data, error } = await supabase
    .from("allowed_emails")
    .select("role")
    .eq("email", userEmail)
    .maybeSingle();

  if (error) {
    return {
      authorized: false,
      response: apiError("Unable to verify administrator access.", 500),
    };
  }

  if (data?.role !== "admin") {
    return {
      authorized: false,
      response: apiError("Administrator access required.", 403),
    };
  }

  return { authorized: true, supabase };
}
