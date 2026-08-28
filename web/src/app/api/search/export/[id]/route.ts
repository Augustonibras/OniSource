import { generateXmlSpreadsheet } from "@/lib/xml-spreadsheet";
import { createServerSupabaseClient } from "../../../../../lib/supabase-server";

export const runtime = "nodejs";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface SupplierResult {
  company_name?: unknown;
  website?: unknown;
  country?: unknown;
  role?: unknown;
  confidence?: unknown;
  notes?: unknown;
}

interface SupplierAnnotation {
  supplier_name?: unknown;
  status?: unknown;
  note?: unknown;
}

const ROLE_LABELS: Record<string, string> = {
  MANUFACTURER: "Fabricante",
  DISTRIBUTOR: "Distribuidor",
  TRADER: "Trader",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  HIGH: "Alta",
  MEDIUM: "Média",
  LOW: "Baixa",
};

const STATUS_LABELS: Record<string, string> = {
  new: "Novo",
  contacted: "Contatado",
  waiting: "Aguardando resposta",
  quoted: "Cotação recebida",
  sample_requested: "Amostra solicitada",
  rejected: "Descartado",
};

function errorResponse(error: string, status: number) {
  return Response.json({ error, code: status }, { status });
}

function text(value: unknown) {
  return typeof value === "string" ? value : "";
}

function supplierKey(value: unknown) {
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
    return errorResponse("Invalid search result id.", 400);
  }

  try {
    const supabase = createServerSupabaseClient();
    const { data: searchResult, error: searchError } = await supabase
      .from("search_results")
      .select("*")
      .eq("id", id)
      .maybeSingle();

    if (searchError) {
      return errorResponse("Unable to load the saved search result.", 500);
    }
    if (!searchResult) {
      return errorResponse("Search result not found.", 404);
    }

    const { data: annotations, error: annotationsError } = await supabase
      .from("supplier_annotations")
      .select("supplier_name,status,note")
      .eq("search_result_id", id);

    if (annotationsError) {
      return errorResponse("Unable to load supplier annotations.", 500);
    }

    const annotationsBySupplier = new Map<string, SupplierAnnotation>();
    for (const annotation of (annotations ?? []) as SupplierAnnotation[]) {
      annotationsBySupplier.set(supplierKey(annotation.supplier_name), annotation);
    }

    const suppliers = Array.isArray(searchResult.results)
      ? (searchResult.results as SupplierResult[])
      : [];
    const rows = suppliers.map((supplier) => {
      const annotation = annotationsBySupplier.get(
        supplierKey(supplier.company_name),
      );
      const role = text(supplier.role);
      const confidence = text(supplier.confidence);
      const status = text(annotation?.status);

      return {
        empresa: text(supplier.company_name),
        pais: text(supplier.country),
        website: text(supplier.website),
        papel: ROLE_LABELS[role] ?? role,
        confianca: CONFIDENCE_LABELS[confidence] ?? confidence,
        nota: text(supplier.notes),
        status_contato: STATUS_LABELS[status] ?? status,
        anotacao: text(annotation?.note),
      };
    });

    const query = String(searchResult.query ?? "resultado");
    const resolvedQuery = text(searchResult.resolved_query);
    const mpCode = searchResult.mp_code;
    const resolvedSubtitle =
      resolvedQuery && resolvedQuery !== query && mpCode !== null && mpCode !== undefined
        ? ` (MP ${mpCode} → ${resolvedQuery})`
        : "";
    const file = generateXmlSpreadsheet({
      title: "OniSource — Sourcing",
      subtitle: `Produto: ${query}${resolvedSubtitle}`,
      sheetName: "Fornecedores",
      columns: [
        { header: "Empresa", key: "empresa", width: 35 },
        { header: "País", key: "pais", width: 18 },
        { header: "Website", key: "website", width: 40 },
        { header: "Papel", key: "papel", width: 16 },
        { header: "Confiança", key: "confianca", width: 14 },
        { header: "Nota", key: "nota", width: 55 },
        { header: "Status", key: "status_contato", width: 20 },
        { header: "Anotação", key: "anotacao", width: 40 },
      ],
      rows,
    });
    const date = new Date(searchResult.created_at ?? Date.now())
      .toISOString()
      .slice(0, 10);
    const filename = `OniSource_Sourcing_${filenamePart(query)}_${date}.xml`;

    return new Response(file, {
      headers: {
        "Content-Type": "application/vnd.ms-excel",
        "Content-Disposition": `attachment; filename="${filename}"`,
      },
    });
  } catch {
    return errorResponse("Unable to export the saved search result.", 500);
  }
}
