const CACHE = "auction-app-shell-v2";

function scopePath(path = "") {
  const scope = new URL(self.registration.scope);
  const base = scope.pathname.endsWith("/") ? scope.pathname : `${scope.pathname}/`;
  return `${base}${path}`.replace(/\/{2,}/g, "/");
}

const SHELL = [
  scopePath(),
  scopePath("index.html"),
  scopePath("app/"),
  scopePath("watchlist/"),
  scopePath("saved/"),
  scopePath("account/"),
  scopePath("pricing/"),
  scopePath("manifest.webmanifest"),
  scopePath("app-icon.svg"),
  scopePath("app-maskable-icon.svg"),
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL).catch(() => undefined)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (
    url.pathname.includes("/data/auctions-data.js") ||
    url.pathname.includes("/data/auctions.json") ||
    url.pathname.includes("/data/import-history.json")
  ) {
    event.respondWith(fetch(event.request, { cache: "no-store" }));
    return;
  }
  if (url.pathname.endsWith("/data/export-meta.json")) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
          return res;
        })
        .catch(() => caches.match(event.request)),
    );
    return;
  }
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(
        () => caches.match(scopePath("index.html")) ?? caches.match(scopePath()) ?? Response.error(),
      ),
    );
  }
});
