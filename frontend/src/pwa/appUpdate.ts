/**
 * Service Worker の登録と、新しい版の検出（task #192・ADR-0028。形は雛形 fastapitemplate の ADR-0035）。
 *
 * SPA は画面を描き替えるだけで再読み込みしないので、**デプロイしても開きっぱなしの端末は古い版のまま
 * 動き続ける**。ホーム画面に置いた PWA は特にそう。Service Worker は新しい版を裏で取ってくるが、
 * 既に読み込まれた JavaScript は差し替えられない。そこで「新しい版が待機している」ことだけを画面へ伝え、
 * 入れ替え（＝再読み込み）は利用者が押したときに行う。
 *
 * ⚠ 待つだけでは気付けない。ブラウザが Service Worker の更新を確認するのはページ遷移のときで、
 * SPA の画面切り替えはページ遷移ではない。30 分ごとと、タブが手前へ戻ったときに確認を起こす。
 */

/** 更新を確認する間隔 */
export const UPDATE_CHECK_INTERVAL_MS = 30 * 60 * 1000;

/** 確認どうしの最短間隔（タブの出入りを繰り返しても頻繁には叩かない） */
export const MIN_CHECK_GAP_MS = 60 * 1000;

/**
 * 押してから、こちらの都合で再読み込みするまでの猶予。
 * 通常は新しい Service Worker が制御を引き継いだ合図（`controllerchange`）で読み直す。⚠ **まだ Service Worker に
 * 制御されていない画面**（登録された直後の初回のタブ）では合図が来ないので、押したのに何も起きなくなる。それを拾う。
 */
export const RELOAD_FALLBACK_MS = 2000;

/**
 * 待っている Service Worker を有効にする合図。⚠ `src/serviceWorker/requestRoutes.ts` と同じ値
 * （そちらを画面の束から読むと Service Worker の束が別の束を import して動かなくなるので、ここにも持つ）
 */
export const SKIP_WAITING_MESSAGE = 'SKIP_WAITING';

/** 新しい版へ入れ替える（現在の画面を再読み込みする） */
export type ApplyUpdate = () => void;

/** 新しい版が待機したときに呼ばれる */
export type UpdateReadyListener = (apply: ApplyUpdate) => void;

/** 待機している新しい版を見張る */
export type WatchForUpdate = (onUpdateReady: UpdateReadyListener) => void;

/** いま更新を確認しに行くか（取得中・オフライン・直前に確認済みなら行かない） */
export const shouldCheckForUpdate = (facts: {
  installing: boolean;
  online: boolean;
  nowMs: number;
  checkedAtMs: number;
}): boolean => !facts.installing && facts.online && facts.nowMs - facts.checkedAtMs >= MIN_CHECK_GAP_MS;

const scheduleChecks = (registration: ServiceWorkerRegistration): void => {
  let checkedAtMs = 0;
  const check = (): void => {
    const nowMs = Date.now();
    if (!shouldCheckForUpdate({
      installing: registration.installing != null, online: navigator.onLine, nowMs, checkedAtMs,
    })) return;
    checkedAtMs = nowMs;
    void registration.update().catch(() => {
      // 確認できなくても画面には出さない（次の機会に取り直す）
    });
  };
  window.setInterval(check, UPDATE_CHECK_INTERVAL_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') check();
  });
};

const applyWith = (registration: ServiceWorkerRegistration): ApplyUpdate => () => {
  let reloading = false;
  const reload = () => {
    if (reloading) return;
    reloading = true;
    window.location.reload();
  };
  navigator.serviceWorker.addEventListener('controllerchange', reload);
  registration.waiting?.postMessage(SKIP_WAITING_MESSAGE);
  window.setTimeout(reload, RELOAD_FALLBACK_MS);
};

/**
 * `/sw.js` を登録し、新しい版が待機したら知らせる。開発サーバ（`npm run dev`）では登録しない
 * （Service Worker は本番の束でしか焼かれない）。
 */
export const watchForUpdate: WatchForUpdate = (onUpdateReady) => {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return;

  const announceIfWaiting = (registration: ServiceWorkerRegistration) => {
    // 制御している版が無い（初めての登録）なら「新しい版」ではない。そのまま有効になる
    if (registration.waiting && navigator.serviceWorker.controller) onUpdateReady(applyWith(registration));
  };

  // ⚠ updateViaCache: 'none' —— sw.js を HTTP のキャッシュから読まない（nginx も no-cache を付ける）
  navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' })
    .then((registration) => {
      announceIfWaiting(registration);
      registration.addEventListener('updatefound', () => {
        const installing = registration.installing;
        installing?.addEventListener('statechange', () => {
          if (installing.state === 'installed') announceIfWaiting(registration);
        });
      });
      scheduleChecks(registration);
    })
    .catch(() => {
      // 登録できなくても画面は動く（ホーム画面に置けない・オフラインで開けないだけ）
    });
};
