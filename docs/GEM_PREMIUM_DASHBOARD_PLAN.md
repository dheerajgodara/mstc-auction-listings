# GeM Premium Auction Intelligence Dashboard — Master Plan (v2.0)

**Status:** Awaiting approval  
**Supersedes:** `GEM_PREMIUM_ANALYSIS_SOP.md` v1.0 (operational detail retained there; this doc is the product + engineering spec)  
**Audience:** Product owner approval before build  
**Goal:** World-class, data-dense financial dashboard for 63 GeM scrap auctions — Bloomberg / TradingView inspired — enabling a **bid/no-bid decision in under 60 seconds**.

---

## 1. Executive summary

We will build a **standalone static dashboard** at:

`https://lightcyan-camel-979846.hostingersite.com/gem-reports/`

completely isolated from the live MSTC site (`/auctions/`). Each of 63 premium auctions gets a **self-contained HTML report** (all CSS/JS inlined — portable, offline-capable) plus a **hub** with sortable master index, portfolio-level KPIs, and cross-auction analytics.

**Core value proposition:** Transform raw GeM auction data (results, tender PDFs, OCR, market research) into an actionable **Bid Strategy Table** with scenario P&L, confidence scoring, and acceptance probability — not just a static write-up.

---

## 2. Non-negotiable constraints

| # | Constraint |
|---|------------|
| 1 | **Zero impact** on `web/`, `web/out/`, `public_html/auctions/`, or MSTC CI deploy |
| 2 | **Separate deploy path** only: `public_html/gem-reports/` |
| 3 | **Self-contained reports** — no CDN dependencies in production HTML (Chart.js, CSS, fonts vendored + inlined) |
| 4 | **Evidence chain** — every ₹ links to source (PDF page image, GeM URL, or cited research URL) |
| 5 | **60-second rule** — Net Margin visible without scrolling past **2 viewport heights** on desktop |
| 6 | **Mobile-first charts** — readable on 390px width without horizontal scroll on KPI section |

---

## 3. Hosting & repository architecture

### 3.1 Production URLs

| Resource | URL |
|----------|-----|
| Hub | `/gem-reports/` |
| Auction report | `/gem-reports/auctions/{id}/` |
| Analysis JSON | `/gem-reports/auctions/{id}/data.json` |
| Assets | `/gem-reports/auctions/{id}/docs/`, `images/` |

### 3.2 Repository layout (final)

```
gem-reports/
├── design-tokens.css              # colours, spacing, typography (source)
├── templates/
│   ├── base.html.j2               # dark theme shell, inlined assets
│   ├── hub.html.j2                # master index
│   ├── auction_report.html.j2     # per-auction dashboard
│   ├── partials/
│   │   ├── kpi_hero.html.j2
│   │   ├── bid_strategy_table.html.j2
│   │   ├── waterfall_chart.html.j2
│   │   ├── scenario_toggle.html.j2
│   │   ├── verdict_modal.html.j2
│   │   ├── lightbox.html.j2
│   │   └── print_summary.html.j2
│   └── assets/                    # vendored, copied inline at build
│       ├── chart.umd.min.js
│       ├── chartjs-plugin-gradient.min.js
│       ├── datatables.min.js
│       ├── datatables.min.css
│       ├── inter.woff2            # subset
│       └── report.js
├── build/                         # rsync target → Hostinger
└── schemas/
    └── analysis_v2.schema.json    # JSON contract

scraper/
├── gem_analysis_pipeline.py       # orchestrator CLI
├── gem_ocr_processor.py           # PDF→PNG, lot↔page mapping
├── gem_lot_extractor.py           # LLM + rules hybrid → JSON
├── gem_cost_engine.py             # logistics, tax, scenario P&L
├── gem_confidence.py              # 0–100% weighted score
├── gem_acceptance_model.py        # P(success) from checkpoint stats
├── gem_report_builder.py          # Jinja → static HTML
└── gem_reports_deploy.py          # rsync gem-reports/build only

work/
├── gem_premium_auctions.json
├── gem_premium_analysis/
├── gem_premium_docs/
└── gem_results_stats_checkpoint.json   # acceptance rate priors
```

