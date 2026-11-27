// Service worker : permet d'installer l'application et de l'ouvrir même sans réseau.
// Toujours le réseau d'abord (pour les données à jour), la copie locale seulement en secours.
const CACHE = "bot-trading-v6";
const BASE = ["./", "./index.html", "./ia.html", "./elan.html", "./theme.css", "./nav.js", "./manifest.webmanifest", "./icone-v3-192.png", "./icone-v3-512.png", "./apple-touch-icon-v3.png", "./lib/lightweight-charts.js"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(BASE))); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(k => Promise.all(k.filter(n => n !== CACHE).map(n => caches.delete(n)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  e.respondWith(
    fetch(e.request).then(r => {
      if (r.ok && !url.pathname.endsWith(".json")) { const copie = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copie)); }
      return r;
    }).catch(() => caches.match(e.request, { ignoreSearch: true }))
  );
});
