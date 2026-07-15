# Pipeline ops plan — Download 2000 / Drain (Parse 100 → Deploy)

**Status:** implemented  
**Related:** `docs/PIPELINE_RUNBOOK.md`, `docs/PRODUCTION_STATUS.md`

---

## Operating model

```text
Every 6 hours (00/06/12/18 IST)
  └─ Download (cap 2000, MSTC deep work)
       · success → Pipeline Drain
       · hard fail → intra-job retry once → auto re-dispatch (+15m, +45m; max 2/slot)

Pipeline Drain (after download success, or safety cron every 6h :00 UTC)
  └─ while parse backlog remains (max 25 cycles):
       ├─ Parse (cap 100)  [retry ×3]
       └─ Deploy           [retry ×3]
```

GeM / eAuction: discover in download; live batch enrich in parse; publish via deploy (no MSTC-style raw HTML store).

---

## Workflows

| Workflow | Trigger | Role |
|----------|---------|------|
| `pipeline-download.yml` | cron 6h + manual | Cap 2000 download |
| `pipeline-download-retry.yml` | download **failure** | Fast retry (not wait 6h) |
| `pipeline-drain.yml` | download **success** + safety cron + manual | Parse 100 → Deploy loop |
| `pipeline-parse.yml` | manual only | Emergency parse |
| `pipeline-deploy.yml` | manual only | Emergency deploy |

Shared concurrency: `auction-pipeline-serial` for download, download-retry, and drain.

---

## Failure matrix

| Failure | Behavior |
|---------|----------|
| Download hard fail | Intra-job retry once (~2 min); then +15m / +45m auto re-dispatch (max 2/slot); then next 6h |
| Download retries exhausted | Telegram `download_retries_exhausted` |
| Partial download crash | Mid-run ledger push every 50 ok |
| Parse fail in drain | Retry ×3; no deploy; `drain_stopped` |
| Deploy fail in drain | Retry ×3; no next parse; `drain_stopped` |
| Per-auction fail ×5 | `blocked` until manual unblock |

---

## Storage

| Asset | Path |
|-------|------|
| Raw HTML | `{domain}/auction_pipeline/raw/...` |
| Ledger | `{domain}/auction_pipeline/pipeline_ledger.json` |
| Download retry state | `{domain}/auction_pipeline/download_retry_state.json` |
| Last deploy fingerprint | `{domain}/auction_pipeline/last_deploy.json` |
| Public media | `…/public_html/auctions/{pdfs,docs,thumbs}` |
