// 切れたログインを、画面を出さずに続ける（ADR-0071。fastapitemplate の ADR-0104 と同じ考え）。
//
// SSO で入ったログインはリフレッシュトークンを持たない。アクセストークン（5 分）が切れたら、
// 見えない枠（iframe）で `/api/auth/renew` を開き、IdP へ `prompt=none` で問い合わせる。
// IdP のログイン状態が生きていれば、戻り（`/api/auth/callback`）が新しい Cookie を載せて
// 結果の頁（`/api/auth/renewed?result=…`）へ送る。画面は枠の行き先（同じオリジン）を読む。
//
// - 枠の中でスクリプトは動かさない（`postMessage` を使わない）。結果は URL だけで渡る
// - 枠が IdP の画面で止まった（読めないオリジンのまま読み込みが終わった）・時間切れは `failed`
// - **タブをまたいで 1 本ずつ**（Web Locks）。往復の印の Cookie は 1 つの値に 3 本まで積むが、
//   同時に走らせると IdP 側の往復も重なるので、待てば済むものは待つ

/** 結果の頁（サーバーの `src/presentation/api/renewal.py` と対）。 */
export const RENEWAL_RESULT_PATH = '/api/auth/renewed';
export const RENEWAL_START_PATH = '/api/auth/renew';
const LOCK_NAME = 'wbs-sso-renewal';
/** IdP の往復を待つ長さ。これを過ぎたら諦めてログイン画面を出す。 */
export const RENEWAL_TIMEOUT_MS = 15_000;

export type RenewalResult = 'renewed' | 'declined' | 'failed';

/** 枠の今の行き先から結果を読む。まだ途中（`about:blank`）なら null。 */
export const resultOf = (frame: HTMLIFrameElement): RenewalResult | null => {
  let location: Location | undefined;
  try {
    location = frame.contentWindow?.location;
    if (!location || location.href === 'about:blank') return null;
    if (location.pathname !== RENEWAL_RESULT_PATH) return 'failed';
  } catch {
    // 読めないオリジン（IdP の画面）で止まった。prompt=none なので画面は出ないはず
    return 'failed';
  }
  const value = new URLSearchParams(location.search).get('result');
  return value === 'renewed' || value === 'declined' ? value : 'failed';
};

/** 見えない枠で 1 回問い合わせる。 */
export const renewInFrame = (timeoutMs = RENEWAL_TIMEOUT_MS): Promise<RenewalResult> =>
  new Promise((resolve) => {
    const frame = document.createElement('iframe');
    frame.hidden = true;
    frame.tabIndex = -1;
    frame.setAttribute('aria-hidden', 'true');
    let settled = false;
    const finish = (result: RenewalResult) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      frame.remove();
      resolve(result);
    };
    const timer = window.setTimeout(() => finish('failed'), timeoutMs);
    frame.addEventListener('load', () => {
      const result = resultOf(frame);
      if (result) finish(result);
    });
    frame.src = RENEWAL_START_PATH;
    document.body.appendChild(frame);
  });

/** タブをまたいで 1 本ずつ走らせる。Web Locks の無いブラウザ（古いもの・http の開発）ではそのまま走らせる。 */
export const oneAtATime = async <T>(task: () => Promise<T>): Promise<T> => {
  const locks = (navigator as Partial<Pick<Navigator, 'locks'>>).locks;
  if (!locks) return task();
  return locks.request(LOCK_NAME, task);
};
