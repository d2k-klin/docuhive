import { flush } from "/capture-queue.js";
const CACHE = "docuhive-capture-v1";
self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const response = await fetch("/capture");
    if (!response.ok || response.redirected) throw new Error("Capture shell unavailable");
    await cache.put("/capture", response.clone());
    const html = await response.text();
    const assets = [...html.matchAll(/(?:src|href)="([^" ]+)"/g)]
      .map(match => match[1].replaceAll("&amp;", "&"))
      .filter(url => url.startsWith("/_next/static/"));
    await cache.addAll([...new Set([...assets, "/capture-queue.js"])]);
    await self.skipWaiting();
  })());
});
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key.startsWith("docuhive-capture-") && key !== CACHE) await caches.delete(key);
    await self.clients.claim();
  })());
});
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== "GET") return;
  if (event.request.mode === "navigate" && url.pathname === "/capture") {
    event.respondWith(fetch(event.request).catch(() => caches.match("/capture")));
  } else if (url.pathname.startsWith("/_next/static/") || url.pathname === "/capture-queue.js") {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
self.addEventListener("sync", event => {
  if (event.tag === "docuhive-uploads") event.waitUntil(flush());
});
