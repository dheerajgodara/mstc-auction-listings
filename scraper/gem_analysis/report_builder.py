from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scraper.config import REPO_ROOT
from scraper.gem_analysis.pipeline import PREMIUM_JSON, BUILD_DIR, WORK

BASE_URL = "https://scrapauctionindia.com/gem-reports"


def _inr(n: float | None) -> str:
    if n is None:
        return "—"
    return f"₹{n:,.0f}"


def _verdict_class(v: str) -> str:
    return v.lower().replace(" ", "-")


def build_auction_html(analysis: dict[str, Any], out_path: Path) -> None:
    aid = analysis["auction_id"]
    sc = analysis["scenarios"]["base"]
    data_json = json.dumps(analysis, ensure_ascii=False)
    lots_rows = []
    for lot in analysis["lots"]:
        base = lot["scenarios"]["base"]
        lots_rows.append(
            f"""<tr data-verdict="{_verdict_class(base['verdict'])}" data-status="{lot.get('status','')}">
<td><strong>{lot['lot_code']}</strong></td>
<td class="desc">{lot.get('description','')[:80]}</td>
<td>{_inr(lot.get('h1_inr'))}</td>
<td class="gross">{_inr(base['gross_inr'])}</td>
<td class="costs">{_inr(base['total_costs_inr'])}</td>
<td class="net" data-val="{base['net_profit_inr']}">{_inr(base['net_profit_inr'])}</td>
<td>{base['margin_pct']:.1f}%</td>
<td><button class="badge {_verdict_class(base['verdict'])}" onclick="showVerdict('{lot['lot_code']}')">{base['verdict']}</button></td>
<td><div class="conf-bar"><span style="width:{lot.get('confidence_pct',0)}%"></span></div>{lot.get('confidence_pct',0)}%</td>
<td>{lot.get('p_success_pct',0)}%</td>
<td><span class="status-chip">{lot.get('status','')[:12]}</span></td>
</tr>"""
        )

    page_imgs = "".join(
        f'<a href="{img}" class="thumb" onclick="openLightbox(event,\'{img}\')"><img src="{img}" alt="page" loading="lazy"></a>'
        for img in analysis.get("assets", {}).get("page_images", [])
    )

    citations = "".join(
        f'<li><a href="{c["url"]}" target="_blank" rel="noopener">{c["material_class"]}</a> — {c.get("snippet","")} ({c.get("accessed","")})</li>'
        for c in analysis.get("research_citations", [])
    )

    nav_prev = analysis.get("navigation", {}).get("prev_id")
    nav_next = analysis.get("navigation", {}).get("next_id")
    nav_links = '<a href="../../index.html">Hub</a>'
    if nav_prev:
        nav_links += f' <a href="../{nav_prev}/index.html">← #{nav_prev}</a>'
    if nav_next:
        nav_links += f' <a href="../{nav_next}/index.html">#{nav_next} →</a>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GeM #{aid} — Auction Intelligence</title>
