# SOP — GeM Premium Auction Profit/Loss Analysis & HTML Report

**Version:** 1.0 (operational)  
**Product spec:** See **`GEM_PREMIUM_DASHBOARD_PLAN.md` v2.0** for UI, schema, and approval checklist.  
**Scope:** 63 auctions — Accepted + total H1 ≥ ₹10 lakh (from `work/gem_premium_auctions.json`)  
**Output:** Static HTML reports with charts, PDF embeds, page images, and cited market research  
**Hosting:** Hostinger — **separate path**, isolated from live MSTC site  

---

## 0. Principles

| Rule | Detail |
|------|--------|
| **One auction per run** | Full depth before moving to the next |
| **Evidence first** | Every ₹ figure traces to tender PDF, GeM page, or cited web source |
| **Confidence labels** | HIGH / MEDIUM / LOW on each valuation line |
| **No silent guesses** | Assumptions listed explicitly in report |
| **Isolation** | Never write to `web/`, `web/out/`, or `public_html/auctions/` |

---

## 1. Infrastructure & directory layout

### 1.1 Hostinger (production)

| Item | Path |
|------|------|
| **Existing MSTC site (do not touch)** | `public_html/auctions/` → `https://lightcyan-camel-979846.hostingersite.com/auctions/` |
| **New GeM analysis site** | `public_html/gem-reports/` → `https://lightcyan-camel-979846.hostingersite.com/gem-reports/` |

Deploy uses same SSH credentials as repo (`HOSTINGER_*` in `.env`); only `HOSTINGER_GEM_REPORTS_DIR` differs.

```bash
# .env addition (not committed)
HOSTINGER_GEM_REPORTS_DIR=/home/u268110164/domains/lightcyan-camel-979846.hostingersite.com/public_html/gem-reports
```

### 1.2 Repo (source of truth)

```
mstc-auction-listings/
├── docs/
│   └── GEM_PREMIUM_ANALYSIS_SOP.md          ← this file
├── gem-reports/                              ← static site SOURCE (new)
│   ├── templates/
│   │   ├── auction_report.html.j2            ← per-auction page
│   │   ├── index.html.j2                   ← hub listing 63 auctions
│   │   └── assets/
│   │       ├── report.css
│   │       ├── report.js                     ← Chart.js init
│   │       └── chart.umd.min.js
│   └── build/                                ← generated output → rsync target
│       ├── index.html
│       └── auctions/{auction_id}/
├── work/
│   ├── gem_premium_auctions.json             ← 63 enriched records
│   ├── gem_premium_analysis/
│   │   ├── {nn}_auction_{id}.json            ← structured analysis (machine)
│   │   ├── {nn}_auction_{id}.md              ← analyst notes (human)
│   │   └── market_rates_cache.json           ← dated rate snapshots + URLs
│   └── gem_premium_docs/{auction_id}/      ← PDFs + OCR text + page PNGs
└── scraper/
    ├── gem_premium_fetch.py                  ← existing enricher
    ├── gem_analysis_pipeline.py              ← NEW: orchestrates phases 2–6
    └── gem_reports_deploy.py                 ← NEW: rsync gem-reports/build only
```

### 1.3 Public URL map

```
/gem-reports/                                 Hub (table + summary charts)
/gem-reports/auctions/34458/                  Auction #1 report
/gem-reports/auctions/34458/docs/tender.pdf   Embedded PDF
/gem-reports/auctions/34458/images/page-02.png  OCR source page
/gem-reports/auctions/34458/data.json         Raw analysis JSON (optional)
```

---

## 2. Per-auction workflow (7 phases)

Process auctions in **descending total H1** order (same as hub index).

```
Phase 1 ─ Collect    GeM + PDFs + images
Phase 2 ─ Parse      Lot catalogue → structured lines
Phase 3 ─ Research   Market rates (web, cited)
Phase 4 ─ Value      Gross → costs → taxes → net P&L
Phase 5 ─ Build      HTML + charts + infographics
Phase 6 ─ QA         Checklist sign-off
Phase 7 ─ Publish    rsync to /gem-reports/ only
```

---

### Phase 1 — Data collection

**Inputs:** `auction_id` from `work/gem_premium_auctions.json`

| Step | Action | Tool / command |
|------|--------|----------------|
| 1.1 | Load enriched record (result, notice, rules) | `gem_premium_auctions.json` |
| 1.2 | Fetch notice HTML if stale | `GemForwardClient` transport `ssh` |
| 1.3 | Resolve file-list URL (both patterns) | Regex: `file-list/{id}/…` AND `file-list/0/44/0/{id}/…` |
| 1.4 | Download all attachments | tender, T&C, undertaking, BOQ, photos |
| 1.5 | Render each PDF page → PNG (200 DPI) | `pymupdf` |
| 1.6 | OCR scanned pages | `tesseract` + `pytesseract` |
| 1.7 | Save artefacts | `work/gem_premium_docs/{id}/` |

