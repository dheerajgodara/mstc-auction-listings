"use client";
import { useEffect, useState } from "react";
type Rate = { name: string; value: string; unit: string; as_of: string };
export function CommodityIndexWidget() {
  const [items, setItems] = useState<Rate[]>([]);
  useEffect(() => {
    fetch(
      `${process.env.NEXT_PUBLIC_BASE_PATH || "/auctions"}/data/benchmark-rates.json`,
    )
      .then((r) => r.json())
      .then((d) => setItems(d.rates ?? []))
      .catch(() => setItems([]));
  }, []);
  if (items.length === 0) return null;
  return (
    <section className="surface-elevated p-3">
      {" "}
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {" "}
        Reference mandi rates{" "}
      </h2>{" "}
      <div className="flex flex-wrap gap-3">
        {" "}
        {items.map((r) => (
          <div key={r.name} className="min-w-[120px]">
            {" "}
            <p className="text-[10px] text-muted-foreground">{r.name}</p>{" "}
            <p className="text-sm font-semibold tabular-nums text-action dark:text-action">
              {" "}
              {r.value}{" "}
              <span className="ml-0.5 text-xs font-normal text-muted-foreground">
                /{r.unit}
              </span>{" "}
            </p>{" "}
            <p className="text-footnote text-muted-foreground">as of {r.as_of}</p>
          </div>
        ))}{" "}
      </div>{" "}
      <p className="mt-2 text-[10px] text-muted-foreground">
        Reference only — verify before bidding.
      </p>{" "}
    </section>
  );
}
