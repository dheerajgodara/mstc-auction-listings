# Monitoring and Alerts

Operational monitoring for the auction listings site combines CI notifications, post-deploy HTTP checks, scheduled freshness probes, and optional external uptime monitoring.

## Layers

| Layer | Mechanism | Action on failure |
|-------|-----------|-------------------|
| CI / refresh pipeline | GitHub Actions email + `NOTIFY_WEBHOOK_URL` via `scraper/notify.py` | Investigate workflow logs; do not deploy if gates fail |
| Post-deploy HTTP | `scraper/http_verify.py` in refresh pipeline | Re-run deploy or rollback from last good export |
| Freshness | `scraper/freshness_check.py` (36h default) | Re-run `refresh-and-deploy` workflow |
| Weekly cron | `.github/workflows/freshness-check.yml` | Same as freshness failure |
| Uptime (optional) | UptimeRobot free tier | Page owner; verify Hostinger + DNS |

## Freshness check

```bash
PYTHONPATH=. python -m scraper.freshness_check \
  --base-url "https://lightcyan-camel-979846.hostingersite.com/auctions"
```

Flags:

- `--max-age-hours 36` — fail if `automation_ran_at` is older
- `--min-count 1000` — fail if export count drops below threshold
- `--warn-only` — print warnings without non-zero exit (used after deploy initially)

## UptimeRobot setup (recommended)

1. Create a free account at [UptimeRobot](https://uptimerobot.com/).
2. Add HTTP(s) monitors:
   - `https://lightcyan-camel-979846.hostingersite.com/auctions/` — keyword `auctions` optional
   - `https://lightcyan-camel-979846.hostingersite.com/auctions/data/export-meta.json` — expect JSON with `automation_ran_at`
3. Alert contacts: email + optional Slack webhook.
4. Interval: 5 minutes (free tier).

## Webhook notifications

Set `NOTIFY_WEBHOOK_URL` in GitHub Actions secrets (Slack/Discord compatible). The refresh pipeline calls `scraper/notify.py` on hard failures.

## When alerted

1. Open `/auctions/status/` — check automation time, source counts, document failures.
2. Run `PYTHONPATH=. python -m scraper.status_report --check-live`.
3. If data is stale but site is up, trigger `refresh-and-deploy` workflow manually.
4. If deploy broke the site, restore `web/public/data` from last artifact and redeploy.

## Status report CLI

```bash
PYTHONPATH=. python -m scraper.status_report --check-live
```

Includes production counts, last run, live HTTP probes, and freshness warnings when `--check-live` is set.
