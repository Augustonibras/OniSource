// Gera XML Spreadsheet 2003 (.xml) com formatação profissional
// Referência: Microsoft XML Spreadsheet 2003 spec

interface Column {
  header: string;
  key: string;
  width: number; // em caracteres
}

interface SpreadsheetOptions {
  title: string;
  subtitle?: string;
  sheetName: string;
  columns: Column[];
  rows: Record<string, string | number>[];
  brandColor?: string; // hex sem #, ex: "16327F"
}

function escapeXml(str: string | number | null | undefined): string {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

export function generateXmlSpreadsheet(options: SpreadsheetOptions): string {
  const { title, subtitle, sheetName, columns, rows, brandColor = '16327F' } = options;

  const styles = `
    <Styles>
      <Style ss:ID="Default">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#1F2937"/>
      </Style>
      <Style ss:ID="Title">
        <Font ss:FontName="Calibri" ss:Size="16" ss:Bold="1" ss:Color="#${brandColor}"/>
      </Style>
      <Style ss:ID="Subtitle">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#6B7280"/>
      </Style>
      <Style ss:ID="Header">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1" ss:Color="#FFFFFF"/>
        <Interior ss:Color="#${brandColor}" ss:Pattern="Solid"/>
        <Alignment ss:Horizontal="Center" ss:Vertical="Center" ss:WrapText="1"/>
        <Borders>
          <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#${brandColor}"/>
        </Borders>
      </Style>
      <Style ss:ID="RowEven">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#1F2937"/>
        <Interior ss:Color="#F8F9FC" ss:Pattern="Solid"/>
        <Alignment ss:Vertical="Center" ss:WrapText="1"/>
        <Borders>
          <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5E7EB"/>
        </Borders>
      </Style>
      <Style ss:ID="RowOdd">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#1F2937"/>
        <Interior ss:Color="#FFFFFF" ss:Pattern="Solid"/>
        <Alignment ss:Vertical="Center" ss:WrapText="1"/>
        <Borders>
          <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E5E7EB"/>
        </Borders>
      </Style>
      <Style ss:ID="Link">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#2563EB" ss:Underline="Single"/>
        <Alignment ss:Vertical="Center" ss:WrapText="1"/>
      </Style>
      <Style ss:ID="LinkEven">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#2563EB" ss:Underline="Single"/>
        <Interior ss:Color="#F8F9FC" ss:Pattern="Solid"/>
        <Alignment ss:Vertical="Center" ss:WrapText="1"/>
      </Style>
      <Style ss:ID="BadgeAlta">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1" ss:Color="#059669"/>
        <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
      </Style>
      <Style ss:ID="BadgeMedia">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1" ss:Color="#D97706"/>
        <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
      </Style>
      <Style ss:ID="BadgeBaixa">
        <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1" ss:Color="#6B7280"/>
        <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
      </Style>
      <Style ss:ID="DateInfo">
        <Font ss:FontName="Calibri" ss:Size="9" ss:Color="#9CA3AF"/>
        <Alignment ss:Horizontal="Right"/>
      </Style>
    </Styles>`;

  const colDefs = columns.map(c => `<Column ss:Width="${c.width * 7}"/>`).join('\n      ');

  // Title row
  const titleRow = `
      <Row ss:Height="30">
        <Cell ss:StyleID="Title"><Data ss:Type="String">${escapeXml(title)}</Data></Cell>
      </Row>`;

  // Subtitle row
  const subtitleRow = subtitle ? `
      <Row ss:Height="20">
        <Cell ss:StyleID="Subtitle"><Data ss:Type="String">${escapeXml(subtitle)}</Data></Cell>
      </Row>` : '';

  // Date row
  const now = new Date().toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
  const dateRow = `
      <Row ss:Height="18">
        <Cell ss:StyleID="DateInfo"><Data ss:Type="String">Gerado em: ${escapeXml(now)}</Data></Cell>
      </Row>`;

  // Empty spacer row
  const spacerRow = `<Row ss:Height="10"/>`;

  // Header row
  const headerCells = columns.map(c => `<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(c.header)}</Data></Cell>`).join('');
  const headerRow = `<Row ss:Height="28">${headerCells}</Row>`;

  // Data rows
  const dataRows = rows.map((row, i) => {
    const isEven = i % 2 === 0;
    const baseStyle = isEven ? 'RowEven' : 'RowOdd';

    const cells = columns.map(c => {
      const value = row[c.key];

      // Confidence badge styling
      if (c.key === 'confidence' || c.key === 'confianca') {
        const v = String(value || '').toLowerCase();
        let badgeStyle = 'BadgeBaixa';
        if (v.includes('alta') || v.includes('high')) badgeStyle = 'BadgeAlta';
        else if (v.includes('méd') || v.includes('med')) badgeStyle = 'BadgeMedia';
        return `<Cell ss:StyleID="${badgeStyle}"><Data ss:Type="String">${escapeXml(value)}</Data></Cell>`;
      }

      // Website as link
      if (c.key === 'website' && value && String(value).startsWith('http')) {
        const linkStyle = isEven ? 'LinkEven' : 'Link';
        return `<Cell ss:StyleID="${linkStyle}" ss:HRef="${escapeXml(value)}"><Data ss:Type="String">${escapeXml(value)}</Data></Cell>`;
      }

      return `<Cell ss:StyleID="${baseStyle}"><Data ss:Type="String">${escapeXml(value)}</Data></Cell>`;
    }).join('');

    return `<Row ss:Height="24">${cells}</Row>`;
  }).join('\n      ');

  return `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:html="http://www.w3.org/TR/REC-html40">
  ${styles}
  <Worksheet ss:Name="${escapeXml(sheetName)}">
    <Table ss:DefaultRowHeight="20">
      ${colDefs}
      ${titleRow}
      ${subtitleRow}
      ${dateRow}
      ${spacerRow}
      ${headerRow}
      ${dataRows}
    </Table>
  </Worksheet>
</Workbook>`;
}
