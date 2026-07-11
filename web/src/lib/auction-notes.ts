const STORAGE_KEY = "mstc_auction_notes_v1";
function readNotesMap(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const data = JSON.parse(raw) as Record<string, unknown>;
    if (!data || typeof data !== "object" || Array.isArray(data)) return {};
    const next: Record<string, string> = {};
    for (const [id, note] of Object.entries(data)) {
      if (typeof note === "string") next[id] = note;
    }
    return next;
  } catch {
    return {};
  }
}
function writeNotesMap(notes: Record<string, string>): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(notes));
}
export function getAuctionNote(auctionId: string): string {
  return readNotesMap()[auctionId] ?? "";
}
export function setAuctionNote(auctionId: string, note: string): void {
  const trimmedId = auctionId.trim();
  if (!trimmedId) return;
  const notes = readNotesMap();
  const trimmedNote = note.trim();
  if (!trimmedNote) {
    delete notes[trimmedId];
  } else {
    notes[trimmedId] = trimmedNote;
  }
  writeNotesMap(notes);
}
export function deleteAuctionNote(auctionId: string): void {
  const notes = readNotesMap();
  if (!(auctionId in notes)) return;
  delete notes[auctionId];
  writeNotesMap(notes);
}
export function getAllAuctionNotes(): Record<string, string> {
  return readNotesMap();
}
