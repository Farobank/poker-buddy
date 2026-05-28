/**
 * Service worker for installability — NETWORK-FIRST.
 *
 * The buddy needs the live network (ElevenLabs SDK + the backend tunnel), so
 * offline-first is explicitly NOT a goal. We go to the network first for the
 * app shell and fall back to cache only when offline. This guarantees an
 * updated index.html always loads — a cache-first shell previously served a
 * stale UI even after deploys.
 */

const CACHE_NAME = "poker-buddy-v2";
const SHELL = ["./", "./index.html", "./manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)).catch(() => {}),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const sameOrigin = req.url.startsWith(self.location.origin);
  const isShell = sameOrigin && SHELL.some((p) => req.url.endsWith(p.replace("./", "")));

  // Navigations + same-origin shell: network-first (always fresh), cache as offline fallback.
  if (req.mode === "navigate" || isShell) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(req).then((r) => r || caches.match("./index.html"))),
    );
    return;
  }

  // Everything else (CDN scripts, the live backend/tunnel): network-only.
});
