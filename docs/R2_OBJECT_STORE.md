# Cloudflare R2 durable PDF store (Phase C)

When configured, the publish lane uploads to R2 first (HTTP API with connect/read timeouts),
then mirrors to Hostinger `public_html` for the live site.

## Secrets (GitHub Actions + `/etc/mstc-pipeline.env`)

| Variable | Purpose |
|----------|---------|
| `R2_ACCOUNT_ID` | Cloudflare account id (builds endpoint if `R2_ENDPOINT_URL` unset) |
| `R2_ACCESS_KEY_ID` | R2 API token access key |
| `R2_SECRET_ACCESS_KEY` | R2 API token secret |
| `R2_BUCKET` | Bucket name |
| `R2_ENDPOINT_URL` | Optional override `https://<account>.r2.cloudflarestorage.com` |
| `R2_PUBLIC_BASE_URL` | Public/custom domain base for `object_doc_url` |

Install: `pip install boto3` (listed in `requirements.txt`).

If R2 env is empty, publish behaves as Hostinger-only (Phase A/B).
