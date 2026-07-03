from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scraper.gem_analysis.archive_pipeline import ARCHIVE_DIR, BUILD_DIR, PREMIUM_JSON


def _format_rate(r: dict[str, Any]) -> str:
    if r.get("unit") == "note":
        return r.get("note") or "No standard rate"
    low, high = r.get("rate_low"), r.get("rate_high")
    unit = r.get("unit", "")
    if low is not None and high is not None:
        return f"₹{low:,.0f}–₹{high:,.0f} {unit}"
    return "—"


def _rate_rows_html(rates: list[dict[str, Any]]) -> str:
    if not rates:
        return '<p class="muted">No standard market rate mapped — see equipment/disposal notes.</p>'
    rows = []
    for r in rates:
        src = r.get("sources") or []
        link = ""
        if src:
            link = f'<a href="{src[0]["url"]}" target="_blank" rel="noopener">{src[0].get("quote", "Source")[:60]}</a>'
        elif r.get("note"):
            link = r["note"]
        rows.append(
            f"<tr><td>{r.get('label','')}</td>"
            f"<td>{_format_rate(r)}</td>"
            f"<td>{r.get('region','')}</td>"
            f"<td class='src'>{link}</td></tr>"
        )
    return (
        "<table class='rate-mini'><thead><tr><th>Rate type</th><th>Range</th><th>Region</th><th>Source</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _md_to_html(text: str) -> str:
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _item_rows(lot: dict[str, Any]) -> str:
    rows = []
    for item in lot.get("items") or []:
        qty = item.get("quantity")
        unit = item.get("unit", "")
        qnote = item.get("quantity_notes")
        qty_disp = f"{qty:,}" if isinstance(qty, (int, float)) and qty == int(qty) else str(qty)
        if qnote:
            qty_disp += f" ({qnote})"
        ev = item.get("evidence") or {}
        page_link = ""
        if ev.get("page_image"):
            page_link = f'<a href="#" onclick="openLb(\'{ev["page_image"]}\');return false">Page {ev.get("page_no","")}</a>'
        plain = _md_to_html(item.get("plain_language") or "")
        tender_line = ev.get("ocr_excerpt") or item.get("description_verbatim") or ""
        rates_html = _rate_rows_html(item.get("market_rates") or [])
        title = item.get("title") or item.get("description_verbatim", "")
        rows.append(
            f"""<tr class="item-row">
<td class="code">{item.get('sub_code','')}</td>
<td class="desc" colspan="3">
  <div class="item-title">{title}</div>
  <div class="item-qty"><strong>{qty_disp}</strong> {unit}</div>
  <p class="item-plain">{plain}</p>
  <p class="tender-quote">Tender says: <em>{tender_line}</em> · {page_link}</p>
</td>
</tr>
<tr class="rates-row"><td colspan="4"><div class="rates-block"><strong>Market rate reference</strong> (indicative only — not a valuation){rates_html}</div></td></tr>"""
        )
    return "".join(rows)


def _about_auction(meta: dict[str, Any]) -> str:
    region = meta.get("region") or "India"
    loc = meta.get("location_summary") or region
    date = meta.get("auction_date") or "see GeM notice"
    seller = meta.get("seller") or "Government seller"
    return (
        f"This archive covers a <strong>government forward auction</strong> ({seller}). "
        f"Material is located at <strong>{loc}</strong>. Auction window: <strong>{date}</strong>. "
        f"Goods are sold <strong>“as is, where is”</strong> — condition and completeness are not guaranteed. "
        f"Below, each <strong>lot</strong> lists what the tender/catalogue says, plain-English explanations, "
        f"the <strong>winning bid (H1)</strong> from GeM, and <strong>indicative market rates</strong> where mapped."
    )


def _docs_section(assets: dict[str, Any]) -> str:
    pdfs = assets.get("pdfs") or []
    primary = assets.get("primary_pdf")
    if pdfs and isinstance(pdfs[0], str):
        primary = primary or pdfs[0]
        pdf_links = "".join(
            f'<p style="margin-top:.35rem;font-size:.85rem"><a href="{p}" download>Download {Path(p).name}</a></p>'
            for p in pdfs
        )
        iframe = (
            f'<iframe class="pdf-frame" src="{primary}" title="Source PDF"></iframe>'
            if primary
            else '<p class="muted">No PDF available for this auction.</p>'
        )
    elif pdfs:
        primary = primary or next((p["path"] for p in pdfs if p.get("primary")), pdfs[0]["path"])
        iframe = f'<iframe class="pdf-frame" src="{primary}" title="Source PDF"></iframe>'
        pdf_links = "".join(
            f'<p style="margin-top:.35rem;font-size:.85rem">'
            f'<a href="{p["path"]}" download>{p.get("label", p["path"])}</a>'
            f'{" · primary" if p.get("primary") else ""}</p>'
            for p in pdfs
        )
    else:
        iframe = '<p class="muted">No PDF documents were attached on GeM for this auction.</p>'
        pdf_links = ""

    thumbs = "".join(
        f'<a href="{img}" onclick="openLb(\'{img}\');return false"><img src="{img}" alt="" loading="lazy"></a>'
        for img in assets.get("page_images") or []
    )
    gallery = (
        f'<div class="gallery">{thumbs}</div>'
        if thumbs
        else '<p class="muted" style="margin-top:.5rem">Page scans will appear here when tender PDFs are available.</p>'
    )
    return f"""
  <section class="docs">
    <h2 style="font-size:.8rem;text-transform:uppercase;color:var(--muted);margin-bottom:.5rem">Source documents</h2>
    {iframe}
    {pdf_links}
    <h3 style="font-size:.75rem;text-transform:uppercase;color:var(--muted);margin:1.25rem 0 .5rem">Tender page scans (click to enlarge)</h3>
    {gallery}
  </section>"""


def _lot_section(lot: dict[str, Any]) -> str:
    res = lot.get("result") or {}
    reg = lot.get("regulatory_notes")
    reg_html = f'<p class="regulatory">⚠ {reg}</p>' if reg else ""
    pages = ", ".join(f"page {p}" for p in lot.get("document_pages") or [])
    status = res.get("acceptance_status") or "—"
    status_cls = "accepted" if status == "Accepted" else "pending" if "Pending" in status else ""
    summary = _md_to_html(lot.get("lot_summary_plain") or "")

    opn = lot.get("opening_price_inr")
    emd = lot.get("pre_bid_emd_inr")
    opn_disp = f"₹{opn:,.0f}" if opn is not None else "—"
    emd_disp = f"₹{emd:,.0f}" if emd is not None else "—"

    return f"""
<section class="lot-section" id="lot-{lot['lot_code']}">
  <div class="lot-header">
    <h2>LOT {lot['lot_code']}</h2>
    <span class="loc">{lot.get('location','')}</span>
  </div>
  <div class="lot-summary-box">
    <h3>What is in this lot?</h3>
    <p>{summary}</p>
  </div>
  <div class="lot-meta">
    <div><label>Opening price</label><span>{opn_disp}</span></div>
    <div><label>Pre-bid EMD</label><span>{emd_disp}</span></div>
    <div><label>How it is sold</label><span>{lot.get('unit_of_sale','')}</span></div>
    <div><label>Contact</label><span>{lot.get('contact','')}</span></div>
    <div><label>Source pages</label><span>{pages}</span></div>
    <div><label>Line items</label><span>{lot.get('item_count',0)}</span></div>
  </div>
  {reg_html}
  <div class="result-box">
    <h3>Winning bid (H1) from GeM</h3>
    <div class="result-grid">
      <div class="h1">{res.get('h1_display','—')}</div>
      <div><label>Winning bidder</label>{res.get('bidder','—')}</div>
      <div><label>Bid placed at</label>{res.get('bid_datetime','—')}</div>
      <div><label>Sale status</label><span class="status {status_cls}">{status}</span></div>
    </div>
    <p class="h1-note">This is the highest bid recorded on GeM. “Accepted” means the seller confirmed the sale; “Pending” means payment/charges not yet cleared.</p>
  </div>
  <h3 class="items-title">Every item in this lot (from tender document)</h3>
  <div class="table-wrap">
    <table class="items-table">
      <thead><tr><th></th><th colspan="3">Item detail</th></tr></thead>
      <tbody>{_item_rows(lot)}</tbody>
    </table>
  </div>
</section>"""


def build_archive_html(archive: dict[str, Any], out_path: Path) -> None:
    aid = archive["auction_id"]
    meta = archive["meta"]
    summary = archive["summary"]
    lots_html = "".join(_lot_section(lot) for lot in archive["lots"])
    lot_nav = " · ".join(
        f'<a href="#lot-{lot["lot_code"]}">{lot["lot_code"]}</a>' for lot in archive["lots"]
    )

    appendix_rows = ""
    for e in archive.get("rate_appendix") or []:
        srcs = "; ".join(
            f'<a href="{s["url"]}" target="_blank">{s.get("accessed","")}</a>' for s in (e.get("sources") or [])
        )
        appendix_rows += (
            f"<tr><td>{e.get('label')}</td><td>{_format_rate(e)}</td>"
            f"<td>{e.get('region')}</td><td>{srcs or (e.get('note') or '—')}</td></tr>"
        )

    disclaimer = "".join(f"<li>{d}</li>" for d in archive.get("disclaimer") or [])
    nav = archive.get("navigation") or {}
    nav_html = '<a href="../../index.html">Hub</a>'
    if nav.get("prev_id"):
        nav_html += f' <a href="../{nav["prev_id"]}/index.html">← #{nav["prev_id"]}</a>'
    if nav.get("next_id"):
        nav_html += f' <a href="../{nav["next_id"]}/index.html">#{nav["next_id"]} →</a>'

    thumbs = "".join(
        f'<a href="{img}" onclick="openLb(\'{img}\');return false"><img src="{img}" alt="" loading="lazy"></a>'
        for img in archive.get("assets", {}).get("page_images", [])
    )

    data_json = json.dumps(archive, ensure_ascii=False)
    about = _about_auction(meta)
    docs_html = _docs_section(archive.get("assets") or {})
    sub_line = f"{meta.get('region','')} · {meta.get('auction_date','')}".strip(" ·")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GeM #{aid} — Lot Archive</title>
<style>
:root{{--bg:#0B0F19;--panel:#121826;--border:rgba(255,255,255,.08);--text:#F1F5F9;--muted:#94A3B8;--accent:#3B82F6;--gain:#22C55E;--alert:#F59E0B}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.55;font-feature-settings:"tnum"}}
a{{color:var(--accent)}}
.topbar{{position:sticky;top:0;z-index:50;background:rgba(11,15,25,.95);backdrop-filter:blur(10px);border-bottom:1px solid var(--border);padding:.75rem 1.25rem;display:flex;flex-wrap:wrap;gap:1rem;align-items:center;justify-content:space-between}}
.wrap{{max-width:1100px;margin:0 auto;padding:1rem 1.25rem 3rem}}
h1{{font-size:1.25rem;font-weight:600}}
.sub{{color:var(--muted);font-size:.875rem;margin:.5rem 0 1rem}}
.summary-bar{{display:flex;flex-wrap:wrap;gap:1.5rem;padding:1rem;background:var(--panel);border:1px solid var(--border);border-radius:10px;margin-bottom:1rem;font-size:.9rem}}
.summary-bar strong{{color:var(--text)}}
.lot-nav{{position:sticky;top:52px;background:var(--bg);padding:.75rem 0;border-bottom:1px solid var(--border);margin-bottom:1.5rem;font-size:.9rem;z-index:40}}
.lot-section{{margin:2.5rem 0;padding-bottom:2rem;border-bottom:1px solid var(--border)}}
.lot-header{{display:flex;align-items:baseline;gap:1rem;margin-bottom:.75rem}}
.lot-header h2{{font-size:1.35rem;color:var(--accent)}}
.loc{{color:var(--muted);font-size:.85rem}}
.lot-meta{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:.75rem;margin-bottom:1rem;font-size:.8rem}}
.lot-meta label{{display:block;color:var(--muted);font-size:.65rem;text-transform:uppercase}}
.regulatory{{background:rgba(245,158,11,.1);border-left:3px solid var(--alert);padding:.6rem .8rem;font-size:.85rem;margin:.75rem 0}}
.result-box{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:1rem;margin:1rem 0}}
.result-box h3{{font-size:.75rem;text-transform:uppercase;color:var(--muted);margin-bottom:.5rem}}
.h1{{font-size:1.75rem;font-weight:700;color:var(--gain)}}
.result-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:.75rem;margin-top:.5rem;font-size:.85rem}}
.result-grid label{{display:block;color:var(--muted);font-size:.65rem}}
.status.accepted{{color:var(--gain)}}.status.pending{{color:var(--alert)}}
.lot-summary-box{{background:rgba(59,130,246,.08);border:1px solid rgba(59,130,246,.25);border-radius:10px;padding:1rem 1.25rem;margin:1rem 0}}
.lot-summary-box h3{{font-size:.8rem;text-transform:uppercase;color:var(--accent);margin-bottom:.5rem}}
.lot-summary-box p{{font-size:.95rem;line-height:1.65;color:var(--text)}}
.item-title{{font-weight:600;font-size:.95rem;margin-bottom:.2rem}}
.item-qty{{font-size:.85rem;color:var(--accent);margin-bottom:.5rem}}
.item-plain{{font-size:.9rem;line-height:1.6;color:var(--text);margin:.5rem 0}}
.tender-quote{{font-size:.75rem;color:var(--muted);margin-top:.35rem}}
.h1-note{{font-size:.78rem;color:var(--muted);margin-top:.75rem;line-height:1.5}}
.items-title{{font-size:.8rem;text-transform:uppercase;color:var(--muted);margin:1.25rem 0 .5rem}}
.table-wrap{{overflow-x:auto;border:1px solid var(--border);border-radius:8px}}
.items-table{{width:100%;border-collapse:collapse;font-size:.82rem}}
.items-table th,.items-table td{{padding:.5rem .65rem;text-align:left;border-bottom:1px solid var(--border)}}
.items-table th{{background:var(--panel);font-size:.7rem;text-transform:uppercase;color:var(--muted)}}
.item-row td.code{{font-weight:700;width:2rem;color:var(--accent)}}
.item-row td.qty,.item-row td.unit{{white-space:nowrap}}
.rates-row td{{background:rgba(59,130,246,.04);padding:.5rem .65rem .75rem}}
.rates-block{{font-size:.78rem}}
.rate-mini{{width:100%;margin-top:.35rem;font-size:.75rem}}
.rate-mini td,.rate-mini th{{padding:.25rem .4rem;border:1px solid var(--border)}}
.muted{{color:var(--muted);font-size:.8rem}}
.docs{{margin:1.5rem 0}}
.pdf-frame{{width:100%;height:420px;border:1px solid var(--border);border-radius:8px;background:#fff}}
.gallery{{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.75rem}}
.gallery img{{height:100px;border-radius:6px;border:1px solid var(--border);cursor:pointer}}
.lightbox{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.9);z-index:200;align-items:center;justify-content:center}}
.lightbox.open{{display:flex}}
.lightbox img{{max-width:95vw;max-height:90vh}}
@media print{{.topbar,.lot-nav,.pdf-frame,.gallery{{display:none}}body{{background:#fff;color:#000}}}}
</style>
</head>
<body>
<div class="topbar">
  <strong>GeM Lot Archive</strong>
  <nav>{nav_html}</nav>
  <button onclick="window.print()" style="background:var(--panel);border:1px solid var(--border);color:var(--text);padding:.35rem .7rem;border-radius:6px;cursor:pointer">Print</button>
</div>
<div class="wrap">
  <h1>{meta.get('title','')[:120]}</h1>
  <p class="sub">{sub_line}</p>
  <p class="sub">Reference: {meta.get('reference_no','')} · Seller: {meta.get('seller','')}</p>
  <p class="sub"><a href="{meta.get('gem_urls',{}).get('notice','')}" target="_blank">GeM Notice</a> · <a href="{meta.get('gem_urls',{}).get('result','')}" target="_blank">GeM Result</a></p>
  <div class="lot-summary-box" style="margin-top:1rem">
    <h3>About this auction</h3>
    <p>{about}</p>
  </div>

  <div class="summary-bar">
    <div><span class="muted">Lots</span><br><strong>{summary.get('lot_count')}</strong></div>
    <div><span class="muted">Total items</span><br><strong>{summary.get('total_items')}</strong></div>
    <div><span class="muted">Total H1</span><br><strong>{summary.get('total_h1_display')}</strong></div>
    <div><span class="muted">Accepted lots</span><br><strong>{summary.get('accepted_lot_count')} / {summary.get('lot_count')}</strong></div>
    <div><span class="muted">Rates as of</span><br><strong>{meta.get('rates_as_of','')}</strong></div>
  </div>

  <div class="lot-nav">Jump: {lot_nav}</div>

  {docs_html}

  {lots_html}

  <section style="margin-top:2rem">
    <h2 style="font-size:.8rem;text-transform:uppercase;color:var(--muted);margin-bottom:.5rem">Market rate appendix (this auction)</h2>
    <div class="table-wrap">
      <table class="items-table">
        <thead><tr><th>Material</th><th>Reference range</th><th>Region</th><th>Source</th></tr></thead>
        <tbody>{appendix_rows}</tbody>
      </table>
    </div>
  </section>

  <section style="margin-top:1.5rem;font-size:.8rem;color:var(--muted)">
    <h2 style="font-size:.8rem;text-transform:uppercase;margin-bottom:.5rem">Disclaimer</h2>
    <ul style="padding-left:1.2rem">{disclaimer}</ul>
  </section>
</div>
<div class="lightbox" id="lb" onclick="closeLb()"><img id="lbImg" src="" alt=""></div>
<script>
function openLb(s){{document.getElementById('lbImg').src=s;document.getElementById('lb').classList.add('open');}}
function closeLb(){{document.getElementById('lb').classList.remove('open');}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeLb();}});
window.__ARCHIVE__ = {data_json};
</script>
</body>
</html>"""
    out_path.write_text(html, encoding="utf-8")


def build_hub_html() -> None:
    import json as _json

    data = _json.loads(PREMIUM_JSON.read_text(encoding="utf-8"))
    auctions = sorted(data["auctions"], key=lambda x: -(x.get("fresh_summary", {}).get("total_bid_inr") or 0))
    rows = []
    for i, a in enumerate(auctions, 1):
        aid = a["auction_id"]
        h1 = a.get("fresh_summary", {}).get("total_bid_inr") or 0
        archive_path = None
        for p in ARCHIVE_DIR.glob(f"*_auction_{aid}_archive.json"):
            archive_path = p
            break
        items = "—"
        link = "#"
        status = "pending"
        if archive_path and archive_path.exists():
            ar = _json.loads(archive_path.read_text())
            items = ar["summary"].get("total_items", "—")
            status = "✓"
            link = f"auctions/{aid}/index.html"
        elif (BUILD_DIR / "auctions" / aid / "index.html").exists():
            link = f"auctions/{aid}/index.html"
            status = "✓"
        rows.append(
            f"<tr><td>{i}</td><td><a href='{link}'>{aid}</a></td>"
            f"<td>{(a.get('title') or '')[:55]}</td>"
            f"<td>{a.get('fresh_summary',{}).get('lot_count','—')}</td>"
            f"<td>₹{h1:,.0f}</td><td>{items}</td><td>{status}</td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GeM Premium Lot Archive</title>
<style>
body{{font-family:system-ui;background:#0B0F19;color:#F1F5F9;margin:0;padding:1.5rem}}
.wrap{{max-width:1100px;margin:0 auto}}
h1{{font-size:1.35rem}}
p{{color:#94A3B8;font-size:.9rem}}
table{{width:100%;border-collapse:collapse;margin-top:1rem;font-size:.85rem}}
th,td{{padding:.6rem;border-bottom:1px solid rgba(255,255,255,.08);text-align:left}}
th{{color:#94A3B8;font-size:.7rem;text-transform:uppercase}}
a{{color:#3B82F6}}
</style></head><body><div class="wrap">
<h1>GeM Premium Lot Archive</h1>
<p>Informational catalogue: items from tender · H1 from GeM · market rate references. No P&amp;L.</p>
<table><thead><tr><th>#</th><th>ID</th><th>Title</th><th>Lots</th><th>Total H1</th><th>Items</th><th>Archive</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</div></body></html>"""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / "index.html").write_text(html, encoding="utf-8")
