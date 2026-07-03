# GitHub Actions

## scrape-and-deploy.yml

Scheduled and manual workflow that:

1. Runs the Python scraper (`scraper.main`)
2. Builds the Next.js static export (`web/out/`)
3. Deploys to Hostinger over SSH (`scraper.deploy`)

Configure repository secrets listed in the root `README.md` before enabling.
