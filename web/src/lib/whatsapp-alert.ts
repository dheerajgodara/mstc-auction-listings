export function whatsappAlertUrl(
  auctionTitle: string,
  detailUrl: string,
  closingIso?: string,
): string {
  const closing = closingIso
    ? new Date(closingIso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })
    : "";
  const text = encodeURIComponent(
    `Remind me about auction: ${auctionTitle}\nCloses: ${closing}\n${detailUrl}`,
  );
  return `https://wa.me/?text=${text}`;
}