### 3.3 Environment

```bash
HOSTINGER_GEM_REPORTS_DIR=.../public_html/gem-reports
OPENROUTER_API_KEY=...          # lot extraction QA / ambiguous OCR
GEM_REPORTS_BASE_URL=https://lightcyan-camel-979846.hostingersite.com/gem-reports
```

### 3.4 Deploy command (isolated)

```bash
PYTHONPATH=. python -m scraper.gem_analysis_pipeline --auction-id 34458 --full
PYTHONPATH=. python -m scraper.gem_reports_deploy
# Never runs scraper.deploy or touches web/out/
```

---

## 4. UI/UX design system

### 4.1 Aesthetic — "Terminal Finance" dark mode

Inspired by Bloomberg Terminal / TradingView Pro — not consumer fintech fluff.

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-deep` | `#0B0F19` | Page background |
| `--bg-panel` | `#121826` | Cards, tables |
| `--bg-glass` | `rgba(18,24,38,0.72)` | Glassmorphism KPI cards |
| `--border-subtle` | `rgba(255,255,255,0.08)` | Dividers |
| `--accent-blue` | `#3B82F6` | Links, focus |
| `--gain` | `#22C55E` | Profit, positive delta |
| `--loss` | `#EF4444` | Loss (muted: `#C75050` for large blocks) |
| `--alert` | `#F59E0B` | Marginal, pending, warnings |
| `--text-primary` | `#F1F5F9` | Headlines |
| `--text-muted` | `#94A3B8` | Labels, captions |

**Typography:** Inter (primary) or Geist — `font-feature-settings: "tnum"` for tabular numbers.  
**Financial figures:** `₹` prefix, Indian grouping (`12,34,567`), 2 decimal places for Cr/L display toggle.

### 4.2 Glassmorphism KPI hero

Four cards in a responsive grid (`1 col mobile → 2 col tablet → 4 col desktop`):

| Card | Content |
|------|---------|
| **Total H1** | Winning bid sum; Accepted vs Pending split chip |
| **Est. Gross Resale** | Scenario-aware (updates on toggle) |
| **Total Costs** | Logistics + compliance + fees + tax float |
| **Net P&L** | Large figure + **Verdict Badge** with soft glow |

**Verdict badge styles:**

| Verdict | Colour | Glow |
|---------|--------|------|
| STRONG PROFIT | Green | `box-shadow: 0 0 24px rgba(34,197,94,0.35)` |
| PROFIT | Green (dim) | subtle |
| MARGINAL | Amber | amber glow |
| LOSS | Red (muted) | red glow |
| STRONG LOSS | Red | strong glow |
| INDETERMINATE | Grey | none |

**Placement rule:** KPI hero + verdict badge = **first viewport** on desktop (1080p). Net P&L is the **largest typographic element** in the hero.

### 4.3 Scenario toggle (Best / Base / Worst)

Segmented control below KPI row — instant re-render of all financial figures and charts without page reload.

| Scenario | Rate source | Cost multiplier |
|----------|-------------|-----------------|
| **Best** | `rate_high` per material, quality_factor +0.1 | costs × 0.9 |
| **Base** | `rate_mid`, default quality | costs × 1.0 |
| **Worst** | `rate_low`, quality_factor −0.15 | costs × 1.15 |

State persisted in `sessionStorage` per auction page.

### 4.4 Charts (Chart.js + gradient plugin)

All charts: dark gridlines, no chart junk, animated on load (600ms ease-out).

