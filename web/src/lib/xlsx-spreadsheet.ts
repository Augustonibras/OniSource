import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const XLSX = require("xlsx") as typeof import("xlsx");

const STYLE_INDEX: Record<string, number> = {
  Default: 0,
  Title: 1,
  Subtitle: 2,
  Header: 3,
  RowEven: 4,
  RowOdd: 5,
  Link: 6,
  LinkEven: 7,
  BadgeAlta: 8,
  BadgeMedia: 9,
  BadgeBaixa: 10,
  DateInfo: 11,
};

function extractBrandColor(xml: string) {
  return (
    xml.match(
      /<Style ss:ID="Title">[\s\S]*?<Font[^>]*ss:Color="#([0-9A-Fa-f]{6})"/,
    )?.[1]?.toUpperCase() ?? "16327F"
  );
}

function buildStylesXml(brandColor: string) {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="9">
    <font><sz val="11"/><color rgb="FF1F2937"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="16"/><color rgb="FF${brandColor}"/><name val="Calibri"/><family val="2"/></font>
    <font><sz val="11"/><color rgb="FF6B7280"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>
    <font><u/><sz val="11"/><color rgb="FF2563EB"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FF059669"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FFD97706"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FF6B7280"/><name val="Calibri"/><family val="2"/></font>
    <font><sz val="9"/><color rgb="FF9CA3AF"/><name val="Calibri"/><family val="2"/></font>
  </fonts>
  <fills count="4">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF${brandColor}"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF8F9FC"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="3">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left/><right/><top/><bottom style="thin"><color rgb="FFE5E7EB"/></bottom><diagonal/></border>
    <border><left/><right/><top/><bottom style="thin"><color rgb="FF${brandColor}"/></bottom><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="12">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyFont="1"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
    <xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
    <xf numFmtId="0" fontId="3" fillId="2" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="6" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="7" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="8" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="right"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
  <dxfs count="0"/>
  <tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleMedium9"/>
</styleSheet>`;
}

function replaceZipEntry(
  cfb: ReturnType<typeof XLSX.CFB.read>,
  path: string,
  content: string,
) {
  const entry = XLSX.CFB.find(cfb, path);
  if (!entry) {
    throw new Error(`Missing XLSX entry: ${path}`);
  }
  entry.content = Buffer.from(content, "utf8");
  entry.size = entry.content.length;
}

export function convertXmlSpreadsheetToXlsx(xml: string): ArrayBuffer {
  const workbook = XLSX.read(xml, { type: "string", cellStyles: true });
  const unstyledFile = XLSX.write(workbook, {
    bookType: "xlsx",
    type: "buffer",
    cellStyles: true,
    compression: true,
  });
  const cfb = XLSX.CFB.read(unstyledFile, { type: "buffer" });
  const sheetEntry = XLSX.CFB.find(cfb, "/xl/worksheets/sheet1.xml");
  if (!sheetEntry?.content) {
    throw new Error("Missing XLSX worksheet entry.");
  }

  const sourceStyles = Array.from(
    xml.matchAll(/<Cell\b[^>]*\bss:StyleID="([^"]+)"[^>]*>/g),
    (match) => match[1],
  );
  let cellIndex = 0;
  const sheetXml = Buffer.from(sheetEntry.content).toString("utf8");
  const styledSheetXml = sheetXml.replace(/<c\b([^>]*)>/g, (_cell, attributes) => {
    const sourceStyle = sourceStyles[cellIndex] ?? "Default";
    cellIndex += 1;
    const styleIndex = STYLE_INDEX[sourceStyle] ?? STYLE_INDEX.Default;
    const cleanAttributes = String(attributes).replace(/\s+s="\d+"/g, "");
    return `<c${cleanAttributes} s="${styleIndex}">`;
  });

  replaceZipEntry(cfb, "/xl/worksheets/sheet1.xml", styledSheetXml);
  replaceZipEntry(cfb, "/xl/styles.xml", buildStylesXml(extractBrandColor(xml)));

  const file = XLSX.CFB.write(cfb, {
    type: "buffer",
    fileType: "zip",
    compression: true,
  });
  return file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength);
}
