export const CSV_HEADERS = [
  "productName",
  "manufacturerName",
  "dosageForm",
  "manufacturingDate",
  "expiryDate",
  "price"
];

const HEADER_ALIASES = new Map([
  ["productname", "productName"],
  ["product name", "productName"],
  ["manufacturername", "manufacturerName"],
  ["manufacturer name", "manufacturerName"],
  ["dosageform", "dosageForm"],
  ["dosage form", "dosageForm"],
  ["manufacturingdate", "manufacturingDate"],
  ["manufacturing date", "manufacturingDate"],
  ["expirydate", "expiryDate"],
  ["expiry date", "expiryDate"],
  ["price", "price"],
  ["price (lkr)", "price"]
]);

function mapHeader(header) {
  const trimmed = header.trim().replace(/^\uFEFF/, "");
  const normalized = trimmed.toLowerCase().replace(/\s+/g, " ");
  return HEADER_ALIASES.get(normalized) || trimmed;
}

export function parseProductsCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let insideQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (insideQuotes) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        insideQuotes = false;
      } else {
        field += character;
      }
    } else if (character === '"' && field.length === 0) {
      insideQuotes = true;
    } else if (character === '"') {
      throw new Error("CSV contains a quote outside a quoted field.");
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n" || character === "\r") {
      row.push(field);
      if (row.some((value) => value.trim() !== "")) rows.push(row);
      row = [];
      field = "";
      if (character === "\r" && text[index + 1] === "\n") index += 1;
    } else {
      field += character;
    }
  }
  if (insideQuotes) throw new Error("CSV has an unclosed quoted field.");
  row.push(field);
  if (row.some((value) => value.trim() !== "")) rows.push(row);

  if (rows.length < 2) throw new Error("CSV must contain a header and at least one product row.");
  const headers = rows[0].map(mapHeader);
  if (new Set(headers).size !== headers.length) {
    throw new Error("CSV headers must not be duplicated.");
  }
  const missingHeaders = CSV_HEADERS.filter((header) => !headers.includes(header));
  if (missingHeaders.length) {
    throw new Error(`CSV is missing required columns: ${missingHeaders.join(", ")}.`);
  }
  return rows.slice(1).map((values, index) => {
    if (values.length !== headers.length) {
      throw new Error(`CSV row ${index + 2} has ${values.length} fields; expected ${headers.length}.`);
    }
    const product = Object.fromEntries(
      headers.map((header, column) => [header, values[column].trim()])
    );
    for (const header of CSV_HEADERS) {
      if (!product[header]) throw new Error(`CSV row ${index + 2}: ${header} is required.`);
    }
    return { rowNumber: index + 2, product };
  });
}
