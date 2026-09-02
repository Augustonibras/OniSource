import { filterSalesResultsByLocation } from "@/lib/sales-geography";
import { generateXmlSpreadsheet } from "@/lib/xml-spreadsheet";
import { convertXmlSpreadsheetToXlsx } from "@/lib/xlsx-spreadsheet";
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
  "Mill/Plant": "Usina/Planta",
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
      .eq("sales_search_id", id)
      .order("created_at", { ascending: true });
    if (annotationsError) {
      return errorResponse("Unable to load prospect annotations.", 500);
    }

    const annotationsByProspect = new Map<string, ProspectAnnotation>();
    for (const annotation of (annotations ?? []) as ProspectAnnotation[]) {
      annotationsByProspect.set(prospectKey(annotation.prospect_name), annotation);
    }

    const savedProspects = Array.isArray(salesSearch.results)
      ? (salesSearch.results as ProspectResult[])
      : [];
    const prospects = filterSalesResultsByLocation(
      savedProspects,
      String(salesSearch.location_type ?? ""),
      String(salesSearch.location_value ?? ""),
    );
    const rows = prospects.map((prospect) => {
      const annotation = annotationsByProspect.get(prospectKey(prospect.company));
      const role = text(prospect.role);
      const status = text(annotation?.status);
      return {
        empresa: text(prospect.company),
        pais: text(prospect.country),
        website: text(prospect.website),
        tipo: ROLE_LABELS[role] ?? role,
        confianca: text(prospect.confidence),
        nota: text(prospect.note),
        status_contato: STATUS_LABELS[status] ?? status,
        anotacao: text(annotation?.note),
      };
    });

    const product = String(salesSearch.product_name ?? "produto");
    const location = String(salesSearch.location_value ?? "local");
    const xml = generateXmlSpreadsheet({
      title: "OniSource — Prospecção de Clientes",
      subtitle: `Produto: ${product} | Localização: ${location}`,
      sheetName: "Prospectos",
      columns: [
        { header: "Empresa", key: "empresa", width: 35 },
        { header: "País", key: "pais", width: 18 },
        { header: "Website", key: "website", width: 40 },
        { header: "Tipo", key: "tipo", width: 20 },
        { header: "Confiança", key: "confianca", width: 14 },
        { header: "Nota", key: "nota", width: 55 },
        { header: "Status", key: "status_contato", width: 20 },
        { header: "Anotação", key: "anotacao", width: 40 },
      ],
      rows,
    });
    const file = convertXmlSpreadsheetToXlsx(xml);
    const date = new Date(salesSearch.created_at ?? Date.now())
      .toISOString()
      .slice(0, 10);
    const filename = `OniSource_Vendas_${filenamePart(product)}_${filenamePart(location)}_${date}.xlsx`;

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
