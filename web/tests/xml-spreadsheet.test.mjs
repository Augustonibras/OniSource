import assert from "node:assert/strict";
import test from "node:test";

import { generateXmlSpreadsheet } from "../src/lib/xml-spreadsheet.ts";

test("generates formatted XML Spreadsheet with escaped values and links", () => {
  const xml = generateXmlSpreadsheet({
    title: "OniSource & Export",
    subtitle: 'Produto: "Ácido" <75%>',
    sheetName: "Fornecedores",
    columns: [
      { header: "Empresa", key: "empresa", width: 35 },
      { header: "Website", key: "website", width: 40 },
      { header: "Confiança", key: "confianca", width: 14 },
    ],
    rows: [
      {
        empresa: "Fornecedor & Cia",
        website: "https://example.com/?a=1&b=2",
        confianca: "Alta",
      },
    ],
  });

  assert.match(xml, /^<\?xml version="1\.0" encoding="UTF-8"\?>/);
  assert.match(xml, /<Worksheet ss:Name="Fornecedores">/);
  assert.match(xml, /OniSource &amp; Export/);
  assert.match(xml, /Produto: &quot;Ácido&quot; &lt;75%&gt;/);
  assert.match(xml, /ss:HRef="https:\/\/example\.com\/\?a=1&amp;b=2"/);
  assert.match(xml, /ss:StyleID="BadgeAlta"/);
  assert.equal((xml.match(/<Column ss:Width=/g) ?? []).length, 3);
});
