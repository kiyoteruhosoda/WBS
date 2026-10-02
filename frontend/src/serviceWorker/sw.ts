// WBS の Service Worker（task #192・ADR-0028）。`/sw.js` として焼かれる（vite.config.ts の serviceWorkerShell）。
//
// - 持つのは画面の殻（index.html・ハッシュ付きの assets・アイコンなど）だけ。データは持たない
//   （データは画面が読み、取れなければ「オフラインです」を出す。打刻は画面が端末に溜める）
// - 画面の遷移には殻の index.html を返す。オフラインでも画面が開く
// - `/api/*`・`/app/*`・`/.well-known/*` には手を出さない（requestRoutes.ts）
// - 新しい版は**待たせておく**。画面の「読み込み直す」で SKIP_WAITING が来たら有効にする（雛形の ADR-0035 と同じ）
//
// ⚠ このファイルは画面の tsconfig から外し、tsconfig.sw.json（WebWorker の型）で検査する。
// ⚠ 読んでよいのは requestRoutes.ts だけ（画面の束と共有にしない）。

import {
  SKIP_WAITING_MESSAGE,
  isShellWorthy,
  routeOf,
  shellCacheName,
  staleShellCaches,
} from './requestRoutes';

declare const self: ServiceWorkerGlobalScope;

/** 焼くときに、殻の一覧と、その中身から作った版が書き込まれる */
declare const __WBS_SHELL__: { version: string; urls: string[] };

const SHELL = __WBS_SHELL__;
const CACHE_NAME = shellCacheName(SHELL.version);
const SHELL_PAGE = '/index.html';

/**
 * 殻を 1 つずつ取って入れる。⚠ `cache.addAll` は使わない —— 1 つでも取れないと install ごと落ち、
 * Service Worker が登録されない（＝ホーム画面に置けなくなる）。取れなかったものは入れずに進む。
 */
const fillShell = async (): Promise<void> => {
  const cache = await caches.open(CACHE_NAME);
  await Promise.all(SHELL.urls.map(async (url) => {
    try {
      // HTTP のキャッシュを飛ばして取り直す（古い index.html を殻に入れない）
      const response = await fetch(new Request(url, { cache: 'reload', credentials: 'same-origin' }));
      if (isShellWorthy(response)) await cache.put(url, response);
    } catch {
      // オフライン等。この版の殻には入らない（ネットワークから取れるときは取れる）
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
  if (route === 'network') return; // 手を出さない（respondWith を呼ばない）

  if (route === 'shell-page') {
    event.respondWith((async () => (await fromShell(SHELL_PAGE)) ?? fetch(request))());
    return;
  }
  event.respondWith((async () => (await fromShell(request)) ?? fetch(request))());
});
