// Service Worker がどの要求に手を出すか（task #192・ADR-0028）。DOM も Service Worker の型も使わない純関数だけを置く
// （Service Worker の束と試験から読む。⚠ 画面の束からは読まない——読むと束が共有になり、Service Worker が
// 別の束を import して動かなくなる。vite.config.ts の焼き方がそれを見て落とす）。
//
// 手を出すのは**画面の殻（静的ファイル）だけ**。次は素通しにする（応答を差し替えない・キャッシュしない）:
// - `/api/*` —— データ・ログインの往復（`/api/auth/*` は assay へ転送する。⚠ 転送を掴むと壊れる）・版（`/api/info`）
// - `/app/*` —— 打刻アプリ（wbstimer）のログインの戻り先 `/app/oauth2redirect`（ADR-0019）。
//   Android の App Links が受け取る URL なので、ブラウザで開かれたときもサーバの答えをそのまま見せる
// - `/.well-known/*` —— App Links の検証ファイル（assetlinks.json。中身は api が作る）
// - `/sw.js` —— Service Worker 自身（ブラウザは更新の確認で Service Worker を通さずに取るが、念のため）
// - GET 以外・よそのオリジン（Google Fonts など）

export type RequestRoute =
  /** 手を出さない（ブラウザがそのままネットワークへ） */
  | 'network'
  /** 画面の遷移。殻（index.html）を返す */
  | 'shell-page'
  /** 静的ファイル。殻にあればそれを返し、無ければネットワークへ */
  | 'shell-file';

export interface RequestFacts {
  method: string;
  url: string;
  /** Request.mode（'navigate' が画面の遷移） */
  mode: string;
}

/** 素通しにする経路の頭。どれも「その経路そのもの」か「その下」に当たる */
export const NETWORK_ONLY_PREFIXES = ['/api', '/app', '/.well-known'] as const;

const SERVICE_WORKER_PATH = '/sw.js';

const isUnder = (pathname: string, prefix: string): boolean =>
  pathname === prefix || pathname.startsWith(`${prefix}/`);

/** 要求をどう扱うか。*origin* は Service Worker のオリジン（self.location.origin）。 */
export const routeOf = (request: RequestFacts, origin: string): RequestRoute => {
  if (request.method !== 'GET') return 'network';
  const url = new URL(request.url);
  if (url.origin !== origin) return 'network';
  if (url.pathname === SERVICE_WORKER_PATH) return 'network';
  if (NETWORK_ONLY_PREFIXES.some((prefix) => isUnder(url.pathname, prefix))) return 'network';
  return request.mode === 'navigate' ? 'shell-page' : 'shell-file';
};

/** 殻のキャッシュの名前。版ごとに分け、新しい版が有効になったら古い名前を消す */
export const SHELL_CACHE_PREFIX = 'wbs-shell-';

export const shellCacheName = (version: string): string => `${SHELL_CACHE_PREFIX}${version}`;

/** 有効になった版のとき、消してよいキャッシュ（この Service Worker が作った古い版だけ） */
export const staleShellCaches = (cacheNames: readonly string[], version: string): string[] =>
  cacheNames.filter((name) => name.startsWith(SHELL_CACHE_PREFIX) && name !== shellCacheName(version));

/** 殻に入れてよい応答か。転送・エラー・よその応答を殻に入れると、オフラインで開いたときにそれが出る */
export const isShellWorthy = (response: { ok: boolean; redirected: boolean; type: string }): boolean =>
  response.ok && !response.redirected && response.type === 'basic';

/**
 * 新しい版を有効にする合図（画面から待っている Service Worker へ送る）。
 * ⚠ 画面の側（`src/pwa/appUpdate.ts`）にも同じ値を持つ。画面の束からこのファイルを読むと、
 * Service Worker と画面で束が共有になり、Service Worker が別の束を import して動かなくなる（試験で一致を見る）
 */
export const SKIP_WAITING_MESSAGE = 'SKIP_WAITING';
