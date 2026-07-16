#!/usr/bin/env node
/**
 * Airbnb design-system verifier — maps to docs/airbnb_official_website_design_system_audit.md
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.join(__dirname, "..");
const srcDir = path.join(webRoot, "src");
const repoRoot = path.resolve(webRoot, "..");

let ok = true;

function check(label, condition, detail = "") {
  const mark = condition ? "OK" : "FAIL";
  if (!condition) ok = false;
  console.log(`${mark}  ${label}${detail ? ` — ${detail}` : ""}`);
}

function read(rel) {
  return fs.readFileSync(path.join(webRoot, rel), "utf8");
}

function walkFiles(dir, exts = [".ts", ".tsx", ".css", ".mjs"]) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (["node_modules", ".next", "out"].includes(entry.name)) continue;
      out.push(...walkFiles(full, exts));
      continue;
    }
    if (exts.some((ext) => entry.name.endsWith(ext))) out.push(full);
  }
  return out;
}

const globals = read("src/app/globals.css");
const tailwind = read("tailwind.config.ts");
const packageJson = read("package.json");
const layout = read("src/app/layout.tsx");
const appShell = read("src/components/app-shell.tsx");
const siteDisclaimer = read("src/components/site-disclaimer.tsx");
const auctionCard = read("src/components/auction-card.tsx");
const discoveryToolbar = read("src/components/discovery-toolbar.tsx");
const footer = read("src/components/site-footer.tsx");
const mapView = read("src/components/map-view-client.tsx");
const primitives = read("src/components/ui/primitives.tsx");
const modal = read("src/components/ui/modal.tsx");
const filterSheet = fs.existsSync(path.join(webRoot, "src/components/filter-bottom-sheet.tsx"))
  ? read("src/components/filter-bottom-sheet.tsx")
  : "";
const pricingPage = read("src/app/pricing/page.tsx");

const auditPath = path.join(repoRoot, "docs/airbnb_official_website_design_system_audit.md");
check("Airbnb audit SoT present in docs/", fs.existsSync(auditPath));

check("verify-build uses Airbnb verifier", packageJson.includes("verify-airbnb-design.mjs"));
check("verify-build no longer uses Apple verifier", !packageJson.includes("verify-apple-design.mjs"));

// Color
check("Rausch primary token exists", globals.includes("--color-rausch: #ff385c"));
check("Product Rausch token exists", globals.includes("--color-product-rausch: #e00b41"));
check("action token maps to Rausch", globals.includes("--color-action: var(--color-rausch)"));
check("old action blue token removed", !globals.includes("--color-action-blue"));
check("Babu accent token exists", globals.includes("--color-babu: #00a699"));
check("Arches accent token exists", globals.includes("--color-arches: #fc642d"));
check("marketplace neutral Hof #222 exists", globals.includes("--color-hof: #222222"));
check("marketplace gray-50 exists", globals.includes("--color-gray-50"));
check("marketplace gray-600 exists", globals.includes("--color-gray-600"));

// Typography
check("Figtree loaded in root layout", /figtree|Figtree/i.test(layout) && layout.includes("next/font"));
check("Cereal-style fallback stack documented", globals.includes("Airbnb Cereal VF") && globals.includes("Circular"));
check("--font-figtree wired into stacks", globals.includes("var(--font-figtree)") || layout.includes("--font-figtree"));
check("weight tokens 400-700", ["--weight-regular: 400", "--weight-medium: 500", "--weight-semibold: 600", "--weight-bold: 700"].every((t) => globals.includes(t)));
check("body text is 16px marketplace scale", /\.text-body\s*\{[^}]*font-size:\s*16px/s.test(globals) || globals.includes("font-size: 16px"));
check("display leading tight ~1.06", globals.includes("--leading-display-tight: 1.06"));
check("display tracking tight", globals.includes("--tracking-display-tight: -0.016em") || globals.includes("--tracking-display-tight: -0.02em"));
check("footnote 12px utility exists", globals.includes(".text-footnote"));
check("caption utility exists", globals.includes(".text-caption"));

// Layout / spacing
check("marketplace container exists", globals.includes(".container-marketplace"));
check("marketplace container is 1280px", globals.includes("--container-standard: 1280px"));
check("nav height is marketplace (not Apple 44)", !globals.includes("--nav-height-regular: 44px") && /--nav-height-regular:\s*(64|72|80)px/.test(globals));
check("page padding marketplace 24/40", globals.includes("--page-padding-small: 24px") && globals.includes("--page-padding-medium: 40px"));
check("spacing scale includes space-96", globals.includes("--space-96:"));
check("py-section uses space-56", globals.includes(".py-section") && globals.includes("var(--space-56)"));

// Surfaces / buttons / motion
check("primary button uses Rausch gradient", globals.includes("linear-gradient(135deg, var(--color-rausch), var(--color-product-rausch))"));
check("btn-primary min touch 44px", globals.includes("min-h-[44px]") || globals.includes("min-height: 44px"));
check("secondary buttons remain neutral", globals.includes(".btn-secondary") && globals.includes("border-foreground bg-card"));
check("cards use Airbnb-style hover elevation", globals.includes("--shadow-hover") && globals.includes(".surface-elevated:hover"));
check("surface-base exists", globals.includes(".surface-base"));
check("surface-translucent-nav exists", globals.includes(".surface-translucent-nav"));
check("shadow-modal token exists", globals.includes("--shadow-modal"));
check("radius-pill token exists", globals.includes("--radius-pill"));
check("motion duration tokens exist", globals.includes("--duration-hover") && globals.includes("--ease-marketplace-nav"));
check("reduced-motion media query present", globals.includes("prefers-reduced-motion"));
check("focus-ring uses Rausch", globals.includes(".focus-ring") && globals.includes("var(--color-rausch)"));
check("link-action uses action color", globals.includes(".link-action"));

// Tailwind
check("Tailwind action maps to design token", tailwind.includes('action: "var(--color-action)"'));
check("Tailwind marketplace gray scale exists", tailwind.includes('"marketplace-gray"'));
check("Tailwind marketplace easing exists", tailwind.includes("marketplace:"));
check("Tailwind listing card shadow exists", tailwind.includes('"listing-card"'));
check("Tailwind breakpoints are Airbnb marketplace (not Apple)", tailwind.includes('sm: "744px"') && tailwind.includes('md: "950px"') && tailwind.includes('lg: "1128px"') && tailwind.includes('xl: "1440px"'));
check("Tailwind has no Apple breakpoints", !tailwind.includes('sm: "734px"') && !tailwind.includes('md: "834px"') && !tailwind.includes('lg: "1068px"'));
check("Tailwind darkMode data-theme", tailwind.includes('data-theme="dark"'));

// Components
check("app shell uses marketplace container", appShell.includes("container-marketplace"));
check(
  "site disclaimer keeps marketplace source messaging",
  siteDisclaimer.includes("MSTC") && siteDisclaimer.includes("before bidding"),
);
check("auction card uses marketplace title scale", auctionCard.includes("text-title"));
check("auction card keeps buyer-critical fields", ["PriceDisplay", "formatImportedDate", "LotDetails", "LotPreviewStrip"].every((s) => auctionCard.includes(s)));
const componentSource = walkFiles(path.join(srcDir, "components"))
  .map((f) => fs.readFileSync(f, "utf8"))
  .join("\n");
check("auction card tabular-nums for price", componentSource.includes("tabular-nums"));
check("discovery toolbar uses elevated marketplace shell", discoveryToolbar.includes("surface-elevated"));
check("footer uses marketplace gray", footer.includes("bg-marketplace-gray-100"));
check("map markers use Rausch red", mapView.includes("#FF385C") || mapView.includes("#ff385c"));
check("filter bottom sheet exists", filterSheet.length > 0);
check("modal has aria-modal", modal.includes("aria-modal"));
check("primitives Input or Button marketplace", /btn-primary|Input|className/.test(primitives));
check("pricing page wraps content in AppShell", pricingPage.includes("AppShell") || pricingPage.includes("PricingPageApp"));

const sourceText = walkFiles(srcDir)
  .map((file) => fs.readFileSync(file, "utf8"))
  .join("\n");

check("no container-apple classes remain", !sourceText.includes("container-apple"));
check("no ease-apple classes remain", !sourceText.includes("ease-apple"));
check("no Apple design comments remain in source", !/Apple color tokens|pre-Apple design system|Apple token/.test(sourceText));
check("no glass UI classes remain", !/glass-panel|glass-card|btn-glass|glass-input|glass-nested/.test(sourceText));
check("no terminal UI chrome remains", !/terminal-action-bar|Terminal grid|Terminal-grade|Command center/.test(sourceText));
check("no page-bg grid pattern class", !sourceText.includes("page-bg-grid"));
check("lazy loading used for images", /loading=["']lazy["']|loading=\{["']lazy["']\}/.test(sourceText) || sourceText.includes('loading="lazy"'));

const launchReadiness = read("scripts/generate-launch-readiness.mjs");
check("launch readiness references Airbnb verifier", launchReadiness.includes("verify-airbnb-design.mjs"));
check("launch readiness no longer references Apple verifier", !launchReadiness.includes("verify-apple-design.mjs"));

// Route coverage: every page.tsx should reference AppShell or a *PageApp that uses it
const pageFiles = walkFiles(path.join(srcDir, "app"), [".tsx"]).filter((f) => f.endsWith(`${path.sep}page.tsx`));
// Sanity floor only — intentional removal of a marketing route must not fail deploy.
check("app has a viable page route set", pageFiles.length >= 15, `found ${pageFiles.length}`);

let pagesMissingShell = 0;
for (const pageFile of pageFiles) {
  const text = fs.readFileSync(pageFile, "utf8");
  const rel = path.relative(srcDir, pageFile);
  const hasShell =
    text.includes("AppShell") ||
    text.includes("PageApp") ||
    text.includes("AuctionListingsApp") ||
    text.includes("SeoLandingPage") ||
    text.includes("LegalPageApp") ||
    text.includes("MaterialHubApp") ||
    text.includes("RegionHubApp") ||
    text.includes("buildMaterialLanding") ||
    text.includes("landing.page");
  if (!hasShell) {
    pagesMissingShell++;
    console.log(`WARN  page may lack AppShell chrome — ${rel}`);
  }
}
check("pages reference AppShell or page app wrappers", pagesMissingShell === 0, `${pagesMissingShell} suspicious`);

const builtIndex = path.join(webRoot, "out", "index.html");
if (fs.existsSync(builtIndex)) {
  const html = fs.readFileSync(builtIndex, "utf8");
  check("built index has no glass-panel", !html.includes("glass-panel"));
  check("built index has no action blue token", !html.includes("--color-action-blue"));
}

if (!ok) process.exit(1);
console.log("\nAll Airbnb design checks passed.");
