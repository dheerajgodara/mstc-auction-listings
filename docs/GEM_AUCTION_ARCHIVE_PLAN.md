# GeM Premium Auction — Informational Archive Plan (v3)

**Status:** For approval — replaces P&L dashboard approach  
**Problem with v2:** Profit/loss model used guessed reuse values, synthetic formulas, and material-class buckets. Portfolio showed “PROFIT” while individual lots were nonsensical (e.g. 700 PCs valued optimistically). **Not trustworthy for decisions.**

**New goal:** A **plain, evidence-based reference** — what was in each lot (from documents), what H1 was (from GeM), and what market rates exist for those item types (from cited research). **No profit/loss, no verdicts, no scenarios, no confidence scores.**

---

## 1. What the user gets (one auction page)

Each auction report answers exactly three questions:

| # | Question | Source |
|---|----------|--------|
| 1 | **What was in each lot, item by item?** | Tender PDF (OCR + human QA) + GeM notice |
| 2 | **What was the H1 bid?** | GeM result page |
| 3 | **What are current market rates for those item types?** | Internet research (cited, dated) — **reference only** |

Nothing else. No net margin, no waterfall, no “should I bid”.

---

## 2. Information hierarchy (lot → item)

```
Auction
├── Meta (title, ref no, seller, location, dates, GeM links)
├── Documents (PDF embed + page images)
└── Lot 1A
    ├── Lot header (location, EMD, opening price, unit of sale)
    ├── Result (H1 ₹, bidder, bid time, acceptance status)
    ├── Items[] (the core)
    │   ├── Item A: full description from tender
    │   ├── Item B: ...
    │   └── ...
    └── Market rates[] (rates that apply to items in THIS lot only)
```

**Rule:** Every item row must trace to a **document line** (tender page + optional notice). If OCR is unclear, show `[OCR uncertain]` and the page image — do not invent quantities.

---

## 3. Item record schema (what we store per line)

```json
{
  "sub_code": "D",
  "description_verbatim": "Polypropylene Rope (different types of diameters such as 24mm, 32mm, 48mm, 64mm etc) Scrap",
  "quantity": 30,
  "unit": "MT",
  "quantity_notes": null,
  "location": "MO(V) / OLD SITE",
  "contact": "0891-2815089 / 5095",
  "unit_of_sale": "By Lot",
  "pre_bid_emd_inr": 100000,
  "regulatory_notes": "CPCB/MOEF/State PCB certificate required",
  "evidence": {
    "source": "tender_pdf",
    "page_no": 2,
    "page_image": "images/page-02.png",
    "ocr_excerpt": "Polypropylene Rope ... Qty- 30 MT"
  },
  "material_tags": ["polypropylene_rope", "rope_scrap"],
  "market_rates": [
    {
      "label": "Mixed plastic rope scrap (India bulk)",
      "rate_low_inr": 8,
      "rate_high_inr": 18,
      "rate_unit": "per kg",
      "region": "India",
      "as_of": "2026-07-03",
      "source_url": "https://...",
      "source_note": "Indicative dealer range — not a quote for this lot",
      "match_reason": "material_tags → polypropylene_rope"
    }
  ]
}
```

**No fields for:** gross_inr, net_profit, verdict, margin_pct, scenarios, reuse_value_inr.

---

## 4. Lot record schema

```json
{
  "lot_code": "1A",
  "items": [ ... ],
  "lot_notes_from_tender": "NOTE: VALID CPCB...",
  "opening_price_inr": 200000,
  "increment_inr": 20000,
  "result": {
    "h1_inr": 4580000,
    "h1_display": "₹45,80,000",
    "bidder": "MARIYAM STEEL",
    "bid_datetime": "18/03/2026 13:29:26",
    "acceptance_status": "Accepted",
    "premium_over_opening_pct": 4480
  },
  "item_count": 5,
  "document_pages": [2]
}
```

---

## 5. How we read and understand documents (extraction pipeline)

### Step 1 — Acquire (unchanged)
- GeM notice, result, rules (already in `gem_premium_auctions.json`)
- Tender PDF + T&C via file-list URL
- Page PNGs at 180–200 DPI
- Full OCR text with page markers

