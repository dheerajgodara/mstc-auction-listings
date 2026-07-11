import type { LotRecord } from "@/types/auction";
function extractField(text: string, patterns: RegExp[]): string | null {
  for (const p of patterns) {
    const m = text.match(p);
    if (m) return m[1]?.trim() ?? m[0];
  }
  return null;
}
export function InspectionReport({ lots }: { lots: LotRecord[] }) {
  const combined = lots
    .map((l) =>
      [l.lot_parameters_text, l.lot_description_text, l.lot_details_text]
        .filter(Boolean)
        .join("\n"),
    )
    .join("\n");
  if (!combined.trim()) return null;
  const moisture = extractField(combined, [
    /moisture[:\s]+([^\n.]+)/i,
    /(\d+(?:\.\d+)?\s*%\s*moisture)/i,
  ]);
  const contamination = extractField(combined, [
    /contamination[:\s]+([^\n.]+)/i,
    /non[- ]metallic[:\s]+([^\n.]+)/i,
  ]);
  const weighbridge = extractField(combined, [
    /weighbridge[:\s]+([^\n.]+)/i,
    /weigh bridge[:\s]+([^\n.]+)/i,
  ]);
  if (!moisture && !contamination && !weighbridge) return null;
  return (
    <div className="surface-elevated p-4 text-body-sm">
      <h3 className="mb-3 text-title text-foreground">
        Inspection & quality norms
      </h3>
      <ul className="space-y-2 text-muted-foreground">
        {" "}
        {moisture && (
          <li>
            {" "}
            <span className="font-medium">Moisture / dust:</span>{" "}
            {moisture}{" "}
          </li>
        )}{" "}
        {contamination && (
          <li>
            {" "}
            <span className="font-medium">Contamination:</span>{" "}
            {contamination}{" "}
          </li>
        )}{" "}
        {weighbridge && (
          <li>
            {" "}
            <span className="font-medium">Weighbridge:</span> {weighbridge}{" "}
          </li>
        )}{" "}
      </ul>{" "}
    </div>
  );
}
export function extractPlantAccessRules(text: string): string[] {
  const rules: string[] = [];
  const lower = text.toLowerCase();
  if (lower.includes("bs-vi") || lower.includes("bs vi"))
    rules.push("BS-VI vehicles only");
  if (lower.includes("safety boot") || lower.includes("ppe"))
    rules.push("PPE / safety boots mandatory");
  if (lower.includes("pollution") && lower.includes("certificate")) {
    rules.push("Valid pollution certificate at gate");
  }
  return rules;
}
export function extractLiftingWindow(text: string): string | null {
  const m = text.match(
    /(?:lift|lifting|removal).{0,40}(\d+\s*(?:working\s*)?days?)[^.]*/i,
  );
  return m ? m[0].trim().slice(0, 120) : null;
}
