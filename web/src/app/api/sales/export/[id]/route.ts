import * as XLSX from "xlsx";

import { createServerSupabaseClient } from "@/lib/supabase-server";

export const runtime = "nodejs";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface ProspectResult {
  company?: unknown;
  country?: unknown;
  website?: unknown;
  role?: unknown;
  confidence?: unknown;
  note?: unknown;
}

interface ProspectAnnotation {
  prospect_name?: unknown;
  status?: unknown;
  note?: unknown;
}

const ROLE_LABELS: Record<string, string> = {
  "Mill/Plant": "Usina",
  Distributor: "Distribuidor",
  Industry: "Indústria",
};
const STATUS_LABELS: Record<string, string> = {
  new: "Novo",
  contacted: "Contatado",
  proposal_sent: "Enviou proposta",
  negotiating: "Negociando",
  closed: "Fechado",
  rejected: "Descartado",
};

function errorResponse(error: string, status: number) {
  return Response.json({ error, code: status }, { status });
}

function text(value: unknown) {
  return typeof value === "string" ? value : "";
}

function prospectKey(value: unknown) {
  return text(value).trim().toLowerCase();
}

function filenamePart(value: string) {
  return (
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-zA-Z0-9_-]+/g, "_")
      .replace(/^_+|_+$/g, "") || "resultado"
  );
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!UUID_PATTERN.test(id)) {
    return errorResponse("Invalid sales result id.", 400);
  }

  try {
    const supabase = createServerSupabaseClient();
    const { data: salesSearch, error: searchError } = await supabase
      .from("sales_searches")
      .select("*")
      .eq("id", id)
      .maybeSingle();
    if (searchError) {
      return errorResponse("Unable to load the saved sales result.", 500);
    }
    if (!salesSearch) {
      return errorResponse("Sales result not found.", 404);
    }

    const { data: annotations, error: annotationsError } = await supabase
      .from("prospect_annotations")
      .select("prospect_name,status,note")
      .eq("sales_search_id", id);
    if (annotationsError) {
      return errorResponse("Unable to load prospect annotations.", 500);
    }

    const annotationsByProspect = new Map<string, ProspectAnnotation>();
    for (const annotation of (annotations ?? []) as ProspectAnnotation[]) {
      annotationsByProspect.set(prospectKey(annotation.prospect_name), annotation);
    }

    const prospects = Array.isArray(salesSearch.results)
      ? (salesSearch.results as ProspectResult[])
      : [];
    const rows = prospects.map((prospect) => {
      const annotation = annotationsByProspect.get(prospectKey(prospect.company));
      const role = text(prospect.role);
      const status = text(annotation?.status);
      return {
        Empresa: text(prospect.company),
        País: text(prospect.country),
        Website: text(prospect.website),
        Tipo: ROLE_LABELS[role] ?? role,
        Confiança: text(prospect.confidence),
        Nota: text(prospect.note),
        "Status de Contato": STATUS_LABELS[status] ?? status,
        Anotação: text(annotation?.note),
      };
    });

    const worksheet = XLSX.utils.json_to_sheet(rows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Potenciais clientes");
    const file = XLSX.write(workbook, { bookType: "xlsx", type: "array" });
    const date = new Date(salesSearch.created_at ?? Date.now())
      .toISOString()
      .slice(0, 10);
    const filename = `OniSource_Vendas_${filenamePart(String(salesSearch.product_name ?? "produto"))}_${filenamePart(String(salesSearch.location_value ?? "local"))}_${date}.xlsx`;

    return new Response(file, {
      headers: {
        "Content-Type":
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": `attachment; filename="${filename}"`,
      },
    });
  } catch {
    return errorResponse("Unable to export the saved sales result.", 500);
  }
}