| Chart | Spec |
|-------|------|
| **P&L Waterfall** | Floating bars: H1 → +gross uplift → −logistics → −compliance → −fees → −tax → net. **Hover tooltip shows formula** (see §6.3). Gradient fill on positive/negative bars. |
| **Cost donut** | Center label = **Net P&L ₹** (absolute, colour-coded). Segments: Purchase (grey), Logistics, CPCB, GeM fees, Tax float. |
| **Material mix pie** | By kg or ₹ — toggle. Legend right on desktop, below on mobile. |
| **H1 vs Market** | Grouped bar per lot: Opening | H1 | Est. market (scenario-aware). |
| **Verdict strip** | Horizontal stacked bar — one segment per lot, colour = verdict. Click segment → scroll to lot row. |
| **Hub portfolio chart** | Cumulative net P&L across 63 auctions (base scenario); verdict distribution donut. |

**Mobile:** Charts max-height 220px; simplified legends; tap for tooltip.

### 4.5 Bid Strategy Table (core UI)

The most important component. Full-width, sticky header, zebra rows on hover.

| Column | Description |
|--------|-------------|
| Lot | `1A`, `8A`, … |
| Contents | Truncated description + expand icon |
| Weight/Qty | Normalized display |
| Location | Site chip (MO(V), ND(V), …) |
| H1 ₹ | Winning bid |
| Gross ₹ | Scenario-aware |
| Costs ₹ | Breakdown icon → mini popover |
| **Net ₹** | Colour-coded |
| **Margin %** | vs H1 |
| **Verdict** | Badge — **click → modal** (margin drivers) |
| **Confidence** | 0–100% meter + label |
| **P(Success)** | Acceptance probability % |
| Status | Accepted / Pending / Rejected chip |
| Evidence | 📄 icon → lightbox page image |

**Interactions:**
- Sort by any numeric column (default: Net ₹ ascending = worst first for risk review)
- Filters: Verdict, Status, CPCB-only, Confidence &lt; 60%, Location
- Row hover: subtle `rgba(59,130,246,0.06)` highlight
- Keyboard: `↑/↓` row focus for power users

### 4.6 Modals & lightbox

**Verdict drill-down modal** (click badge):
- Margin drivers bullet list (e.g. "H1 31% above HMS melt", "528 battery weight uncertain")
- Assumptions used
- Link to evidence page image
- Scenario comparison mini-table

**Lightbox** (PDF page images):
- Vanilla JS — no heavy library
- Keyboard: `Esc` close, `←/→` page nav
- Pinch-zoom on mobile
- Sidebar: OCR text for active page
- Preload adjacent images

### 4.7 Document gallery

- PDF: `<iframe>` + download button + page count badge
- Thumbnail grid of PNG pages — click opens lightbox
- SHA256 hash displayed (collapsed) for audit trail

### 4.8 Print / export

**"Print Bid Summary"** button:
- CSS `@media print` strips nav, charts (optional), dark backgrounds
- Outputs 1–2 page **Bid Summary** — KPI, top 5 lots table, net margin, key risks, citations
- Uses white background, black text for paper

### 4.9 Navigation

- Sticky top bar: Hub | Auction #{n} | Prev/Next | Print | Scenario toggle
- Breadcrumb: `GeM Reports › #34458 › Indian Navy MO(V)`
- Hub row click → auction report

---

## 5. Hub architecture (`/gem-reports/index.html`)

### 5.1 Summary statistics (glass KPI row)

| Card | Calculation |
|------|-------------|
| **Auctions analysed** | `n / 63` |
| **Total H1 in queue** | Sum of all total_h1 |
| **Est. portfolio net (Base)** | Sum of net_profit_base |
| **Profitable auctions** | Count verdict ∈ {PROFIT, STRONG PROFIT} |
| **At-risk capital** | Sum H1 where verdict ∈ {LOSS, STRONG LOSS} |

### 5.2 Master index table (DataTables.js — vendored, inlined)

Columns: Rank | ID | Title | Region | H1 | Net (Base) | Verdict | Avg Confidence | Accepted % | Analysed date | Open

Features:
- Global search
- Column sort
- Filters: Verdict, Region, Category (scrap/vehicle/ewaste), Analysis status (done/pending)
- Pagination: 25/50/all
- Export buttons: CSV, Print

