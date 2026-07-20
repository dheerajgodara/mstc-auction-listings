# Cloudflare R2 durable PDF/docs/thumbs store (canonical CDN)

Media durability is **R2-only**. Public origin:

`https://files.csmg.in/{pdfs|docs|thumbs}/...`

Set `R2_PUBLIC_BASE_URL` to the custom domain attached to the bucket
(must match Cloudflare R2 → Custom Domains). Do **not** use `*.r2.dev` in production.

Hostinger is **not** used for media mirrors. It remains for:
- website/app deploy (HTML/JSON)
- private `auction_pipeline/` ledger + raw HTML (until migrated)

## Secrets (GitHub Actions + `/etc/mstc-pipeline.env`)

| Variable | Purpose |
|----------|---------|
| `R2_ACCOUNT_ID` | Cloudflare account id (builds endpoint if `R2_ENDPOINT_URL` unset) |
| `R2_ACCESS_KEY_ID` | R2 API token access key |
| `R2_SECRET_ACCESS_KEY` | R2 API token secret |
| `R2_BUCKET` | Bucket name (`scrapauction-pdfs`) |
| `R2_ENDPOINT_URL` | Optional `https://<account>.r2.cloudflarestorage.com` |
| `R2_PUBLIC_BASE_URL` | **`https://files.csmg.in`** |
| `MEDIA_R2_ONLY` | Default `1` — skip Hostinger media rsync |

Install: `pip install boto3` (listed in `requirements.txt`).

## Custom domain setup

1. Cloudflare dashboard → R2 → bucket → Settings → Custom Domains
2. Connect `files.csmg.in` (zone must be on the same Cloudflare account)
3. Wait until status is **Active**
4. Set GitHub secret `R2_PUBLIC_BASE_URL=https://files.csmg.in`
5. Prefer disabling the `r2.dev` public development URL for production traffic

## Smoke test

```bash
R2_PUBLIC_BASE_URL=https://files.csmg.in PYTHONPATH=. python - <<'PY'
from scraper.object_store import verify_public_object_url
assert verify_public_object_url("https://files.csmg.in/robots.txt")
print("CDN OK")
PY
```

With API keys configured, also:

```bash
PYTHONPATH=. python -m scraper.r2_smoke_test
```

## Pipeline behavior

1. **Download** — portal fetch → local stage → R2 upload + CDN verify → `download=done` (`object_doc_url`)
2. **Publish media** — drains `fetched_local` → R2 only
3. **Parse** — HTTP-fetches catalogue PDFs from CDN/R2 (no Hostinger media pull)
4. **Derived media** — docs/thumbs uploaded to R2 via `push_public_media`
5. **Build** — exports absolute CDN URLs in `pdf_url` / lot media fields

## Backfill legacy Hostinger media

```bash
PYTHONPATH=. python -m scraper.media_backfill_r2 --limit 500
PYTHONPATH=. python -m scraper.media_backfill_r2 --rewrite-ledger --pull-ledger --push-ledger
PYTHONPATH=. python -m scraper.media_backfill_r2 --rewrite-export
```

Or run GitHub Action **Pipeline Media Backfill (R2 CDN)** (`pipeline-media-backfill-r2.yml`).

## Frontend

Optional `NEXT_PUBLIC_MEDIA_CDN_HOST` (hostname only). Default is `files.csmg.in`.