<style>
:root{{--bg:#0B0F19;--panel:#121826;--glass:rgba(18,24,38,.75);--border:rgba(255,255,255,.08);--text:#F1F5F9;--muted:#94A3B8;--gain:#22C55E;--loss:#C75050;--alert:#F59E0B;--accent:#3B82F6}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;font-feature-settings:"tnum"}}
a{{color:var(--accent);text-decoration:none}}
.topbar{{position:sticky;top:0;z-index:100;background:rgba(11,15,25,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:.75rem 1.25rem;display:flex;flex-wrap:wrap;gap:1rem;align-items:center;justify-content:space-between}}
.topbar nav{{display:flex;gap:1rem;font-size:.875rem}}
.scenario-toggle{{display:flex;gap:0;border:1px solid var(--border);border-radius:8px;overflow:hidden}}
.scenario-toggle button{{background:transparent;border:none;color:var(--muted);padding:.4rem .9rem;cursor:pointer;font-size:.8rem}}
.scenario-toggle button.active{{background:var(--accent);color:#fff}}
.wrap{{max-width:1280px;margin:0 auto;padding:1rem 1.25rem 3rem}}
.hero{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin:1rem 0}}
.kpi{{background:var(--glass);backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:12px;padding:1rem 1.25rem}}
.kpi label{{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}}
.kpi .val{{font-size:1.75rem;font-weight:700;margin-top:.25rem}}
.kpi.net .val{{font-size:2rem}}
.badge{{border:none;border-radius:999px;padding:.35rem .85rem;font-size:.7rem;font-weight:700;cursor:pointer;text-transform:uppercase}}
.badge.strong-profit,.badge.profit{{background:rgba(34,197,94,.2);color:var(--gain);box-shadow:0 0 20px rgba(34,197,94,.25)}}
.badge.marginal{{background:rgba(245,158,11,.2);color:var(--alert);box-shadow:0 0 16px rgba(245,158,11,.2)}}
.badge.loss,.badge.strong-loss{{background:rgba(199,80,80,.2);color:var(--loss);box-shadow:0 0 16px rgba(199,80,80,.2)}}
.pos{{color:var(--gain)}}.neg{{color:var(--loss)}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1.5rem 0}}
@media(max-width:768px){{.charts{{grid-template-columns:1fr}}}}
.chart-box{{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:1rem}}
.chart-box h3{{font-size:.85rem;color:var(--muted);margin-bottom:.75rem}}
canvas{{max-height:240px;width:100%!important}}
h1{{font-size:1.35rem;font-weight:600}}
.sub{{color:var(--muted);font-size:.875rem;margin-top:.25rem}}
section{{margin:2rem 0}}
section h2{{font-size:1rem;margin-bottom:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
.table-wrap{{overflow-x:auto;border:1px solid var(--border);border-radius:12px}}
table{{width:100%;border-collapse:collapse;font-size:.8rem}}
th,td{{padding:.6rem .75rem;text-align:left;border-bottom:1px solid var(--border)}}
th{{background:var(--panel);position:sticky;top:52px;cursor:pointer;user-select:none}}
tr:hover td{{background:rgba(59,130,246,.06)}}
.conf-bar{{height:4px;background:var(--border);border-radius:2px;width:60px;display:inline-block;vertical-align:middle;margin-right:4px}}
.conf-bar span{{display:block;height:100%;background:var(--accent);border-radius:2px}}
.filters{{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.75rem}}
.filters input,.filters select{{background:var(--panel);border:1px solid var(--border);color:var(--text);padding:.4rem .6rem;border-radius:6px;font-size:.8rem}}
.gallery{{display:flex;gap:.5rem;flex-wrap:wrap}}
.thumb img{{height:120px;border-radius:8px;border:1px solid var(--border)}}
.pdf-frame{{width:100%;height:480px;border:1px solid var(--border);border-radius:8px;background:#fff}}
.modal,.lightbox{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:200;align-items:center;justify-content:center;padding:1rem}}
.modal.open,.lightbox.open{{display:flex}}
.modal-box{{background:var(--panel);border:1px solid var(--border);border-radius:12px;max-width:520px;padding:1.5rem;max-height:80vh;overflow:auto}}
.lightbox img{{max-width:95vw;max-height:85vh;border-radius:8px}}
@media print{{.topbar,.filters,.scenario-toggle,button{{display:none!important}}body{{background:#fff;color:#000}}.kpi{{border:1px solid #ccc}}}}
</style>
</head>
<body>
<div class="topbar">
  <div><strong>GeM Intelligence</strong> · #{aid}</div>
  <nav>{nav_links}</nav>
  <div class="scenario-toggle" id="scenarioToggle">
    <button data-s="best">Best</button>
    <button data-s="base" class="active">Base</button>
    <button data-s="worst">Worst</button>
  </div>
  <button onclick="window.print()" style="background:var(--panel);border:1px solid var(--border);color:var(--text);padding:.4rem .8rem;border-radius:6px;cursor:pointer">Print Summary</button>
</div>
<div class="wrap">
  <h1>{analysis['meta'].get('title','')[:100]}</h1>
  <p class="sub">{analysis['meta'].get('seller','')} · {analysis['meta'].get('region','')} · {analysis['meta'].get('auction_date','')}</p>

  <div class="hero" id="kpiHero">
    <div class="kpi"><label>Total H1</label><div class="val" id="kpiH1">{_inr(analysis['summary']['total_h1_inr'])}</div></div>
    <div class="kpi"><label>Est. Gross</label><div class="val" id="kpiGross">{_inr(sc['gross_resale_inr'])}</div></div>
    <div class="kpi"><label>Net P&amp;L</label><div class="val {'pos' if sc['net_profit_inr']>=0 else 'neg'}" id="kpiNet">{_inr(sc['net_profit_inr'])}</div></div>
    <div class="kpi net"><label>Verdict</label><div><span class="badge {_verdict_class(sc['verdict'])}" id="kpiVerdict">{sc['verdict']}</span></div><div class="sub" id="kpiMargin">{sc['margin_pct']:.1f}% margin</div></div>
  </div>

  <div class="charts">
    <div class="chart-box"><h3>P&amp;L Waterfall (Base)</h3><canvas id="waterfall"></canvas></div>
    <div class="chart-box"><h3>Verdict by Lot</h3><canvas id="verdictBar"></canvas></div>
  </div>

  <section>
    <h2>Bid Strategy Table</h2>
    <div class="filters">
      <input type="search" id="searchLots" placeholder="Search lots…">
      <select id="filterVerdict"><option value="">All verdicts</option><option>STRONG LOSS</option><option>LOSS</option><option>MARGINAL</option><option>PROFIT</option></select>
    </div>
    <div class="table-wrap">
      <table id="lotsTable">
        <thead><tr>
          <th data-sort="lot">Lot</th><th>Contents</th><th data-sort="h1">H1</th><th data-sort="gross">Gross</th><th data-sort="costs">Costs</th>
          <th data-sort="net">Net</th><th data-sort="margin">Margin</th><th>Verdict</th><th>Conf.</th><th>P(Success)</th><th>Status</th>
        </tr></thead>
        <tbody>{''.join(lots_rows)}</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>Documents</h2>
    <iframe class="pdf-frame" src="docs/Tender_Document.pdf" title="Tender PDF"></iframe>
    <p style="margin-top:.5rem"><a href="docs/Tender_Document.pdf" download>Download Tender PDF</a></p>
    <div class="gallery" style="margin-top:1rem">{page_imgs}</div>
  </section>

  <section>
    <h2>Research citations</h2>
    <ul style="font-size:.85rem;color:var(--muted)">{citations}</ul>
  </section>
</div>

<div class="modal" id="verdictModal"><div class="modal-box"><button onclick="closeModal()" style="float:right;background:none;border:none;color:var(--muted);cursor:pointer">✕</button><h3 id="modalTitle"></h3><ul id="modalBody" style="margin-top:1rem;font-size:.9rem"></ul></div></div>
<div class="lightbox" id="lightbox" onclick="closeLightbox()"><img id="lightboxImg" src="" alt=""></div>

<script>
window.__ANALYSIS__ = {data_json};

function fmt(n){{return '₹'+Math.round(n).toLocaleString('en-IN');}}
let scenario='base';

function applyScenario(s){{
  scenario=s;
  document.querySelectorAll('.scenario-toggle button').forEach(b=>b.classList.toggle('active',b.dataset.s===s));
  const sc=window.__ANALYSIS__.scenarios[s];
  document.getElementById('kpiGross').textContent=fmt(sc.gross_resale_inr);
  const netEl=document.getElementById('kpiNet');
  netEl.textContent=fmt(sc.net_profit_inr);
  netEl.className='val '+(sc.net_profit_inr>=0?'pos':'neg');
  const v=document.getElementById('kpiVerdict');
  v.textContent=sc.verdict;
  v.className='badge '+sc.verdict.toLowerCase().replace(/ /g,'-');
  document.getElementById('kpiMargin').textContent=sc.margin_pct.toFixed(1)+'% margin';
  drawCharts();
}}

document.getElementById('scenarioToggle').addEventListener('click',e=>{{
  if(e.target.dataset.s) applyScenario(e.target.dataset.s);
}});

function showVerdict(code){{
  const lot=window.__ANALYSIS__.lots.find(l=>l.lot_code===code);
  document.getElementById('modalTitle').textContent='Lot '+code+' — '+lot.scenarios.base.verdict;
  document.getElementById('modalBody').innerHTML=lot.margin_drivers.map(d=>'<li>'+d+'</li>').join('');
  document.getElementById('verdictModal').classList.add('open');
}}
function closeModal(){{document.getElementById('verdictModal').classList.remove('open');}}
function openLightbox(e,src){{e.preventDefault();document.getElementById('lightboxImg').src=src;document.getElementById('lightbox').classList.add('open');}}
function closeLightbox(){{document.getElementById('lightbox').classList.remove('open');}}

function drawCharts(){{
  const lots=window.__ANALYSIS__.lots;
  const wf=document.getElementById('waterfall');
  const ctx=wf.getContext('2d');
  const dpr=window.devicePixelRatio||1;
  wf.width=wf.clientWidth*dpr;wf.height=220*dpr;ctx.scale(dpr,dpr);
  const w=wf.clientWidth,h=220;
  ctx.clearRect(0,0,w,h);
  let totalH1=0,totalGross=0,totalNet=0;
  lots.forEach(l=>{{totalH1+=l.h1_inr||0;totalGross+=l.scenarios[scenario].gross_inr;totalNet+=l.scenarios[scenario].net_profit_inr;}});
  const items=[['H1',-totalH1,'#64748b'],['Gross',totalGross,'#22c55e'],['Net',totalNet,totalNet>=0?'#22c55e':'#c75050']];
  const max=Math.max(totalH1,totalGross)*1.1;let x=40;
  const barW=(w-80)/items.length-12;
  items.forEach(([lb,val,col])=>{{
    const bh=Math.abs(val)/max*(h-50);
    const y=val>=0?h-30-bh:h-30;
    ctx.fillStyle=col;ctx.fillRect(x,y,barW,bh);
    ctx.fillStyle='#94a3b8';ctx.font='10px sans-serif';ctx.fillText(lb,x, h-12);
    ctx.fillStyle='#f1f5f9';ctx.fillText(fmt(Math.abs(val)),x,y-4);
    x+=barW+12;
  }});
  const vb=document.getElementById('verdictBar');
  const vx=vb.getContext('2d');
  vb.width=vb.clientWidth*dpr;vb.height=220*dpr;vx.scale(dpr,dpr);
  const vw=vb.clientWidth,vh=220;
  vx.clearRect(0,0,vw,vh);
  const colors={{'STRONG PROFIT':'#22c55e','PROFIT':'#4ade80','MARGINAL':'#f59e0b','LOSS':'#f87171','STRONG LOSS':'#c75050'}};
  const barH=Math.min(28,(vh-40)/lots.length);
  lots.forEach((l,i)=>{{
    const v=l.scenarios[scenario];
    const bw=(v.net_profit_inr+totalH1)/totalH1*vw*0.5;
    vx.fillStyle=colors[v.verdict]||'#64748b';
    vx.fillRect(100,i*barH+20,bw,barH-4);
    vx.fillStyle='#94a3b8';vx.font='11px sans-serif';vx.fillText(l.lot_code,10,i*barH+20+barH/2);
  }});
}}

document.getElementById('searchLots').addEventListener('input',e=>{{
  const q=e.target.value.toLowerCase();
  document.querySelectorAll('#lotsTable tbody tr').forEach(r=>{{
    r.style.display=r.textContent.toLowerCase().includes(q)?'':'none';
  }});
}});
document.getElementById('filterVerdict').addEventListener('change',e=>{{
  const v=e.target.value;
  document.querySelectorAll('#lotsTable tbody tr').forEach(r=>{{
    r.style.display=!v||r.querySelector('.badge').textContent===v?'':'none';
  }});
}});

applyScenario('base');
window.addEventListener('resize',()=>drawCharts());
</script>
</body>
</html>"""
    out_path.write_text(html, encoding="utf-8")


def build_hub_html() -> None:
    import json as _json

    data = _json.loads(PREMIUM_JSON.read_text(encoding="utf-8"))
    auctions = sorted(
        data["auctions"],
        key=lambda x: -(x.get("fresh_summary", {}).get("total_bid_inr") or 0),
    )
    rows = []
    total_h1 = 0
    analysed = 0
    total_net = 0
    for i, a in enumerate(auctions, 1):
        aid = a["auction_id"]
        h1 = a.get("fresh_summary", {}).get("total_bid_inr") or 0
        total_h1 += h1
        analysis_path = WORK / "gem_premium_analysis" / f"{i:02d}_auction_{aid}.json"
        if not analysis_path.exists() and aid != "31705":
            # check by id not sequence
            for p in (WORK / "gem_premium_analysis").glob(f"*_auction_{aid}.json"):
                analysis_path = p
                break
        verdict = "—"
        net = "—"
        conf = "—"
        link = f"auctions/{aid}/index.html" if (BUILD_DIR / "auctions" / aid / "index.html").exists() else "#"
        if analysis_path.exists():
            an = _json.loads(analysis_path.read_text())
            verdict = an["scenarios"]["base"]["verdict"]
            net = an["scenarios"]["base"]["net_profit_inr"]
            total_net += net
            conf = an["summary"].get("portfolio_confidence_pct", "—")
            analysed += 1
            link = f"auctions/{aid}/index.html"
        rows.append(
            f"<tr><td>{i}</td><td><a href='{link}'>{aid}</a></td><td>{(a.get('title') or '')[:50]}</td>"
            f"<td>{_inr(h1)}</td><td class='{'neg' if isinstance(net,(int,float)) and net<0 else 'pos'}'>{_inr(net) if isinstance(net,(int,float)) else net}</td>"
            f"<td><span class='badge {_verdict_class(verdict) if verdict!='—' else ''}'>{verdict}</span></td>"
            f"<td>{conf}</td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GeM Premium Auction Intelligence Hub</title>
<style>
:root{{--bg:#0B0F19;--panel:#121826;--glass:rgba(18,24,38,.75);--border:rgba(255,255,255,.08);--text:#F1F5F9;--muted:#94A3B8;--gain:#22C55E;--loss:#C75050;--accent:#3B82F6}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);margin:0;padding:1.5rem}}
.wrap{{max-width:1200px;margin:0 auto}}
.hero{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin:1.5rem 0}}
.kpi{{background:var(--glass);backdrop-filter:blur(12px);border:1px solid var(--border);border-radius:12px;padding:1rem}}
.kpi label{{font-size:.65rem;text-transform:uppercase;color:var(--muted)}}
.kpi .val{{font-size:1.5rem;font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:.85rem;margin-top:1rem}}
th,td{{padding:.6rem;border-bottom:1px solid var(--border);text-align:left}}
th{{color:var(--muted);font-size:.7rem;text-transform:uppercase}}
a{{color:var(--accent)}}.pos{{color:var(--gain)}}.neg{{color:var(--loss)}}
.badge{{padding:.2rem .5rem;border-radius:999px;font-size:.65rem}}
.badge.strong-loss,.badge.loss{{background:rgba(199,80,80,.2);color:var(--loss)}}
.badge.marginal{{background:rgba(245,158,11,.2);color:#f59e0b}}
.badge.profit,.badge.strong-profit{{background:rgba(34,197,94,.2);color:var(--gain)}}
</style></head><body><div class="wrap">
<h1>GeM Premium Auction Intelligence</h1>
<p style="color:var(--muted)">Accepted + ≥ ₹10L · {analysed} / {len(auctions)} analysed</p>
<div class="hero">
<div class="kpi"><label>Queue H1</label><div class="val">{_inr(total_h1)}</div></div>
<div class="kpi"><label>Portfolio Net (Base)</label><div class="val {'neg' if total_net<0 else 'pos'}">{_inr(total_net)}</div></div>
<div class="kpi"><label>Analysed</label><div class="val">{analysed}/{len(auctions)}</div></div>
</div>
<table><thead><tr><th>#</th><th>ID</th><th>Title</th><th>H1</th><th>Net P&amp;L</th><th>Verdict</th><th>Confidence</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p style="margin-top:2rem;font-size:.75rem;color:var(--muted)">MSTC live site unaffected · /auctions/</p>
</div></body></html>"""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / "index.html").write_text(html, encoding="utf-8")