### 5.3 Hub charts

- Verdict distribution donut (all 63)
- Top 10 |net loss| bar chart
- Acceptance rate by category (from checkpoint data)

---

## 6. Advanced technical analysis

### 6.1 Analysis JSON schema v2

```json
{
  "schema_version": "2.0",
  "auction_id": "34458",
  "sequence": 1,
  "meta": { "title": "", "seller": "", "region": "", "auction_date": "", "analysed_at": "", "gem_urls": {} },
  "scenarios": {
    "best":  { "gross_resale_inr": 0, "total_costs_inr": 0, "net_profit_inr": 0, "margin_pct": 0, "verdict": "" },
    "base":  { "gross_resale_inr": 0, "total_costs_inr": 0, "net_profit_inr": 0, "margin_pct": 0, "verdict": "" },
    "worst": { "gross_resale_inr": 0, "total_costs_inr": 0, "net_profit_inr": 0, "margin_pct": 0, "verdict": "" }
  },
  "summary": {
    "total_h1_inr": 0,
    "accepted_h1_inr": 0,
    "lot_count": 0,
    "accepted_lot_count": 0,
    "portfolio_confidence_pct": 0,
    "weighted_p_success_pct": 0
  },
  "lots": [
    {
      "lot_code": "8A",
      "description": "",
      "lines": [
        {
          "sub_code": "A",
          "text": "Submarine batteries ×528",
          "quantity": 528,
          "unit": "nos",
          "weight_kg_est": 184800,
          "material_class": "lead_acid_battery",
          "location": "MO(V) Old Site",
          "flags": ["cpcb", "haz"],
          "evidence": { "pdf": "docs/Tender_document.pdf", "page_image": "images/page-03.png", "page_no": 3 }
        }
      ],
      "opening_inr": 8000000,
      "h1_inr": 21655000,
      "bidder": "",
      "status": "Accepted",
      "valuation": {
        "gross_best_inr": 0,
        "gross_base_inr": 0,
        "gross_worst_inr": 0,
        "rate_used": { "mid_inr_per_kg": 68, "source_url": "", "as_of": "" }
      },
      "costs": {
        "loading_inr": 0,
        "transport_inr": 0,
        "sorting_inr": 0,
        "compliance_inr": 0,
        "disposal_inr": 0,
        "gem_fee_inr": 0,
        "tax_float_inr": 0,
        "total_base_inr": 0,
        "formulas": []
      },
      "scenarios": { "best": {}, "base": {}, "worst": {} },
      "verdict_base": "MARGINAL",
      "confidence_pct": 42,
      "confidence_factors": {
        "source_quality": 0.7,
        "research_recency": 0.9,
        "yield_variance": 0.4
      },
      "p_success_pct": 78,
      "margin_drivers": ["…"]
    }
  ],
  "research_citations": [],
  "assumptions": [],
  "assets": { "pdfs": [], "page_images": [], "manifest_sha256": "" }
}
```

### 6.2 Confidence score (0–100%) — per lot

Weighted composite:

```
confidence = 100 × (
  0.40 × source_quality +
  0.35 × research_recency +
  0.25 × yield_certainty
)
```

| Factor | Score | Criteria |
|--------|-------|----------|
| **source_quality** | 0.0–1.0 | 1.0 = OCR + PDF page mapped + LLM validated; 0.7 = OCR only; 0.4 = notice text; 0.2 = inference from lot code only |
| **research_recency** | 0.0–1.0 | 1.0 if rate ≤7 days old; linear decay to 0.5 at 30 days; 0.3 if &gt;60 days |
| **yield_certainty** | 0.0–1.0 | 1.0 = weight in MT from tender; 0.6 = unit count × avg weight; 0.3 = wide range (&gt;40% spread); 0.1 = pure guess |

**Portfolio confidence** = H1-weighted average of lot confidence scores.

### 6.3 Logistics / cost engine (dynamic formulas)

