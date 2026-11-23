// Service Worker: la aplicación abre sin conexión (estrategia cache-first
// para la interfaz; los datos viven en IndexedDB y se sincronizan por deltas).
const CACHE = "clima-firavitoba-v2";
const INTERFAZ = ["./", "index.html", "estilos.css", "app.js", "icono.svg", "manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(INTERFAZ)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // la API siempre va a la red
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then((r) => r || fetch(e.request)));
});
