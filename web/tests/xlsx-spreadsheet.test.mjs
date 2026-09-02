import assert from "node:assert/strict";
import test from "node:test";

import * as XLSX from "xlsx";

import { generateXmlSpreadsheet } from "../src/lib/xml-spreadsheet.ts";
import { convertXmlSpreadsheetToXlsx } from "../src/lib/xlsx-spreadsheet.ts";

test("converts the formatted export to a real XLSX workbook", () => {
  const xml = generateXmlSpreadsheet({
    title: "OniSource — Sourcing",
    subtitle: "Produto: Ácido fosfórico",
    sheetName: "Fornecedores",
    columns: [
      { header: "Empresa", key: "empresa", width: 35 },
      { header: "Website", key: "website", width: 40 },
      { header: "Confiança", key: "confianca", width: 14 },
    ],
    rows: [
      {
        empresa: "Fornecedor A",
        website: "https://example.com",
        confianca: "Alta",
      },
    ],
  });

  const file = convertXmlSpreadsheetToXlsx(xml);
  const bytes = new Uint8Array(file);
  assert.equal(String.fromCharCode(bytes[0], bytes[1]), "PK");

  const workbook = XLSX.read(file, { type: "array", cellStyles: true });
  assert.deepEqual(workbook.SheetNames, ["Fornecedores"]);
  const sheet = workbook.Sheets.Fornecedores;
  assert.equal(sheet.A1.v, "OniSource — Sourcing");
  assert.equal(sheet.A2.v, "Produto: Ácido fosfórico");
  assert.equal(sheet.A5.v, "Empresa");
  assert.equal(sheet.A6.v, "Fornecedor A");
  assert.equal(sheet.B6.l.Target, "https://example.com");
  assert.equal(sheet.A5.s.patternType, "solid");
  assert.equal(sheet.A5.s.fgColor.rgb, "16327F");
  assert.equal(sheet.A6.s.patternType, "solid");
  assert.equal(sheet.A6.s.fgColor.rgb, "F8F9FC");
  assert.equal(sheet["!cols"].length, 3);
});