### Step 2 — Parse lot blocks (new, strict)
1. Split OCR on `Lot No` / `\d+A` patterns
2. Within each block, extract sub-items `(A)`, `(B)`, … `(Z)`
3. For each sub-item parse:
   - Description (text before `Qty`)
   - `Qty-N` / `Qty - N` / `aty- N` (OCR tolerance)
   - Unit: `MT`, `Nos`, `Kgs`, `Grms`
   - Location, contact, EMD, unit disp (`By Lot`, `By Count`, `By Weight`)
4. Cross-link to GeM **opening price** row (`1A`, `2A`, …)
5. Cross-link to GeM **result** row (H1, bidder, status)

### Step 3 — Human QA gate (mandatory for publish)
| Check | Action |
|-------|--------|
| Lot count matches GeM rules (9 lots = 9 rows) | Block publish if mismatch |
| Every item has `page_image` | Required |
| Quantity ambiguous in OCR | Flag `needs_review`; show both OCR variants |
| Missing sub-item letters | Do not merge lots — fix parser or manual edit |

### Step 4 — Optional LLM assist (read-only structuring)
- Input: OCR chunk + page image reference
- Output: JSON items[] **only** — no valuations
- LLM **forbidden** from: inventing qty, adding items not in OCR, assigning ₹ values
- Validator rejects if item count &lt; OCR line count − tolerance

### Step 5 — Market rate attachment (per item, not per lot)
For each item, after `material_tags` are assigned:
1. Look up rate card (see §6)
2. Attach 1–3 **reference rates** with URL + date
3. If no good match → `market_rates: []` + tag `rate_research_pending`

**Never multiply** qty × rate on the page. Optional footnote only:  
*“Indicative: 30 MT × ₹12/kg ≈ ₹3.6L reference — not a valuation.”* — **off by default**, user asked for no calculations.

---

## 6. Market rate research (reference table only)

### 6.1 Rate card structure (`work/gem_market_rates.json`)

```json
{
  "updated": "2026-07-03",
  "entries": [
    {
      "id": "hms_iron_visakhapatnam",
      "tags": ["hms_iron", "mt_scrap", "iron_scrap"],
      "label": "HMS / iron melting scrap",
      "rate_low": 29,
      "rate_high": 36,
      "rate_typical": 33,
      "unit": "INR/kg",
      "region": "Visakhapatnam",
      "sources": [
        { "url": "https://scraprates.in/visakhapatnam", "accessed": "2026-07-03", "quote": "Iron ₹32.93/kg" }
      ]
    }
  ]
}
```

### 6.2 Tag → rate mapping rules

| material_tags | Rate entries to attach |
|---------------|------------------------|
| `hms_iron`, `mt_scrap`, `machinery_scrap` | HMS iron (regional) |
| `steel_wire_rope` | Steel wire / cable scrap |
| `polypropylene_rope` | Plastic rope / PP scrap |
| `aluminium_scrap` | Aluminium scrap |
| `brass`, `brass_boring` | Brass scrap |
| `cupro_nickel` | Cupro-nickel / Cu-Ni scrap |
| `bearing_scrap` | Bearing / alloy steel scrap |
| `mixed_ewaste`, `computer`, `television` | E-waste mixed OR per-device table |
| `electrical_scrap` | Electrical / copper-bearing scrap |
| `tyre` | Tyre scrap per kg or per tyre |
| `wood_scrap` | Wood / timber scrap |
| `industrial_equipment`, `crane`, `engine` | **No ₹/kg** — attach note: “Resale highly variable; no standard scrap ₹/kg” |
| `mattress` | Disposal cost note only, or “no standard market rate” |
| `boat`, `genie`, `forklift` | Equipment — note only |

### 6.3 Research protocol per auction
- Use **auction region** (city/state from notice) for regional scrap pages
- Minimum **2 sources** per material class where rates exist
- Record `as_of` date on every rate
- Refresh rates weekly; show **“Rates as of DATE”** banner on every page

### 6.4 Presenting rates on the page (item row)

Each item shows a small **“Market reference”** sub-table:

| Source | Region | Rate range | Unit | As of |
|--------|--------|------------|------|-------|
| scraprates.in | Visakhapatnam | ₹29–36 | /kg | 2026-07-03 |

If multiple tags match (e.g. brass coupling + brass boring), show both rate rows.

---

## 7. HTML presentation plan