Each cost line stores `{ amount_inr, formula, inputs }` for tooltip display.

**Loading:**
```
loading_inr = weight_mt × loading_rate_per_mt × site_factor
# site_factor: naval yard = 1.2, civilian = 1.0
```

**Transport:**
```
transport_inr = weight_mt × distance_km × fuel_factor_inr_per_mt_km
# fuel_factor default: ₹30/mt/km (tunable per region)
# Multi-site: sum per location group
```

**Compliance (CPCB/haz):**
```
compliance_inr = gross_base_inr × compliance_pct
# tyres/ewaste: 15%; submarine batteries: 20%; standard metal: 0%
```

**Disposal (negative-value items):**
```
disposal_inr = mattress_count × ₹75 + bottle_count × ₹10 + …
```

**GeM fee:**
```
gem_fee_inr = h1_inr × 0.015
```

**GST working capital (RCM):**
```
tax_float_inr = h1_inr × 0.18 × (float_days / 365) × (1 - itc_recovery_rate)
# itc_recovery_rate default 1.0 for registered dealers
```

**Waterfall tooltip example:**
```
Transport: 185 MT × 45 km × ₹30 = ₹2,49,750
```

### 6.4 P(Success) — acceptance probability

Derived from `gem_results_stats_checkpoint.json` priors:

```
p_success = P(Accepted | status published as H1) × category_factor × emd_factor
```

| Prior (checkpoint) | Value |
|--------------------|-------|
| Lot row → Accepted | ~47% |
| Lot row → Pending charge | ~42.5% |
| Lot row → Rejected | ~10.5% |

Adjustments:
- Already **Accepted** in result → 95% (residual = payment failure)
- **Pending** → 42.5% × 1.0
- High EMD relative to H1 → ×0.9
- CPCB lot without cert flag → ×0.7

Display as % in Bid Strategy Table with tooltip explaining prior.

### 6.5 Verdict thresholds (unchanged, applied per scenario)

| Verdict | Net margin % of H1 |
|---------|-------------------|
| STRONG PROFIT | &gt; +15% |
| PROFIT | +5% to +15% |
| MARGINAL | −5% to +5% |
| LOSS | −5% to −20% |
| STRONG LOSS | &lt; −20% |

---

## 7. Pipeline engine — implementation detail

### 7.1 Phase map (automated + human QA)

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ 1. INGEST   │──▶│ 2. OCR/MAP  │──▶│ 3. EXTRACT  │──▶│ 4. RESEARCH │
│ GeM+PDFs    │   │ pages↔lots  │   │ LLM+rules   │   │ web rates   │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
       │                                                        │
       ▼                                                        ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ 8. DEPLOY   │◀──│ 7. QA GATE  │◀──│ 6. HTML     │◀──│ 5. VALUE    │
│ Hostinger   │   │ checklist   │   │ Jinja build │   │ cost engine │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
```

### 7.2 `gem_ocr_processor.py`

- Download PDFs via both file-list URL patterns
- Render pages 150–200 DPI PNG → `images/page-{nn}.png`
- OCR full doc → `ocr/full.txt` with page markers
- **Lot mapper:** regex + layout heuristics link `lot_code` → `{page_no, bbox_est}`
- Output `manifest.json`: files, page count, lot_page_map

### 7.3 `gem_lot_extractor.py` (LLM + rules hybrid)

1. **Rules pass:** parse tables from OCR (qty, MT, nos, location)
2. **LLM pass** (OpenRouter via existing `ai_extractor.py` patterns):
   - Input: OCR chunk per page + GeM opening items
   - Output: strict JSON matching schema v2 `lines[]`
   - Validate with `analysis_v2.schema.json`
3. **Human QA flag** if confidence &lt; 60% or LLM/rule mismatch &gt;10%

### 7.4 `gem_cost_engine.py`

- Input: parsed lots + `market_rates_cache.json` + region defaults
- Output: scenarios + formulas[] per cost line
- Unit tests with auction 34458 fixtures

### 7.5 `gem_report_builder.py`

- Jinja2 render → single `index.html` per auction (~800KB–2MB with inlined JS)
- Embed `data.json` as `window.__ANALYSIS__` for scenario toggle (no fetch needed offline)
- Copy `docs/`, `images/` alongside HTML

### 7.6 CLI

```bash
# Full pipeline for one auction
python -m scraper.gem_analysis_pipeline --auction-id 34458 --full

