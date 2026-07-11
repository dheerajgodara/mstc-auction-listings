import type { Metadata } from "next";
import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import { SeoLandingPage } from "@/components/seo-landing-page";
import { buildTopDetailLinks } from "@/lib/seo/auction-url";
import { enrichAuctionDisplay } from "@/lib/display-enrichment";
import { loadAuctionsAtBuild } from "@/lib/load-auction-at-build";
import { landingPageQualifies } from "@/lib/seo/index-policy";
import { NOINDEX_METADATA } from "@/lib/seo/robots-meta";
import { absoluteUrl } from "@/lib/site-url";

interface StatePageConfig {
  slug: string;
  stateName: string;
  intro: string;
}

/** Fallback when public/data/seo-state-pages.json is absent (gitignored in CI). */
const DEFAULT_STATE_CONFIGS: StatePageConfig[] = [
  {
    slug: "uttar-pradesh",
    stateName: "Uttar Pradesh",
    intro:
      "Uttar Pradesh hosts frequent government scrap and surplus auctions from power utilities, railways, and state PSUs. Browse active auctions with parsed locations, quantities, and official document links.",
  },
  {
    slug: "maharashtra",
    stateName: "Maharashtra",
    intro:
      "Maharashtra is one of India's largest industrial auction markets with MSTC Western Region listings, port scrap, and PSU disposals in Mumbai, Pune, and Nagpur corridors.",
  },
  {
    slug: "karnataka",
    stateName: "Karnataka",
    intro:
      "Karnataka government auctions cover Bengaluru industrial scrap, mining minerals, and utility surplus from KPTCL and state departments.",
  },
  {
    slug: "tamil-nadu",
    stateName: "Tamil Nadu",
    intro:
      "Tamil Nadu auctions include Southern Region MSTC listings, port scrap, textile machinery, and PSU vehicle disposals across Chennai and Coimbatore.",
  },
  {
    slug: "gujarat",
    stateName: "Gujarat",
    intro:
      "Gujarat industrial auctions feature petrochemical scrap, port cargo, and Vadodara/Ahmedabad PSU surplus with high scrap volumes.",
  },
];

function loadStateConfigs(): StatePageConfig[] {
  const p = path.join(process.cwd(), "public", "data", "seo-state-pages.json");
  try {
    if (fs.existsSync(p)) {
      return JSON.parse(fs.readFileSync(p, "utf8")) as StatePageConfig[];
    }
  } catch {
    /* use defaults */
  }
  return DEFAULT_STATE_CONFIGS;
}

export const dynamicParams = false;

export function generateStaticParams(): { "state-slug": string }[] {
  try {
    const configs = loadStateConfigs();
    const data = loadAuctionsAtBuild();
    const params = configs
      .filter((cfg) => {
        const count = (data.auctions ?? []).filter((a) => {
          const st =
            enrichAuctionDisplay(a).display_location_state ?? a.state ?? "";
          return st.toLowerCase().includes(cfg.stateName.toLowerCase());
        }).length;
        return landingPageQualifies(count, 15);
      })
      .map((cfg) => ({ "state-slug": cfg.slug }));
    // output:export requires at least one concrete path when the segment exists
    if (params.length === 0) {
      return [{ "state-slug": configs[0]?.slug ?? "maharashtra" }];
    }
    return params;
  } catch {
    return [{ "state-slug": "maharashtra" }];
  }
}

type PageProps = { params: Promise<{ "state-slug": string }> };

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { "state-slug": slug } = await params;
  const cfg = loadStateConfigs().find((c) => c.slug === slug);
  if (!cfg) return { robots: NOINDEX_METADATA.robots };
  try {
    const data = loadAuctionsAtBuild();
    const auctions = (data.auctions ?? []).filter((a) => {
      const st = enrichAuctionDisplay(a).display_location_state ?? a.state ?? "";
      return st.toLowerCase().includes(cfg.stateName.toLowerCase());
    });
    const indexable = landingPageQualifies(auctions.length, 15);
    const title = `${cfg.stateName} Government Auctions | Scrap & Surplus Listings`;
    const description = `Active government auctions in ${cfg.stateName} — MSTC, GeM, and eAuction listings with lot details.`;
    return {
      title,
      description,
      alternates: { canonical: absoluteUrl(`/state/${slug}/`) },
      robots: indexable
        ? { index: true, follow: true }
        : NOINDEX_METADATA.robots,
    };
  } catch {
    return {
      title: `${cfg.stateName} Government Auctions`,
      robots: NOINDEX_METADATA.robots,
    };
  }
}

export default async function StateLandingPage({ params }: PageProps) {
  const { "state-slug": slug } = await params;
  const cfg = loadStateConfigs().find((c) => c.slug === slug);
  if (!cfg) notFound();
  let auctions: Awaited<ReturnType<typeof loadAuctionsAtBuild>>["auctions"] = [];
  try {
    const data = loadAuctionsAtBuild();
    auctions = (data.auctions ?? []).filter((a) => {
      const st = enrichAuctionDisplay(a).display_location_state ?? a.state ?? "";
      return st.toLowerCase().includes(cfg.stateName.toLowerCase());
    });
  } catch {
    notFound();
  }
  if (!landingPageQualifies(auctions.length, 15)) {
    // Placeholder path for empty CI datasets — keep export valid
    return (
      <SeoLandingPage
        title={`${cfg.stateName} Auctions`}
        description={`Government auction listings in ${cfg.stateName}.`}
        intro={`${cfg.intro}\n\nAlways verify on official source portals before bidding.`}
        auctions={[]}
        topLinks={[]}
      />
    );
  }
  return (
    <SeoLandingPage
      title={`${cfg.stateName} Auctions`}
      description={`${auctions.length} active government auction listings in ${cfg.stateName}.`}
      intro={`${cfg.intro}\n\nAlways verify on official source portals before bidding.`}
      auctions={auctions}
      topLinks={buildTopDetailLinks(auctions)}
    />
  );
}
