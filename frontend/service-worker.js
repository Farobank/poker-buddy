/**
 * Minimal service worker for installability.
 *
 * Strategy: cache the app shell on install; for everything else, go to the
 * network (we depend on the ConvAI widget script and the live tunnel). The
 * point of the SW is to satisfy iOS's "installable web app" requirements;
 * offline-first is explicitly NOT a goal — the buddy needs the live LLM.
 */

const CACHE_NAME = "poker-buddy-v1";
const SHELL = ["./", "./index.html", "./manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)),
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

  // Same-origin shell requests: cache-first.
  if (req.url.startsWith(self.location.origin) && SHELL.some((p) => req.url.endsWith(p.replace("./", "")))) {
    event.respondWith(
      caches.match(req).then((res) => res || fetch(req)),
    );
    return;
  }

  // Everything else: network-only (we need the live widget + tunnel).
});