**Outputs:**

```
work/gem_premium_docs/34458/
├── Tender_document.pdf
├── Terms_Conditions.pdf
├── Tender_document_ocr.txt
├── pages/
│   ├── page-01.png
│   ├── page-02.png
│   └── …
└── manifest.json          ← filenames, SHA256, page count
```

**Gate:** ≥1 catalogue PDF with OCR text **or** lot table in notice HTML — else flag `INDETERMINATE_LOTS` and stop Phase 4 for affected lots.

---

### Phase 2 — Lot decomposition

**Goal:** One row per sub-line item with qty, unit, location, regulatory flags.

| Field | Source |
|-------|--------|
| `lot_code` | GeM rules (e.g. `1A`, `8A`) |
| `description` | Tender PDF OCR / BOQ |
| `quantity` | Parsed number |
| `unit` | MT, kg, nos, lot |
| `location` | MO(V), ND(V), Hyderabad, etc. |
| `emd_inr` | Tender pre-bid table |
| `opening_inr` | GeM business rules |
| `h1_inr` | Result page |
| `bidder` | Result page |
| `status` | Accepted / Pending / Rejected |
| `flags` | `cpcb`, `haz`, `ewaste`, `vehicle`, `property` |

**Parser rules:**

1. Split OCR by `Lot No` / `\d+A` headers.
2. Sub-items `(A)`, `(B)`, … under each lot.
3. Normalize weights: `150 MT` → `{qty: 150, unit: "MT", kg: 150000}`.
4. Cross-check: sum of lot H1 = `fresh_summary.total_bid_inr` (±₹1).

**Output:** `work/gem_premium_analysis/{nn}_auction_{id}.json` → `lots[]` array.

---

### Phase 3 — Market research (mandatory internet)

**Rule:** Minimum **3 independent sources** per material class used in the auction. Record URL, date accessed, and rate used.

#### 3.1 Source tiers

