#!/usr/bin/env node

function hasText(value) {
  return Boolean(value && String(value).trim());
}

function synthesizeLotSectionText(lot, key) {
  if (key === "lot_details_text") {
    const lines = [];
    if (lot.lot_id) lines.push(`Lot No - ${lot.lot_id}`);
    if (lot.item_title && lot.item_title !== lot.lot_id) {
      lines.push(`Lot Name - ${lot.item_title}`);
    }
    if (lot.product_type) lines.push(`Product Type - ${lot.product_type}`);
    if (lot.category) lines.push(`Category - ${lot.category}`);
    return lines.length ? lines.join("\n") : null;
  }
  if (key === "lot_description_text") {
    return lot.item_description?.trim() || null;
  }
  if (key === "lot_parameters_text") {
    const lines = [];
    if (lot.quantity) lines.push(`Quantity - ${lot.quantity}`);
    if (lot.start_price != null) lines.push(`Start Price in INR - ${Math.trunc(lot.start_price)}`);
    return lines.length ? lines.join("\n") : null;
  }
  if (key === "lot_other_details_text") {
    const lines = [];
    if (lot.gst) lines.push(`GST (%) - ${lot.gst}`);
    if (lot.location) lines.push(`Lot Location - ${lot.location}`);
    return lines.length ? lines.join("\n") : null;
  }
  if (key === "lot_documents_text") {
    if (lot.annexure_file) {
      return `Annexure for Lot no ${lot.lot_id || "1"} - ${lot.annexure_file}`;
    }
    return null;
  }
  return null;
}

function getLotSectionDisplayText(lot, key) {
  const raw = lot[key];
  if (hasText(raw)) return String(raw).trim();
  const synthesized = synthesizeLotSectionText(lot, key);
  if (hasText(synthesized)) return synthesized.trim();
  return "Not available";
}

const lot = {
  lot_id: "1",
  item_title: "Godrej Safe",
  item_description: "Godrej Safe description",
  quantity: "1 LOT",
  start_price: 1,
  gst: "18%",
  location: "GURDASPUR",
  annexure_file: "Annex_test.pdf",
};

const details = getLotSectionDisplayText(lot, "lot_details_text");
const params = getLotSectionDisplayText(lot, "lot_parameters_text");
const other = getLotSectionDisplayText(lot, "lot_other_details_text");
const docs = getLotSectionDisplayText(lot, "lot_documents_text");

if (details === "Not available") {
  console.error("FAIL lot section synthesis: details");
  process.exit(1);
}
if (params === "Not available") {
  console.error("FAIL lot section synthesis: parameters");
  process.exit(1);
}
if (other === "Not available") {
  console.error("FAIL lot section synthesis: other details");
  process.exit(1);
}
if (docs === "Not available") {
  console.error("FAIL lot section synthesis: documents");
  process.exit(1);
}

console.log("OK  lot section display synthesis self-tests");
