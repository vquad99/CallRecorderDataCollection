// The application's service worker (PWA-004, PWA-005, PWA-006; D-110). The build puts a line
// `const BUILD = "...";` before this text and writes the result as /sw.js, so every release has
// a different file and the browser sees that there is a new version.
//
// What it does, and nothing more:
// - keeps the built files under /assets/ (their names change whenever their content does) and
//   the offline page, so the application starts fast and can say "You are offline";
// - a page that cannot be fetched gets the offline page.
// What it never touches: anything under /api/ or /health/, anything that is not a GET, anything
// from another address (recordings in storage). Nothing a person sees after signing in is kept.
const CACHE = `ccp-static-${BUILD}`;
const OFFLINE = ["/offline.html", "/offline.css", "/icon-192.png", "/favicon.svg"];

self.addEventListener("install", (event) => {
  // No skipWaiting here: the page asks for it when the person clicks "Reload".
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(OFFLINE)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("ccp-static-") && k !== CACHE)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "skip-waiting") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/health/")) return;

  if (request.mode === "navigate") {
    // Always the server's page; without a connection, the offline page.
    event.respondWith(
      fetch(request).catch(() =>
        caches.match("/offline.html").then((page) => page ?? Response.error()),
      ),
    );
    return;
  }
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const kept = await cache.match(request);
        if (kept) return kept;
        const fresh = await fetch(request);
        if (fresh.ok) await cache.put(request, fresh.clone());
        return fresh;
      }),
    );
    return;
  }
  if (OFFLINE.includes(url.pathname)) {
    event.respondWith(
      fetch(request).catch(() => caches.match(request).then((r) => r ?? Response.error())),
    );
  }
});