### 7.1 Design shift from v2
- Keep **dark, clean, readable** — but remove KPI profit cards, waterfall, verdict badges, scenario toggle
- Tone: **reference archive / catalogue**, not trading terminal

### 7.2 Auction page layout (top → bottom)

#### Block A — Auction header (compact)
- Auction ID, reference no, title
- Seller, location, auction date
- Links: GeM notice | GeM result
- Summary line: **9 lots · Total H1 ₹2,77,39,461 · 7 Accepted**

#### Block B — Documents (evidence)
- Tender PDF iframe + download
- Page thumbnail strip → lightbox (unchanged from v2)

#### Block C — Lot index (jump links)
```
1A · 2A · 3A · 4A · 5A · 6A · 7A · 8A · 9A
```
Sticky on desktop; dropdown on mobile.

#### Block D — One section per lot (repeat × N)

```
┌─────────────────────────────────────────────────────────────┐
│ LOT 1A                                    MO(V) Old Site    │
├─────────────────────────────────────────────────────────────┤
│ GeM opening: ₹2,00,000    EMD: ₹1,00,000    Sale: By Lot   │
│ CPCB: Required                                            │
├─────────────────────────────────────────────────────────────┤
│ RESULT (GeM)                                                │
│ H1: ₹45,80,000  │  Bidder: MARIYAM STEEL  │  Accepted      │
│ Bid time: 18/03/2026 13:29:26                             │
├─────────────────────────────────────────────────────────────┤
│ ITEMS (from tender document, page 2)                        │
│                                                             │
│ ┌────┬──────────────────────────────────┬──────┬─────────┐ │
│ │    │ Description                      │ Qty  │ Unit    │ │
│ ├────┼──────────────────────────────────┼──────┼─────────┤ │
│ │ A  │ Hand Trolley Assorted            │ 5    │ Nos     │ │
│ │    │ Market ref: [equipment — no std rate]             │ │
│ ├────┼──────────────────────────────────┼──────┼─────────┤ │
│ │ B  │ Fork Lifters Assorted            │ 11   │ Nos     │ │
│ │ ...│                                                  │ │
│ │ D  │ Polypropylene Rope Scrap (24–64mm) │ 30  │ MT    │ │
│ │    │ Market ref: ₹8–18/kg (India bulk) [scraprates…]   │ │
│ │ E  │ Steel Wire Rope Scrap            │ 3    │ MT     │ │
│ │    │ Market ref: ₹28–35/kg [source]                    │ │
│ └────┴──────────────────────────────────┴──────┴─────────┘ │
│                                                             │
│ [View source page 2 →]                                      │
└─────────────────────────────────────────────────────────────┘
```

#### Block E — Master market rate appendix (auction-level)
Alphabetical table of **all unique rate types** used in this auction + full citations. Avoids repeating long citations on every item row.

#### Block F — Assumptions & limitations (short)
- OCR source noted
- Rates are indicative, not quotes
- H1 ≠ confirmed sale until Accepted
- No P&L interpretation

### 7.3 Hub page (`/gem-reports/`)
Simple table — **no portfolio profit**:

| # | ID | Title | Lots | Total H1 | Analysed | Open |
|---|-----|-------|------|----------|----------|------|
| 2 | 31705 | Navy MO(V) scrap… | 9 | ₹2.77 Cr | ✓ | View |

Filter: analysed / pending. Search by ID or title.

### 7.4 Mobile
- Lot sections accordion (tap to expand)
- Item table: card layout (description, qty, H1 at lot level only once)
- Market ref collapses to “Rates →” expander

### 7.5 Print
- One section per lot; items table + H1 + rate refs
- No charts

---

## 8. Example — Lot 2A (31705) done properly

**Lot 2A — Mixed electronics (CPCB)**

**Result:** H1 **₹27,60,787** · Aman E waste Recyclers Pvt Ltd · **Accepted**

**Items (from tender, page 2)** — every line listed, not summarized:

