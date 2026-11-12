/**
 * Service Worker registration and new-version detection (task #192, ADR-0028; shape follows the fastapitemplate template's ADR-0035).
 *
 * The SPA only redraws and never reloads, so **after a deploy, devices left open keep running the old
 * version**. Especially PWAs on the home screen. The Service Worker fetches the new version in the background,
 * but already loaded JavaScript cannot be swapped. So we only tell the UI that "a new version is waiting",
 * and switch over (= reload) when the user presses the button.
 *
 * ⚠ Waiting alone does not notice it. The browser checks for Service Worker updates on page navigation,
 * and SPA screen changes are not navigations. We trigger a check every 30 minutes and when the tab comes back to the foreground.
 */

/** Interval between update checks */
export const UPDATE_CHECK_INTERVAL_MS = 30 * 60 * 1000;

/** Minimum interval between checks (avoids hammering when the tab is repeatedly switched) */
export const MIN_CHECK_GAP_MS = 60 * 1000;

/**
 * Grace period after the press before we reload on our own.
 * Normally we reload on the signal that the new Service Worker took control (`controllerchange`). ⚠ On **pages not yet
 * controlled by a Service Worker** (the first tab right after registration) the signal never comes, so pressing would do nothing. This catches that.
 */
export const RELOAD_FALLBACK_MS = 2000;

/**
 * Message that activates the waiting Service Worker. ⚠ Same value as in `src/serviceWorker/requestRoutes.ts`
 * (importing it from the UI bundle would make the Service Worker bundle import another bundle and break, so it is duplicated here)
 */
export const SKIP_WAITING_MESSAGE = 'SKIP_WAITING';

/** Switch to the new version (reloads the current page) */
export type ApplyUpdate = () => void;

/** Called when a new version is waiting */
export type UpdateReadyListener = (apply: ApplyUpdate) => void;

/** Watch for a waiting new version */
export type WatchForUpdate = (onUpdateReady: UpdateReadyListener) => void;

/** Whether to check for updates now (not while fetching, offline, or just checked) */
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
      // A failed check is not shown in the UI (retried next time)
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
 * Registers `/sw.js` and reports when a new version is waiting. Not registered on the dev server (`npm run dev`)
 * (the Service Worker is only built into the production bundle).
 */
export const watchForUpdate: WatchForUpdate = (onUpdateReady) => {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return;

  const announceIfWaiting = (registration: ServiceWorkerRegistration) => {
    // With no controlling version (first registration) it is not a "new version"; it activates as is
    if (registration.waiting && navigator.serviceWorker.controller) onUpdateReady(applyWith(registration));
  };

  // ⚠ updateViaCache: 'none' —— do not read sw.js from the HTTP cache (nginx also sets no-cache)
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
      // The UI works even if registration fails (it just can't be added to the home screen or opened offline)
    });
};
