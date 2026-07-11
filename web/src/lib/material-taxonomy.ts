export type MaterialNode = {
  id: string;
  label: string;
  children?: MaterialNode[];
  /** display_material_category values that match this node */ match: string[];
};
export const MATERIAL_TAXONOMY: MaterialNode[] = [
  {
    id: "ferrous",
    label: "Ferrous",
    match: ["ferrous_scrap", "steel", "hms"],
    children: [
      {
        id: "hms",
        label: "HMS 1 & 2",
        match: ["ferrous_scrap", "hms", "melting"],
      },
      {
        id: "turning",
        label: "MS turning / boring",
        match: ["turning", "boring", "ms scrap"],
      },
    ],
  },
  {
    id: "non_ferrous",
    label: "Non-ferrous",
    match: ["aluminium", "copper", "brass", "conductor"],
    children: [
      {
        id: "copper",
        label: "Copper & cable",
        match: ["copper", "cable", "wire"],
      },
      {
        id: "aluminium",
        label: "Aluminium",
        match: ["aluminium", "conductor"],
      },
    ],
  },
  {
    id: "ewaste",
    label: "E-waste (CPCB)",
    match: ["ewaste", "e-waste", "pcb"],
  },
  {
    id: "machinery",
    label: "Plant machinery",
    match: ["machinery", "plant", "loom", "equipment"],
  },
  { id: "vehicle", label: "Vehicles", match: ["vehicle"] },
];
export function flattenMaterialIds(
  nodes: MaterialNode[],
): Map<string, string[]> {
  const map = new Map<string, string[]>();
  function walk(n: MaterialNode) {
    map.set(n.id, n.match);
    n.children?.forEach(walk);
  }
  nodes.forEach(walk);
  return map;
}
export function auctionMatchesMaterialIds(
  category: string | null | undefined,
  title: string | null | undefined,
  selectedIds: Set<string>,
): boolean {
  if (selectedIds.size === 0) return true;
  const hay = `${category ?? ""} ${title ?? ""}`.toLowerCase();
  const flat = flattenMaterialIds(MATERIAL_TAXONOMY);
  for (const id of selectedIds) {
    const patterns = flat.get(id) ?? [];
    if (patterns.some((p) => hay.includes(p.toLowerCase()))) return true;
  }
  return false;
}