| Tier | Examples | Use |
|------|----------|-----|
| **A — Regional scrap indices** | [scraprates.in](https://scraprates.in) (city page), IndiaMART bulk quotes | Primary ₹/kg |
| **B — Commodity / trade** | ScrapIndex, LME-linked lead/copper commentary | Cross-check |
| **C — Regulatory context** | CPCB e-waste rules, GST RCM notifications 36/2017 | Cost flags, not ₹/kg |
| **D — Institutional** | GeM comparable closed auctions (same category) | Sanity check |

#### 3.2 Rate card (update per auction date region)

Store snapshot in `work/gem_premium_analysis/market_rates_cache.json`:

```json
{
  "region": "Visakhapatnam",
  "as_of": "2026-06-02",
  "rates": {
    "hms_iron_inr_per_kg": { "low": 29, "mid": 33, "high": 36, "sources": ["…"] },
    "lead_acid_battery_inr_per_kg": { "low": 66, "mid": 68, "high": 71, "sources": ["…"] },
    "mixed_ewaste_inr_per_kg": { "low": 35, "mid": 45, "high": 55, "sources": ["…"] },
    "brass_inr_per_kg": { "low": 380, "mid": 410, "high": 430, "sources": ["…"] },
    "aluminium_inr_per_kg": { "low": 140, "mid": 152, "high": 165, "sources": ["…"] },
    "cupro_nickel_inr_per_kg": { "low": 280, "mid": 350, "high": 450, "sources": ["…"] }
  }
}
```

#### 3.3 Research checklist (per auction)

- [ ] Identify **seller city/state** → pick regional rate page
- [ ] List **unique material classes** in lots
- [ ] Fetch current ₹/kg or ₹/unit for each class (Tier A)
- [ ] Note **bulk discount** (−10–20% for mixed/low grade; +10% for sorted HMS)
- [ ] Check **hazardous / CPCB** lots → add compliance cost % (10–25% of gross)
- [ ] GST: RCM applicable on govt disposal → model 18% cash float (metals), ITC recovery flag
- [ ] Log all URLs in `research_citations[]` in analysis JSON

---

### Phase 4 — Valuation & P&L model

#### 4.1 Gross resale (per lot line)

```
gross = quantity_kg × rate_mid_inr_per_kg × quality_factor
     OR quantity_nos × unit_scrap_inr × condition_factor
```

| `quality_factor` | When |
|------------------|------|
| 1.0 | Clean HMS, sorted |
| 0.85 | Mixed machinery scrap |
| 0.70 | Contaminated / BER |
| 0.50 | Mattresses, wood, glass bottles (disposal drag) |

#### 4.2 Cost stack (per lot)

| Cost | Default range | Notes |
|------|---------------|-------|
| **Purchase (H1)** | actual bid | from GeM |
| **Loading** | ₹500–800 / MT | naval yards higher end |
| **Transport** | ₹1,500–2,500 / MT / 50 km | multi-site → sum per location |
| **Cutting / sorting** | ₹500–1,000 / MT | machinery lots |
| **CPCB / haz** | 10–25% of gross | batteries, tyres, e-waste |
| **Disposal** | ₹50–150 / mattress; ₹5–15 / bottle | negative value items |
| **GeM transaction** | ~1.5% of H1 | buyer charge |
| **GST working capital** | 18% × H1 × float_days/365 | if ITC recovered → net ~0 |

#### 4.3 Net P&L

```
net_profit = gross_resale − h1_purchase − logistics − compliance − gem_fees − net_tax_cost
margin_pct = net_profit / h1_purchase × 100
```

#### 4.4 Verdict scale

| Verdict | Net margin (% of H1) |
|---------|----------------------|
| **STRONG PROFIT** | > +15% |
| **PROFIT** | +5% to +15% |
| **MARGINAL** | −5% to +5% |
| **LOSS** | −5% to −20% |
| **STRONG LOSS** | < −20% |
| **INDETERMINATE** | Missing weight/catalogue |

#### 4.5 Scenario bands

Always compute **Low / Mid / High** gross using rate card bounds → report as shaded band in charts.

---

### Phase 5 — HTML report generation

**Tech:** Static HTML + CSS + Chart.js (no Next.js — keeps deploy independent of MSTC `web/` build).

#### 5.1 Page sections (per auction)

1. **Hero** — Auction ID, title, seller, date, total H1, verdict badge  
2. **Executive infographic** — 4 KPI cards: H1 | Est. gross | Est. costs | Net P&L  
3. **Waterfall chart** — H1 → gross → costs → net (Chart.js bar/waterfall)  
4. **Lot map** — Table: lot code, contents, H1, gross, net, verdict, confidence  
5. **P&L donut** — Cost breakdown (purchase / logistics / tax / compliance)  
6. **Material mix** — Pie chart by weight or value (ferrous / non-ferrous / e-waste / other)  
7. **H1 vs market** — Scatter or bar: opening vs H1 vs est. market per lot  
8. **Document gallery** — PDF iframe + page PNG thumbnails (click → lightbox)  
9. **Lot catalogue** — OCR text beside page image (side-by-side)  
10. **Research appendix** — Cited URLs, rate table, assumptions  
11. **GeM links** — Notice, result, rules (external)  
12. **Navigation** — Prev / next auction, back to hub  

#### 5.2 Infographic specs

| Graphic | Type | Data |
|---------|------|------|
| KPI cards | CSS grid | 4 numbers + delta arrows |
| P&L waterfall | Chart.js floating bar | purchase, +gross gap, −each cost |
| Cost donut | Chart.js doughnut | logistics, tax, compliance, fees |
| Material pie | Chart.js pie | kg or ₹ by class |
| Lot verdict strip | Horizontal stacked bar | green/yellow/red per lot |
| Confidence meter | CSS | % HIGH / MED / LOW lines |
| Location map | Static SVG (AP/Telangana pins) | multi-site auctions only |

#### 5.3 PDF & image display

```html
<!-- PDF embed -->
<iframe src="docs/Tender_document.pdf" class="pdf-frame"></iframe>
<a href="docs/Tender_document.pdf" download>Download tender PDF</a>

<!-- Page proof (OCR source) -->
<figure>
  <img src="images/page-02.png" alt="Lot catalogue page 2" loading="lazy">
  <figcaption>Lot 1A–3A catalogue (OCR source)</figcaption>
</figure>
```

- Generate thumbnails: max width 1200px PNG  
- Lazy-load images below fold  
- `manifest.json` drives gallery order  

#### 5.4 Hub index (`/gem-reports/index.html`)

- Sortable table: rank, ID, title, H1, net P&L, verdict, status  
- Summary charts: verdict distribution (63 auctions), total H1 vs total est. net  
- Progress tracker: `12 / 63 analysed`  
- Filter: Accepted only, scrap only, loss only  

---

### Phase 6 — QA checklist (sign-off before publish)

| # | Check |
|---|-------|
| 1 | All lots in result page appear in analysis |
| 2 | H1 sums match GeM result ±₹1 |
| 3 | Every lot has confidence label |
| 4 | ≥3 research citations with dates |
| 5 | PDFs open in report (relative paths) |
| 6 | All page PNGs match OCR text |
| 7 | Charts render with non-zero data |
| 8 | No broken links to `/auctions/` |
| 9 | `data.json` validates against schema |
| 10 | Mobile layout readable (CSS media query) |

---

### Phase 7 — Publish to Hostinger

```bash
# Build HTML for one auction or all
PYTHONPATH=. python -m scraper.gem_analysis_pipeline \
  --auction-id 34458 \
  --build-html

# Or rebuild hub + all completed analyses
PYTHONPATH=. python -m scraper.gem_analysis_pipeline --build-all

# Deploy ONLY gem-reports (never touches /auctions/)
PYTHONPATH=. python -m scraper.gem_reports_deploy
```

`gem_reports_deploy.py` rsyncs `gem-reports/build/` → `$HOSTINGER_GEM_REPORTS_DIR`.

**Verify:** `https://lightcyan-camel-979846.hostingersite.com/gem-reports/auctions/34458/`

---

## 3. Analysis JSON schema (contract)

```json
{
  "auction_id": "34458",
  "sequence": 1,
  "meta": {
    "title": "…",
    "seller": "…",
    "region": "Visakhapatnam",
    "auction_date": "2026-06-02",
    "analysed_at": "2026-07-03T…",
    "analyst_version": "1.0"
  },
  "summary": {
    "total_h1_inr": 39623490,
    "accepted_h1_inr": 34738601,
    "gross_resale_mid_inr": 31000000,
    "total_costs_inr": 5500000,
    "net_profit_mid_inr": -9100000,
    "verdict": "LOSS",
    "confidence": "MEDIUM"
  },
  "lots": [
    {
      "lot_code": "8A",
      "description": "Submarine batteries ×528 + mattresses ×2000",
      "h1_inr": 21655000,
      "gross_low_inr": 12600000,
      "gross_mid_inr": 16200000,
      "gross_high_inr": 19700000,
      "costs_inr": 4500000,
      "net_mid_inr": -9955000,
      "verdict": "MARGINAL",
      "confidence": "LOW",
      "lines": [ … ]
    }
  ],
  "research_citations": [
    { "url": "https://scraprates.in/visakhapatnam", "accessed": "2026-07-03", "used_for": "HMS iron ₹33/kg" }
  ],
  "assumptions": [
    "Submarine battery avg weight 350 kg — not confirmed without inspection"
  ],
  "assets": {
    "pdfs": ["docs/Tender_document.pdf"],
    "page_images": ["images/page-02.png"]
  }
}
```

---

## 4. Auction queue (63)

Process in this order (H1 descending). Tick when HTML published.

| # | ID | H1 ₹ | Status |
|---|-----|------|--------|
| 1 | 34458 | 3.96 Cr | Analysis draft ✓ — HTML pending |
| 2 | 31705 | 2.77 Cr | |
| 3 | 33637 | 2.05 Cr | |
| … | … | … | |
| 63 | 33677 | 10.1 L | |

Full ID list: `work/gem_premium_auctions.json` → sort by `fresh_summary.total_bid_inr`.

---

## 5. Roles & time budget

| Phase | Est. time / auction |
|-------|---------------------|
| 1 Collect | 15–30 min (automated) |
| 2 Parse | 20–45 min (OCR QA) |
| 3 Research | 30–60 min |
| 4 Value | 30–45 min |
| 5 HTML | 10 min (automated) + 15 min review |
| 6 QA | 15 min |
| 7 Publish | 5 min |
| **Total** | **~2.5–4 hours** (simple) to **6–8 hours** (multi-site haz lots) |

---

## 6. What we do NOT do

- Do not merge into MSTC Next.js app or `web/out/` build  
- Do not run GeM full-population crawl during analysis sprints  
- Do not publish without PDF/page images when catalogue exists  
- Do not use a single ₹/kg for mixed lots without line-item split  
- Do not mark PROFIT without deducting logistics + compliance  

---

## 7. Implementation roadmap (repo tasks)

| Priority | Task | File |
|----------|------|------|
| P0 | Fix `find_file_list_url` for `file-list/0/44/0/{id}/…` | `gem_scrap_samples_fetch.py` |
| P0 | PDF → PNG page export + manifest | `gem_analysis_pipeline.py` |
| P0 | HTML template + Chart.js charts | `gem-reports/templates/` |
| P1 | Hub index generator | `gem_analysis_pipeline.py` |
| P1 | Separate deploy script | `gem_reports_deploy.py` |
| P2 | `market_rates_cache` auto-fetch from scraprates | optional scraper |
| P2 | GitHub Action `deploy-gem-reports.yml` (manual only) | `.github/workflows/` |

---

## 8. Example live URLs (after first publish)

| Page | URL |
|------|-----|
| Hub | `https://lightcyan-camel-979846.hostingersite.com/gem-reports/` |
| Auction #1 | `https://lightcyan-camel-979846.hostingersite.com/gem-reports/auctions/34458/` |
| MSTC (unchanged) | `https://lightcyan-camel-979846.hostingersite.com/auctions/` |

---

*This SOP is the single reference for all 63 premium auction analyses. Update version when valuation rules or deploy path changes.*