| Code | Description | Qty | Unit |
|------|-------------|-----|------|
| A | Projectors Assorted | 15 | Nos |
| B | Laptops Assorted | 11 | Nos |
| C | Binoculars Assorted | 135 | Nos |
| D | Television Assorted | 500 | Nos |
| E | Camera Assorted | 15 | Nos |
| F | CCTV Camera Assorted | 20 | Nos |
| G | Thermal imaging Camera Assorted | 6 | Nos |
| H | Water Purifier Assorted | 150 | Nos |
| J | Computers / All in One PC Assorted | 700 | Nos |
| K | Printers Assorted | 100 | Nos |
| L | Xerox Machine Assorted | 50 | Nos |
| M | Air Conditioners Assorted | 50 | Nos |
| N | Refrigerators Assorted | 30 | Nos |
| P | Washing Machines Assorted | 20 | Nos |
| Q | Micro Ovens Assorted | 25 | Nos |
| R | Geysers Assorted | 10 | Nos |
| S | Generators Assorted | 8 | Nos |
| T | Sextant Assorted | 6 | Nos |
| U | Bearing Site Assorted | 14 | Nos |
| V | Micro Scope Assorted | 21 | Nos |
| W | Fans Assorted | 300 | Nos |
| X | Grass/Tree Branch Cutting Machines | 21 | Nos |
| Y | Vacuum Cleaner / Deck cleaning Machines | 10 | Nos |
| Z | Foam/Coir Mattress Assorted | ~1000 | Nos |

**Market references (for this lot):**
- Mixed e-waste bulk: ₹35–55/kg (scraprates.in)
- LCD/LED TV scrap: ₹200–600/unit (dealer guides — cite source)
- Laptop scrap: ₹800–3,000/unit by tier (cite source)
- Mattress: no standard scrap rate — disposal note only

**No line says “STRONG PROFIT”.**

---

## 9. Implementation phases (after approval)

| Phase | Work | Output |
|-------|------|--------|
| **1** | New schema `archive_v1.json` — strip P&L fields | `schemas/archive_v1.schema.json` |
| **2** | Tender parser: full item extraction + page map | `gem_tender_parser.py` |
| **3** | Market rate card + tag matcher (no math) | `gem_market_rates.json` + `gem_rate_matcher.py` |
| **4** | Re-extract **31705** with full item lists (all 24 lines in 2A) | `02_auction_31705_archive.json` |
| **5** | New HTML template `archive_report.html.j2` | Replace P&L dashboard for 31705 |
| **6** | Redeploy `/gem-reports/auctions/31705/` | Live link |
| **7** | Re-do **34458** (auction #1) as second reference | 13 lots, full OCR items |
| **8** | Hub update — informational columns only | |
| **9** | Remaining 61 auctions | 2–3 per day |

### Deprecate (do not delete yet, stop using in UI)
- `cost_engine.py` scenarios / verdicts
- Verdict badges, waterfall, P(Success), confidence meters
- `reuse_value_inr` guesses

---

## 10. Quality checklist (per auction before publish)

- [ ] Lot count = GeM rules count = result row count
- [ ] Every GeM result lot has a tender item list
- [ ] Every item has description + qty + unit from document
- [ ] Every item has `evidence.page_image`
- [ ] H1 matches GeM result to the rupee
- [ ] Market rates have URL + date (or explicit “no standard rate”)
- [ ] **Zero** profit/loss/margin fields in published JSON/HTML
- [ ] User can read Lot 2A items without opening PDF (but PDF linked)

---

## 11. Approval

| # | Decision |
|---|----------|
| A | Drop P&L / verdict / scenario UI entirely |
| B | Lot → item structure with verbatim tender descriptions |
| C | H1 block per lot from GeM only |
| D | Market rates as cited reference ranges — no calculations |
| E | Rebuild 31705 first, then 34458 |
| F | Keep `/gem-reports/` hosting path |

---

## 12. Why the old analysis failed (for the record)

1. **Collapsed items** — Lot 2A stored as “700 PCs + 500 TVs + misc” instead of 24 tender lines  
2. **reuse_value_inr** — invented ₹ for cranes, genies, forklifts with no document basis  
3. **quality_factor / scenarios** — opaque multipliers producing fake “PROFIT”  
4. **Portfolio rollup** — summed incompatible lots into one misleading +7.6%  
5. **Skipped OCR QA** — page 2 lot headers mangled (`LOT) NO`) but items not fully enumerated  

The v3 archive fixes this by **showing what the tender actually says**, then **H1**, then **published market ranges** — nothing more.

---

*Plan v3 — Informational Archive. Approve §11 to start Phase 1 on auction 31705.*
