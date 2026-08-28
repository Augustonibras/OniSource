import * as XLSX from "xlsx";

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
        Empresa: text(supplier.company_name),
        País: text(supplier.country),
        Website: text(supplier.website),
        Papel: ROLE_LABELS[role] ?? role,
        Confiança: CONFIDENCE_LABELS[confidence] ?? confidence,
        "Nota do Sistema": text(supplier.notes),
        "Status de Contato": STATUS_LABELS[status] ?? status,
        "Anotação do Usuário": text(annotation?.note),
      };
    });

    const worksheet = XLSX.utils.json_to_sheet(rows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Fornecedores");
    const file = XLSX.write(workbook, { bookType: "xlsx", type: "array" });
    const date = new Date(searchResult.created_at ?? Date.now())
      .toISOString()
      .slice(0, 10);
    const filename = `OniSource_${filenamePart(String(searchResult.query ?? "resultado"))}_${date}.xlsx`;

    return new Response(file, {
      headers: {
        "Content-Type":
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": `attachment; filename="${filename}"`,
      },
    });
  } catch {
    return errorResponse("Unable to export the saved search result.", 500);
  }
}
