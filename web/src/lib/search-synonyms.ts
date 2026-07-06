/** Material/search synonym expansion per production readiness plan §3.11 */

const SYNONYM_GROUPS: string[][] = [
  ["aluminium", "aluminum", "al conductor", "acsr", "aluminium conductor"],
  ["tower", "transmission tower", "tower parts", "transmission"],
  ["cable", "wire", "conductor", "earthwire", "earth wire"],
  ["scrap", "ms scrap", "iron scrap", "ferrous", "hms", "steel scrap"],
  ["vehicle", "car", "truck", "bus", "auto", "end of life vehicle"],
  ["timber", "wood", "logs", "teak", "sal"],
  ["transformer oil", "used oil", "insulating oil", "sludge oil"],
  ["coal", "rom", "g10", "g12", "g13"],
  ["machinery", "machine", "plant", "equipment"],
  ["moose", "deer", "panther", "conductor scrap"],
];

const TOKEN_TO_GROUP = new Map<string, number>();

for (let i = 0; i < SYNONYM_GROUPS.length; i++) {
  for (const term of SYNONYM_GROUPS[i]) {
    TOKEN_TO_GROUP.set(term.toLowerCase(), i);
  }
}

/** Expand query tokens with synonym group members for search matching. */
export function expandSearchTokens(query: string): string[] {
  const raw = query
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/gu)
    .filter((t) => t.length > 1);
  const out = new Set(raw);
  const groups = new Set<number>();
  for (const token of raw) {
    const g = TOKEN_TO_GROUP.get(token);
    if (g !== undefined) groups.add(g);
    for (const [key, gi] of TOKEN_TO_GROUP.entries()) {
      if (token.includes(key) || key.includes(token)) groups.add(gi);
    }
  }
  for (const g of groups) {
    for (const term of SYNONYM_GROUPS[g]) out.add(term);
  }
  return Array.from(out);
}

export function queryMatchesSynonym(haystack: string, query: string): boolean {
  const h = haystack.toLowerCase();
  return expandSearchTokens(query).some((t) => h.includes(t));
}
