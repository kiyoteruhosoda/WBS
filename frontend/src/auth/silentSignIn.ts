// ログイン画面を描く前に、IdP（Assay）でもう入っているかを黙って確かめる（task #647・ADR-0062）。
//
// 入っていればボタンを押さずにそのまま入り、入っていなければふつうのログイン画面を出す。
// 確かめるのはサーバの `/api/auth/login?silent=1`（認可要求に `prompt=none` を付ける）で、
// ここが決めるのは**試してよいか**だけ。
//
// 試さないとき（ループと勝手な入り直しを防ぐ）:
// - このタブで一度試して戻ってきた後（sessionStorage の印。入れたら消す）。
//   ただし**本人が再読み込みしたときは、もう 1 回だけ試す**（別のタブで Assay に入ってから戻ってきたとき。ADR-0063）。
//   断られて戻る先は再読み込みではない遷移なので、ループにはならない
// - このアプリでサインアウトした後（localStorage の印。次に入れたら消す）
// - ログイン画面（`/login`）に `next` 以外が付いているとき（`error` など。黙って断られた印 `sso_silent` は再読み込みなら構わない）
// - 印が読み書きできないとき（1 回だけの印が置けないと、戻ってくるたびに試してループになる）

const ATTEMPTED_KEY = 'wbs.sso.silentAttempted';
const SIGNED_OUT_KEY = 'wbs.sso.signedOut';

const LOGIN_PATH = '/login';
/** ログイン画面の URL で、付いていても試してよいもの（開こうとした画面）。 */
const ALLOWED_LOGIN_PARAMS = new Set(['next']);
/** 再読み込みしたときに限って、付いていても試してよいもの（前に黙って断られた印）。 */
const SILENT_DECLINED_PARAM = 'sso_silent';

/** この画面は本人の再読み込みで開かれたか。1 つの画面で 1 回だけ真（試した後にまた真にならないように） */
let reloadAllowanceUsed = false;
const openedByReload = (): boolean => {
  if (reloadAllowanceUsed) return false;
  try {
    const [entry] = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
    return entry?.type === 'reload';
  } catch {
    return false;
  }
};

type Place = Pick<Location, 'pathname' | 'search'>;

export const shouldTrySilently = ({ pathname, search }: Place, reloaded = openedByReload()): boolean => {
  if (pathname === LOGIN_PATH) {
    for (const name of new URLSearchParams(search).keys()) {
      if (ALLOWED_LOGIN_PARAMS.has(name) || (reloaded && name === SILENT_DECLINED_PARAM)) continue;
      return false;
    }
  }
  try {
    if (localStorage.getItem(SIGNED_OUT_KEY) !== null) return false;
    return reloaded || sessionStorage.getItem(ATTEMPTED_KEY) === null;
  } catch {
    return false;
  }
};

/** これから試す。戻ってきたら、このタブではもう試さない。置けなければ偽（試さない） */
export const markSilentAttempt = (): boolean => {
  reloadAllowanceUsed = true;
  try {
    sessionStorage.setItem(ATTEMPTED_KEY, '1');
    return true;
  } catch {
    return false;
  }
};

/** サインアウトした。次に入るまで黙って入り直さない */
export const rememberSignedOut = (): void => {
  try {
    localStorage.setItem(SIGNED_OUT_KEY, '1');
  } catch {
    // 覚えられないだけ。ストレージが使えない環境では、そもそも試さない
  }
};

/** 入れた。次に切れたときは、また 1 回だけ試してよい */
export const forgetSilentMarks = (): void => {
  try {
    sessionStorage.removeItem(ATTEMPTED_KEY);
    localStorage.removeItem(SIGNED_OUT_KEY);
  } catch {
    // 消せないなら試さないままになるだけ（ボタンで入れる）
  }
};

/**
 * ログイン後に戻る先。ログイン画面そのものへは戻さず、付いている `next`（黙って確かめて戻ってきたとき）を使う。
 * 外を指す値はサーバの `RedirectTarget` が落とすので、ここでは形だけ見る。
 */
export const returnPathOf = ({ pathname, search }: Place): string => {
  if (pathname !== LOGIN_PATH) return `${pathname}${search}`;
  const next = new URLSearchParams(search).get('next');
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
};
