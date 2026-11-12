// Continue an expired session without showing any UI (ADR-0071; same idea as fastapitemplate's ADR-0104).
//
// SSO sessions have no refresh token. When the access token (5 minutes) expires,
// open `/api/auth/renew` in a hidden iframe and ask the IdP with `prompt=none`.
// If the IdP session is alive, the return (`/api/auth/callback`) sets new cookies and
// redirects to the result page (`/api/auth/renewed?result=…`). The UI reads the frame's location (same origin).
//
// - No scripts run inside the frame (no `postMessage`). The result is passed via the URL only
// - A frame stuck on an IdP page (finished loading on an unreadable origin) or a timeout is `failed`
// - **One at a time across tabs** (Web Locks). The round-trip state cookie stacks up to 3 in one value,
//   but running concurrently also overlaps the IdP round trips, so wait when waiting suffices

/** Result page (paired with the server's `src/presentation/api/renewal.py`). */
export const RENEWAL_RESULT_PATH = '/api/auth/renewed';
export const RENEWAL_START_PATH = '/api/auth/renew';
const LOCK_NAME = 'wbs-sso-renewal';
/** How long to wait for the IdP round trip. After this, give up and show the sign-in page. */
export const RENEWAL_TIMEOUT_MS = 15_000;

export type RenewalResult = 'renewed' | 'declined' | 'failed';

/** Read the result from the frame's current location. null while still in progress (`about:blank`). */
export const resultOf = (frame: HTMLIFrameElement): RenewalResult | null => {
  let location: Location | undefined;
  try {
    location = frame.contentWindow?.location;
    if (!location || location.href === 'about:blank') return null;
    if (location.pathname !== RENEWAL_RESULT_PATH) return 'failed';
  } catch {
    // Stuck on an unreadable origin (an IdP page). With prompt=none no page should be shown
    return 'failed';
  }
  const value = new URLSearchParams(location.search).get('result');
  return value === 'renewed' || value === 'declined' ? value : 'failed';
};

/** Ask once in a hidden frame. */
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

/** Run one at a time across tabs. Browsers without Web Locks (old ones, http dev) just run it directly. */
export const oneAtATime = async <T>(task: () => Promise<T>): Promise<T> => {
  const locks = (navigator as Partial<Pick<Navigator, 'locks'>>).locks;
  if (!locks) return task();
  return locks.request(LOCK_NAME, task);
};
