import {
  formatLotPrice,
  formatQuantityUnit,
  getLotSectionDisplayText,
} from "@/lib/format";
import { formatDateTime } from "@/lib/utils";
import { resolveMediaUrl } from "@/lib/listing-pdf";
import type { LotRecord } from "@/types/auction";
function LotField({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (!value || value === "—") return null;
  return (
    <div className="min-w-0">
      {" "}
      <dt className="text-caption font-medium text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-0.5 break-words text-sm tabular-nums text-foreground">
        {value}
      </dd>{" "}
    </div>
  );
}
function LotCard({ lot, index }: { lot: LotRecord; index: number }) {
  const title = lot.item_title?.trim() || `Lot ${index + 1}`;
  const details = getLotSectionDisplayText(lot, "lot_details_text");
  const description = getLotSectionDisplayText(lot, "lot_description_text");
  return (
    <article
      className="surface-elevated space-y-3 p-4"
      id={`lot-${lot.lot_id || index}`}
    >
      {" "}
      <header>
        {" "}
        <h3 className="text-heading text-foreground">{title}</h3>{" "}
        {lot.lot_id && (
          <p className="text-caption mt-1">Lot ID: {lot.lot_id}</p>
        )}{" "}
      </header>{" "}
      <dl className="grid gap-3 sm:grid-cols-2">
        {" "}
        <LotField label="Start price" value={formatLotPrice(lot)} />{" "}
        <LotField
          label="Quantity"
          value={formatQuantityUnit(lot.quantity, lot.unit)}
        />{" "}
        <LotField label="Location" value={lot.location} />{" "}
        <LotField label="State" value={lot.lot_state} />{" "}
        <LotField label="Category" value={lot.category} />{" "}
        <LotField
          label="Bid valid till"
          value={lot.bid_valid_till ? formatDateTime(lot.bid_valid_till) : null}
        />{" "}
      </dl>{" "}
      {description !== "Not available" && (
        <div>
          {" "}
          <h4 className="text-xs font-semibold uppercase text-muted-foreground">
            Description
          </h4>{" "}
          <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
            {description}
          </p>{" "}
        </div>
      )}{" "}
      {details !== "Not available" && details !== description && (
        <div>
          {" "}
          <h4 className="text-xs font-semibold uppercase text-muted-foreground">
            Details
          </h4>{" "}
          <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
            {details}
          </p>{" "}
        </div>
      )}{" "}
      {lot.documents && lot.documents.length > 0 && (
        <ul className="flex flex-wrap gap-2 text-sm">
          {" "}
          {lot.documents.map((doc, i) => {
            const href = doc.cached_url ? resolveMediaUrl(doc.cached_url) : null;
            if (!href) return null;
            return (
              <li key={`${doc.filename}-${i}`}>
                {" "}
                <a
                  href={href}
                  className="link-action"
                  rel="noopener noreferrer"
                >
                  {" "}
                  {doc.type}: {doc.filename}{" "}
                </a>{" "}
              </li>
            );
          })}{" "}
        </ul>
      )}{" "}
    </article>
  );
}
export function AuctionDetailLots({ lots }: { lots: LotRecord[] }) {
  if (!lots.length) {
    return (
      <p className="text-sm text-muted-foreground">No lot details available.</p>
    );
  }
  return (
    <section aria-labelledby="lots-heading" className="space-y-4">
      {" "}
      <h2 id="lots-heading" className="text-heading text-foreground">
        {" "}
        Lots ({lots.length}){" "}
      </h2>{" "}
      <div className="space-y-4">
        {" "}
        {lots.map((lot, index) => (
          <LotCard key={lot.lot_id || String(index)} lot={lot} index={index} />
        ))}{" "}
      </div>{" "}
    </section>
  );
}
