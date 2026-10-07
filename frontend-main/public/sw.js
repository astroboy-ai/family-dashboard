/*
 * FamilyOS service worker.
 *
 * Two jobs only: make the app shell open when the network is down, and keep
 * static assets from being re-downloaded. It deliberately does NOT touch the
 * API.
 *
 * Why /api/ is excluded: this is a private, authenticated app. A cached API
 * response would show one member stale or another member's data, and an
 * offline write would silently vanish. Every API call goes straight to the
 * network and fails loudly if the network is down — which is the honest
 * behaviour.
 *
 * Navigations are network-first for the same reason: a cached HTML page could
 * be the logged-out or wrong-account view. The cache is only a fallback for
 * when the network is genuinely unavailable.
 */

const VERSION = "v1";
const SHELL_CACHE = `familyos-shell-${VERSION}`;
const ASSET_CACHE = `familyos-assets-${VERSION}`;

/* Pre-cached at install so the app opens offline on first use. */
const SHELL_URLS = [
  "/offline.html",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      // addAll rejects the whole install if any single URL fails, which would
      // leave the worker stuck; add them individually instead.
      .then((cache) => Promise.all(SHELL_URLS.map((url) => cache.add(url).catch(() => undefined))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== SHELL_CACHE && key !== ASSET_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

/** Only same-origin http(s) requests are ours to handle. */
function isHandlable(request, url) {
  if (request.method !== "GET") return false;
  if (url.origin !== self.location.origin) return false;
  if (!url.protocol.startsWith("http")) return false;
  return true;
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  if (!isHandlable(event.request, url)) return;

  // Never intercept the API: always live, never cached.
  if (url.pathname.startsWith("/api/")) return;

  // Next.js serves hashed, immutable build output — safe to serve from cache
  // and never revalidate.
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.match(event.request).then(
        (cached) =>
          cached ||
          fetch(event.request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(ASSET_CACHE).then((cache) => cache.put(event.request, copy));
            }
            return response;
          }),
      ),
    );
    return;
  }

  // Icons and the manifest rarely change; serve from cache and refresh behind
  // the scenes.
  if (/\.(png|svg|ico|webmanifest)$/.test(url.pathname)) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        const network = fetch(event.request)
          .then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(SHELL_CACHE).then((cache) => cache.put(event.request, copy));
            }
            return response;
          })
          .catch(() => cached);
        return cached || network;
      }),
    );
    return;
  }

  // Navigations: live first, cache only as an offline fallback.
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match(event.request).then((cached) => cached || caches.match("/offline.html")),
      ),
    );
  }
});
