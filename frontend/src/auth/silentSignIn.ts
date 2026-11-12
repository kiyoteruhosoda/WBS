// Before rendering the sign-in page, silently check whether the user is already signed in at the IdP (Assay) (task #647, ADR-0062).
//
// If so, sign in without pressing the button; otherwise show the normal sign-in page.
// The check is the server's `/api/auth/login?silent=1` (adds `prompt=none` to the authorization request);
// this module only decides **whether to try**.
//
// When not to try (prevents loops and unwanted re-sign-in):
// - after trying once in this tab and coming back (a sessionStorage marker, cleared on sign-in).
//   But **when the user reloads, try once more** (after signing in to Assay in another tab and coming back. ADR-0063).
//   The return after a refusal is not a reload navigation, so it does not loop
// - after signing out of this app (a localStorage marker, cleared on the next sign-in)
// - when the sign-in page (`/login`) carries anything other than `next` (`error` etc.; the silent-refusal marker `sso_silent` is fine on reload)
// - when markers can't be read or written (without the one-shot marker it would retry on every return and loop)

const ATTEMPTED_KEY = 'wbs.sso.silentAttempted';
const SIGNED_OUT_KEY = 'wbs.sso.signedOut';

const LOGIN_PATH = '/login';
/** Sign-in page URL parameters that still allow trying (the page the user wanted to open). */
const ALLOWED_LOGIN_PARAMS = new Set(['next']);
/** Parameters that allow trying only on reload (marker of an earlier silent refusal). */
const SILENT_DECLINED_PARAM = 'sso_silent';

/** Whether this page was opened by a user reload. True only once per page (so it isn't true again after trying) */
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

/** About to try. After returning, don't try again in this tab. False if the marker can't be stored (don't try) */
export const markSilentAttempt = (): boolean => {
  reloadAllowanceUsed = true;
  try {
    sessionStorage.setItem(ATTEMPTED_KEY, '1');
    return true;
  } catch {
    return false;
  }
};

/** Whether the signed-out marker is set (also skips the session continuation request. ADR-0071). True if unreadable */
export const signedOutHere = (): boolean => {
  try {
    return localStorage.getItem(SIGNED_OUT_KEY) !== null;
  } catch {
    return true;
  }
};

/** Signed out. No silent re-sign-in until the next sign-in */
export const rememberSignedOut = (): void => {
  try {
    localStorage.setItem(SIGNED_OUT_KEY, '1');
  } catch {
    // Just can't remember it. Without storage we never try anyway
  }
};

/** Signed in. Next time the session ends, one more try is allowed */
export const forgetSilentMarks = (): void => {
  try {
    sessionStorage.removeItem(ATTEMPTED_KEY);
    localStorage.removeItem(SIGNED_OUT_KEY);
  } catch {
    // If it can't be cleared we just won't try (the button still works)
  }
};

/**
 * Where to return after sign-in. Never the sign-in page itself; use its `next` (when returning from a silent check).
 * External targets are dropped by the server's `RedirectTarget`, so only the shape is checked here.
 */
export const returnPathOf = ({ pathname, search }: Place): string => {
  if (pathname !== LOGIN_PATH) return `${pathname}${search}`;
  const next = new URLSearchParams(search).get('next');
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
};
