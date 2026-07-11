/** Canonical production domain (no trailing slash). */
export const SITE_ROOT_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://scrapauctionindia.com"
).replace(
  /\/$/,
  "",
); /** App base path without trailing slash (e.g. `/auctions`). */
export function siteBasePath(): string {
  return (process.env.NEXT_PUBLIC_BASE_PATH || "/auctions").replace(/\/$/, "");
} /** Full public app URL with trailing slash (e.g. `https://scrapauctionindia.com/auctions/`). */
export const SITE_BASE_URL = `${SITE_ROOT_URL}${siteBasePath()}/`; /** * Build an absolute URL on the production site. * Accepts paths relative to the app root (`/mstc/582972/`) or including base path (`/auctions/mstc/582972/`). */
export function absoluteUrl(path: string): string {
  const trimmed = path.trim();
  if (!trimmed) return SITE_BASE_URL;
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    return trimmed.endsWith("/") ? trimmed : `${trimmed}/`;
  }
  const base = siteBasePath();
  let relative = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  if (base && relative.startsWith(`${base}/`)) {
    relative = relative.slice(base.length) || "/";
  }
  if (!relative.startsWith("/")) relative = `/${relative}`;
  if (!relative.endsWith("/")) relative = `${relative}/`;
  return `${SITE_ROOT_URL}${base}${relative}`;
}
