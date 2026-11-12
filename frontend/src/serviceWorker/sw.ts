// WBS Service Worker (task #192, ADR-0028). Built as `/sw.js` (serviceWorkerShell in vite.config.ts).
//
// - Holds only the app shell (index.html, hashed assets, icons, etc.). No data
//   (the UI reads data and shows "offline" when it can't)
// - Navigations get the shell's index.html, so the UI opens offline too
// - `/api/*`, `/app/*` and `/.well-known/*` are not handled (requestRoutes.ts)
// - New versions are **kept waiting**, and activate when SKIP_WAITING arrives from the UI's "reload" (same as the template's ADR-0035)
// - No device notifications (Web Push). Event and time-entry notifications are sent by Scheduler and Tracker (task #543, ADR-0070)
//
// ⚠ This file is excluded from the UI tsconfig and checked with tsconfig.sw.json (WebWorker types).
// ⚠ It may import only requestRoutes.ts (no chunks shared with the UI bundle).

import {
  SKIP_WAITING_MESSAGE,
  isShellWorthy,
  routeOf,
  shellCacheName,
  staleShellCaches,
} from './requestRoutes';

declare const self: ServiceWorkerGlobalScope;

/** At build time, the shell list and a version derived from its contents are written here */
declare const __WBS_SHELL__: { version: string; urls: string[] };

const SHELL = __WBS_SHELL__;
const CACHE_NAME = shellCacheName(SHELL.version);
const SHELL_PAGE = '/index.html';

/**
 * Fetch and cache the shell one file at a time. ⚠ No `cache.addAll` —— a single failure fails the whole install
 * and the Service Worker is not registered (= can't be added to the home screen). Failed files are skipped.
 */
const fillShell = async (): Promise<void> => {
  const cache = await caches.open(CACHE_NAME);
  await Promise.all(SHELL.urls.map(async (url) => {
    try {
      // Bypass the HTTP cache (don't put a stale index.html into the shell)
      const response = await fetch(new Request(url, { cache: 'reload', credentials: 'same-origin' }));
      if (isShellWorthy(response)) await cache.put(url, response);
    } catch {
      // Offline etc. Not in this version's shell (still fetched from the network when available)
    }
  }));
};

self.addEventListener('install', (event) => {
  event.waitUntil(fillShell());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const stale = staleShellCaches(await caches.keys(), SHELL.version);
    await Promise.all(stale.map((name) => caches.delete(name)));
  })());
});

self.addEventListener('message', (event) => {
  if (event.data === SKIP_WAITING_MESSAGE) void self.skipWaiting();
});

const fromShell = async (key: string | Request): Promise<Response | undefined> => {
  const cache = await caches.open(CACHE_NAME);
  return cache.match(key);
};

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const route = routeOf({ method: request.method, url: request.url, mode: request.mode }, self.location.origin);
  if (route === 'network') return; // not handled (respondWith is not called)

  if (route === 'shell-page') {
    event.respondWith((async () => (await fromShell(SHELL_PAGE)) ?? fetch(request))());
    return;
  }
  event.respondWith((async () => (await fromShell(request)) ?? fetch(request))());
});
