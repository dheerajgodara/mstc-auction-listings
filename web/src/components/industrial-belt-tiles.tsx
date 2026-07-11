import Link from "next/link";
import { resolveAppPath, resolvePublicUrl } from "@/lib/utils";
const BELTS = [
  { slug: "ncr", label: "NCR & Haryana", sub: "Manesar · Faridabad" },
  { slug: "mumbai", label: "Maharashtra", sub: "Mumbai · Chakan" },
  { slug: "bengaluru", label: "Karnataka", sub: "Bengaluru belt" },
  { slug: "hyderabad", label: "Telangana", sub: "Hyderabad corridor" },
  { slug: "kolkata", label: "East", sub: "Kolkata belt" },
];
export function IndustrialBeltTiles() {
  return (
    <section className="space-y-2">
      {" "}
      <h2 className="text-sm font-semibold text-foreground dark:text-foreground">
        Industrial belts
      </h2>{" "}
      <div className="flex flex-wrap gap-2">
        {" "}
        {BELTS.map((b) => (
          <Link
            key={b.slug}
            href={resolveAppPath(`hub/region/${b.slug}/`)}
            className="rounded-lg border border-border bg-card px-3 py-2 text-left hover:border-action"
          >
            {" "}
            <p className="text-sm font-medium">{b.label}</p>{" "}
            <p className="text-[10px] text-muted-foreground">{b.sub}</p>{" "}
          </Link>
        ))}{" "}
      </div>{" "}
    </section>
  );
}