# Rebuild HTML only (after manual JSON edit)
python -m scraper.gem_analysis_pipeline --auction-id 34458 --html-only

# Rebuild hub after any auction update
python -m scraper.gem_analysis_pipeline --hub-only

# Deploy
python -m scraper.gem_reports_deploy
```

---

## 8. Market research protocol (enhanced)

### 8.1 Per material class — minimum sources

| Class | Primary | Secondary | Refresh |
|-------|---------|-----------|---------|
| HMS / iron | scraprates.in city | IndiaMART MT quote | 7 days |
| Lead battery | scraprates.in battery | CPCB recycler quote | 7 days |
| Brass / Cu-Ni | scraprates.in + ScrapIndex | — | 14 days |
| E-waste mixed | scraprates.in e-waste | National Recycling recovery table | 14 days |
| Tyres | CPCB authorized rate | Local dealer | 14 days |

### 8.2 Citation object (required)

```json
{
  "material_class": "hms_iron",
  "rate_low": 29, "rate_mid": 33, "rate_high": 36,
  "unit": "INR/kg",
  "region": "Visakhapatnam",
  "url": "https://scraprates.in/visakhapatnam",
  "accessed": "2026-07-03",
  "snippet": "Iron ₹32.93/kg"
}
```

---

## 9. Per-auction analyst workflow (human steps)

| Step | Action | Time |
|------|--------|------|
| 1 | Run `--full` pipeline | 15–30 min auto |
| 2 | Review OCR lot mapper — fix page links if wrong | 15 min |
| 3 | Validate LLM extraction against page images | 20–45 min |
| 4 | Confirm market rates / add manual citation if needed | 15–30 min |
| 5 | Adjust assumptions for haz lots (battery weight etc.) | 15–60 min |
| 6 | Run QA checklist | 15 min |
| 7 | Approve → deploy | 5 min |

**Simple auction:** ~2 h | **Complex (34458-type):** ~5 h

---

## 10. QA & acceptance criteria

### 10.1 "Usable report" checklist

| # | Criterion | Pass? |
|---|-----------|-------|
| 1 | Net P&L visible within **2 screens** on 1080p desktop | |
| 2 | Scenario toggle updates all figures in **&lt;100ms** | |
| 3 | Bid Strategy Table sortable + filterable | |
| 4 | Waterfall tooltip shows formula on hover | |
| 5 | Donut center = Net P&L | |
| 6 | Verdict badge opens margin driver modal | |
| 7 | Lightbox works keyboard + mobile pinch | |
| 8 | Print produces clean 1–2 page summary | |
| 9 | Mobile: KPI stack readable, charts ≤220px | |
| 10 | No external CDN requests (offline test) | |
| 11 | `data.json` validates against schema v2 | |
| 12 | All PDFs + page images load from relative paths | |
| 13 | ≥3 research citations with dates | |
| 14 | Confidence + P(Success) on every lot row | |
| 15 | Lighthouse Performance ≥85, A11y ≥90 | |

### 10.2 60-second bid decision test

User must answer from index page alone:
1. Is this auction net profitable (base case)?
2. What is the biggest risk lot?
3. What is acceptance risk?

If any answer requires &gt;2 screens scroll → **fail**, redesign hero.

---

## 11. Implementation phases & milestones

### Phase A — Foundation (Week 1)

| Task | Deliverable |
|------|-------------|
| A1 | `analysis_v2.schema.json` |
| A2 | Fix file-list URL patterns in fetcher |
| A3 | `gem_ocr_processor.py` + manifest |
| A4 | Design tokens + base Jinja template (dark theme) |
| A5 | `gem_reports_deploy.py` + empty hub live on Hostinger |

**Milestone:** Empty styled hub at `/gem-reports/` deployed.

### Phase B — Intelligence pipeline (Week 2)

| Task | Deliverable |
|------|-------------|
| B1 | `gem_lot_extractor.py` (LLM + rules) |
| B2 | `gem_cost_engine.py` + unit tests |
| B3 | `gem_confidence.py` + `gem_acceptance_model.py` |
| B4 | `market_rates_cache.json` fetcher |
| B5 | Auction **34458** `data.json` v2 complete |

**Milestone:** JSON v2 for reference auction validated.

### Phase C — Dashboard UI (Week 3)

| Task | Deliverable |
|------|-------------|
| C1 | KPI hero + verdict badge + scenario toggle |
| C2 | Bid Strategy Table (sort/filter) |
| C3 | Waterfall + donut + material pie charts |
| C4 | Verdict modal + lightbox |
| C5 | Print CSS bid summary |
| C6 | Auction **34458** `index.html` complete |

**Milestone:** Reference report passes 60-second test.

### Phase D — Hub & scale (Week 4+)

| Task | Deliverable |
|------|-------------|
| D1 | Hub DataTables + portfolio KPIs |
| D2 | Hub charts (verdict distribution, top losses) |
| D3 | Batch pipeline for auctions 2–10 |
| D4 | GitHub Action `deploy-gem-reports.yml` (manual trigger) |
| D5 | Remaining 53 auctions (2–3 per day) |

**Milestone:** 63/63 analysed, hub portfolio view live.

---

## 12. Risk register

| Risk | Mitigation |
|------|------------|
| Scanned PDFs OCR garbage | LLM cleanup + page image side-by-side QA |
| Submarine battery weight unknown | Explicit range in worst/base/best; INDETERMINATE flag |
| Inline HTML file size &gt;3MB | Split vendored JS once; gzip on Hostinger |
| LLM hallucinated quantities | Schema validation + rule cross-check + confidence penalty |
| Market rates stale | `research_recency` factor + visible "as of" date on every rate |
| MSTC deploy accidental overlap | Separate deploy script; separate remote dir; CI guard |

---

## 13. Success metrics (post-launch)

| Metric | Target |
|--------|--------|
| Time to bid decision (user test) | ≤ 60 sec |
| Analysis coverage | 63/63 auctions |
| Avg portfolio confidence | Reported on hub |
| Mobile usability score | No horizontal scroll on KPI |
| Report portability | Opens correctly offline after save |

---

## 14. Approval checklist

Please confirm before build starts:

- [ ] **A.** Separate Hostinger path `/gem-reports/` — approved
- [ ] **B.** Dark Bloomberg-style UI with glassmorphism KPIs — approved
- [ ] **C.** Best / Base / Worst scenario toggle — approved
- [ ] **D.** Bid Strategy Table with Confidence + P(Success) — approved
- [ ] **E.** LLM lot extraction (OpenRouter) with human QA — approved
- [ ] **F.** All assets inlined (no CDN) — approved
- [ ] **G.** Phase A→D timeline acceptable — approved / adjust
- [ ] **H.** Proceed with auction **34458** as reference implementation — approved

**Approver:** _______________  
**Date:** _______________

---

## 15. Reference links

| Doc | Path |
|-----|------|
| Operational SOP (v1) | `docs/GEM_PREMIUM_ANALYSIS_SOP.md` |
| Premium auction data | `work/gem_premium_auctions.json` |
| Draft analysis #1 | `work/gem_premium_analysis/01_auction_34458.md` |
| Live MSTC (untouched) | `https://lightcyan-camel-979846.hostingersite.com/auctions/` |
| Target hub | `https://lightcyan-camel-979846.hostingersite.com/gem-reports/` |

---

*Plan v2.0 — GeM Premium Auction Intelligence Dashboard. Submit approval on §14 to begin Phase A.*
