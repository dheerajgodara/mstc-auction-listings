#!/usr/bin/env node
/**
 * Generates docs/Airbnb_design_system_compliance_checklist.md from the Airbnb audit SoT.
 * Mapped to docs/airbnb_official_website_design_system_audit.md §§1–18.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outPath = path.resolve(
  __dirname,
  "../../docs/Airbnb_design_system_compliance_checklist.md",
);

const routes = [
  "/",
  "/[source]/[id]",
  "/scrap",
  "/metal-scrap",
  "/aluminium-scrap",
  "/coal-auctions",
  "/timber-auctions",
  "/vehicle-auctions",
  "/mstc-auctions",
  "/gem-forward-auctions",
  "/eauction-gov-in",
  "/hub/material/[id]",
  "/hub/region/[slug]",
  "/state/[state-slug]",
  "/watchlist",
  "/saved",
  "/map",
  "/insights",
  "/status",
  "/accessibility",
  "/pricing",
  "/account",
  "/support",
  "/app",
  "/terms",
  "/privacy",
  "/refund-policy",
  "/launch-readiness",
];

const sections = [
  {
    id: "01",
    title: "Typography (§1)",
    items: [
      { text: "Figtree loaded via next/font as Cereal-compatible face", method: "auto" },
      { text: "Font stack documents Airbnb Cereal VF + Circular + system fallbacks", method: "auto" },
      { text: "Body uses --font-text; display uses --font-display", method: "auto" },
      { text: "Weights 400/500/600/700 tokenized", method: "auto" },
      { text: "Type scale includes 14/16/18/22/26/32 and display 40+", method: "auto" },
      { text: "Body copy .text-body at 16px / ~20–24 line-height", method: "auto" },
      { text: "Titles use .text-title / .text-headline semibold", method: "visual" },
      { text: "Heroes use .text-display", method: "visual" },
      { text: "Captions .text-caption; footnotes .text-footnote 12px", method: "auto" },
      { text: "Display leading tight (~1.06); tracking tight", method: "auto" },
      { text: "Prices use tabular-nums", method: "auto" },
      { text: "No decorative monospace in UI chrome", method: "manual" },
    ],
  },
  {
    id: "02",
    title: "Color (§2)",
    items: [
      { text: "Rausch #ff385c primary brand token", method: "auto" },
      { text: "Product Rausch #e00b41 strong action", method: "auto" },
      { text: "--color-action maps to Rausch (not Apple blue)", method: "auto" },
      { text: "Babu #00a699 and Arches #fc642d accent tokens", method: "auto" },
      { text: "Hof #222222 marketplace neutral", method: "auto" },
      { text: "Marketplace gray scale 50–600", method: "auto" },
      { text: "Primary buttons Rausch gradient white text", method: "auto" },
      { text: "Secondary buttons neutral border and card bg", method: "auto" },
      { text: "No --color-action-blue leftover", method: "auto" },
      { text: "No glass-panel or btn-glass classes", method: "auto" },
      { text: "Muted text uses muted-foreground semantic", method: "auto" },
      { text: "Selected states use action/Rausch", method: "visual" },
      { text: "Disabled controls reduced opacity", method: "visual" },
      { text: "Scrim overlays neutral black not slate", method: "auto" },
    ],
  },
  {
    id: "03",
    title: "Layout (§3)",
    items: [
      { text: "container-marketplace max 1280px", method: "auto" },
      { text: "Homepage modular discovery stack wired", method: "manual" },
      { text: "Global nav in AppShell", method: "auto" },
      { text: "Market pulse ribbon band", method: "manual" },
      { text: "Hero headline + subcopy band", method: "visual" },
      { text: "Home modules horizontal scroll rows", method: "visual" },
      { text: "Ending soon tile grid", method: "manual" },
      { text: "Footer directory columns", method: "auto" },
      { text: "Detail page local breadcrumb nav", method: "visual" },
      { text: "Section bands use gray-100 / muted surfaces", method: "visual" },
      { text: "No page-bg grid patterns", method: "auto" },
      { text: "Sticky discovery toolbar on scroll", method: "visual" },
      { text: "List + filter drawer two-column desktop", method: "visual" },
      { text: "Max-width prose on legal copy", method: "manual" },
    ],
  },
  {
    id: "04",
    title: "Spacing (§4)",
    items: [
      { text: "Spacing tokens --space-2 through --space-96 defined", method: "auto" },
      { text: "Card padding uses space-16/24", method: "visual" },
      { text: "Section vertical rhythm space-56/96", method: "auto" },
      { text: "Nav height marketplace token (not Apple 44)", method: "auto" },
      { text: "Page padding 24px / 40px marketplace rhythm", method: "auto" },
      { text: "Grid gap consistent space-8/16", method: "visual" },
      { text: "Modal padding space-24", method: "manual" },
      { text: "Sticky bar padding space-16", method: "visual" },
    ],
  },
  {
    id: "05",
    title: "Imagery (§5)",
    items: [
      { text: "Auction photos lazy-loaded", method: "auto" },
      { text: "Alt text on informative images", method: "manual" },
      { text: "Aspect ratio preserved in listing cards", method: "visual" },
      { text: "No heavy decorative imagery in chrome", method: "manual" },
      { text: "Placeholder skeletons neutral gray", method: "visual" },
      { text: "Map tiles deferred load", method: "manual" },
      { text: "Gallery overlays readable contrast", method: "visual" },
    ],
  },
  {
    id: "06",
    title: "Components (§6)",
    items: [
      { text: "btn-primary pill radius + Rausch gradient", method: "auto" },
      { text: "btn-secondary pill radius neutral", method: "auto" },
      { text: "surface-elevated cards with hover elevation", method: "auto" },
      { text: "Chip primitive + active filter chips", method: "manual" },
      { text: "Modal focus trap and scrim", method: "auto" },
      { text: "Accordion disclosure pattern", method: "manual" },
      { text: "Filter drawer + bottom sheet", method: "auto" },
      { text: "Command palette dialog", method: "manual" },
      { text: "Pagination bar", method: "manual" },
      { text: "Auction card buyer-critical fields", method: "auto" },
      { text: "Auction table view mode", method: "manual" },
      { text: "Input/Select primitives marketplace styled", method: "auto" },
    ],
  },
  {
    id: "07",
    title: "Motion (§7)",
    items: [
      { text: "Duration tokens instant through ribbon", method: "auto" },
      { text: "--ease-standard and --ease-marketplace-nav", method: "auto" },
      { text: "Hover transitions use duration-hover", method: "auto" },
      { text: "prefers-reduced-motion respected globally", method: "auto" },
      { text: "No price-pulse or shimmer border effects", method: "auto" },
      { text: "Modal enter subtle", method: "visual" },
    ],
  },
  {
    id: "08",
    title: "Iconography (§8)",
    items: [
      { text: "Lucide icons stroke ~1.5 default", method: "manual" },
      { text: "Icons paired with text labels in nav", method: "visual" },
      { text: "Star for watchlist semantic", method: "manual" },
      { text: "ExternalLink for outbound bid", method: "manual" },
    ],
  },
  {
    id: "09",
    title: "Surfaces (§9)",
    items: [
      { text: "surface-base page background", method: "auto" },
      { text: "surface-elevated elevated cards", method: "auto" },
      { text: "surface-translucent-nav header", method: "auto" },
      { text: "Radius tokens xs through pill", method: "auto" },
      { text: "--shadow-subtle / --shadow-hover / --shadow-modal", method: "auto" },
      { text: "Tailwind listing-card shadow", method: "auto" },
      { text: "No glass-panel surfaces", method: "auto" },
    ],
  },
  {
    id: "10",
    title: "Content (§10)",
    items: [
      { text: "Marketplace buyer tone (no terminal metaphors)", method: "auto" },
      { text: "CTA View listing / Bid on source outbound", method: "manual" },
      { text: "Short hero subheads", method: "visual" },
      { text: "Disclaimer footnotes present", method: "auto" },
      { text: "Source capitalization MSTC GeM", method: "manual" },
      { text: "SEO copy human readable", method: "manual" },
    ],
  },
  {
    id: "11",
    title: "Navigation (§11)",
    items: [
      { text: "Global header with marketplace container", method: "auto" },
      { text: "Theme toggle in nav", method: "manual" },
      { text: "Mobile drawer", method: "visual" },
      { text: "Footer uses marketplace gray", method: "auto" },
      { text: "Detail breadcrumb", method: "visual" },
      { text: "Watchlist / Map / Pricing nav links", method: "manual" },
      { text: "Pricing page content inside AppShell", method: "auto" },
    ],
  },
  {
    id: "12",
    title: "Interaction (§12)",
    items: [
      { text: "focus-ring / focus-visible Rausch halo", method: "auto" },
      { text: "Hover elevation on surface-elevated", method: "auto" },
      { text: "Disabled opacity on buttons", method: "visual" },
      { text: "Touch targets min 44px primary CTAs", method: "auto" },
      { text: "Link hover underline on link-action", method: "auto" },
    ],
  },
  {
    id: "13",
    title: "Forms (§13)",
    items: [
      { text: "Input marketplace border and height", method: "auto" },
      { text: "Labels on filter fields", method: "manual" },
      { text: "Placeholder muted-foreground", method: "visual" },
      { text: "Search aria-label present", method: "manual" },
      { text: "Form error messages visible", method: "manual" },
    ],
  },
  {
    id: "14",
    title: "Responsive (§14)",
    items: [
      { text: "Breakpoints sm 744 / md 950 / lg 1128 / xl 1440 (not Apple)", method: "auto" },
      { text: "Mobile filter bottom sheet", method: "auto" },
      { text: "Desktop filter sidebar", method: "visual" },
      { text: "Cards single column mobile", method: "visual" },
      { text: "Nav hamburger mobile", method: "visual" },
      { text: "Safe area bottom sticky bars", method: "manual" },
    ],
  },
  {
    id: "15",
    title: "Accessibility (§15)",
    items: [
      { text: "main landmark on pages", method: "manual" },
      { text: "Modal aria-modal true", method: "auto" },
      { text: "Reduced motion global rule", method: "auto" },
      { text: "Focus visible not outline-none alone", method: "auto" },
      { text: "Decorative icons aria-hidden", method: "manual" },
      { text: "Color contrast Rausch on white CTAs", method: "visual" },
    ],
  },
  {
    id: "16",
    title: "SEO (§16)",
    items: [
      { text: "Metadata on routes", method: "manual" },
      { text: "Single h1 per page", method: "visual" },
      { text: "Sitemap static export", method: "manual" },
      { text: "Internal hub links", method: "manual" },
      { text: "Canonical / OG patterns", method: "manual" },
    ],
  },
  {
    id: "17",
    title: "Performance (§17)",
    items: [
      { text: "Static export out/", method: "manual" },
      { text: "Figtree subset via next/font (no pirated Cereal)", method: "auto" },
      { text: "Image lazy loading", method: "auto" },
      { text: "prefers-reduced-motion kills animations", method: "auto" },
    ],
  },
  {
    id: "18",
    title: "Design Tokens (§18)",
    items: [
      { text: "All color tokens in globals.css", method: "auto" },
      { text: "Type weight / leading / tracking tokens", method: "auto" },
      { text: "Full spacing + layout container tokens", method: "auto" },
      { text: "Radius + shadow + motion + z-index tokens", method: "auto" },
      { text: "Tailwind darkMode data-theme", method: "auto" },
      { text: "Tailwind action + marketplace-gray + marketplace easing", method: "auto" },
      { text: "HSL shadcn mapped from Rausch primary", method: "auto" },
    ],
  },
  {
    id: "19",
    title: "Cross-system",
    items: [
      { text: "verify-airbnb-design.mjs passes", method: "auto" },
      { text: "No Apple verifier / container-apple / ease-apple", method: "auto" },
      { text: "No terminal UI chrome copy", method: "auto" },
      { text: "Audit SoT present in docs/", method: "auto" },
      { text: "Production scrapauctionindia.com /auctions", method: "manual" },
    ],
  },
];

let lines = [
  "# Airbnb Design System Compliance Checklist",
  "",
  "Mapped to [`airbnb_official_website_design_system_audit.md`](airbnb_official_website_design_system_audit.md).",
  "",
  "Legend: `[x]` pass · `[ ]` pending · **auto** = verify script · **manual** = human QA · **visual** = browser check",
  "",
];

const markAuto = process.argv.includes("--mark-auto");
const markRoutes = process.argv.includes("--mark-routes");

let total = 0;
let checked = 0;
for (const sec of sections) {
  lines.push(`## ${sec.title}`);
  lines.push("");
  sec.items.forEach((item, i) => {
    const id = `DS-${sec.id}-${String(i + 1).padStart(3, "0")}`;
    const done = markAuto && item.method === "auto";
    if (done) checked++;
    lines.push(`- [${done ? "x" : " "}] **${id}** (${item.method}) ${item.text}`);
    total++;
  });
  lines.push("");
}

lines.push("## Per-route matrix (§3 + §11)");
lines.push("");
routes.forEach((route, ri) => {
  const base = `DS-RT-${String(ri + 1).padStart(2, "0")}`;
  const mark = markRoutes ? "x" : " ";
  if (markRoutes) checked += 3;
  lines.push(`### Route \`${route}\``);
  lines.push(`- [${mark}] **${base}-01** (auto) AppShell or equivalent global chrome`);
  lines.push(`- [${mark}] **${base}-02** (visual) text-display / text-body typography`);
  lines.push(`- [${mark}] **${base}-03** (visual) SiteFooter or route-appropriate footer`);
  lines.push("");
  total += 3;
});

lines.splice(4, 0, `**Total items: ${total}**${markAuto || markRoutes ? ` · **Checked: ${checked}**` : ""}`, "");

fs.writeFileSync(outPath, lines.join("\n"));
console.log(`Wrote ${total} checklist items to ${outPath}${checked ? ` (${checked} checked)` : ""}`);
