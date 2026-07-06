# GitHub Actions

## refresh-and-deploy.yml (authoritative production workflow)

Scheduled (01:30 IST daily) and manual workflow that:

1. Runs unit tests
2. Runs the batch scrape pipeline (`scraper.refresh_and_deploy`)
3. Merges batches, runs QA + safety gates
4. Promotes to `web/public/data/auctions.json` (with backup)
5. Builds the Next.js static export (`pnpm run build:prod`)
6. Runs `verify-build`
7. Optionally deploys to Hostinger over SSH

Configure repository secrets listed in the root `README.md` before enabling.

## scrape-and-deploy.yml (legacy — manual only)

Legacy all-in-one MSTC workflow. **Not scheduled for production.**

- Requires `confirm_legacy_deploy=true` to deploy
- Can overwrite production with capped data if misused
- Use `refresh-and-deploy.yml` instead
