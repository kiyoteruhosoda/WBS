/**
 * The front proxy (edge) saying "closed" (task #655, ADR-0075; same behaviour as fastapitemplate ADR-0067).
 *
 * While a deployment or a planned maintenance is declared for this host, the edge answers every request with 503,
 * and non-browser requests (`fetch` / axios) get JSON:
 *
 *   {"error": "service_unavailable", "reason": "maintenance", "until": "…Z",
 *    "message": "<reason>", "title": "<heading>", "body": "<text>"}
 *
 * When only the upstream (this app) is missing, `reason` is `"stopped"`.
 *
 * ⚠ **Navigating does not show the edge's own maintenance page**, because the Service Worker serves the cached shell.
 * So the API answers switch the app to an in-app screen. This module only holds that state (closed or not, and what was said).
 *
 * ⚠ The app's own errors are `{"detail": …}` and never have `error` + `reason` at the top level.
 * A 503 of any other shape is not treated as "closed".
 */

export type OutageReason = 'maintenance' | 'stopped';

/** What the edge said. Text fields are null when missing (older edges have no title / body). */
export interface Outage {
  reason: OutageReason;
  title: string | null;
  body: string | null;
  /** Why it is closed (`--reason` of the declaration). */
  message: string | null;
  /** Expected back (ISO 8601, UTC). */
  until: string | null;
}

/** Result of a re-check. `unknown` = unreachable or another failure: neither closed nor open can be said. */
export type ServiceState = 'open' | 'closed' | 'unknown';

const SERVICE_UNAVAILABLE = 503;

/**
 * Path the re-check calls: public (no sign-in needed) and light.
 * ⚠ Any path works while closed (the edge closes every path of a declared host).
 */
export const PROBE_PATH = '/api/auth/config';

const text = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() !== '' ? value : null;

const isOutageReason = (value: unknown): value is OutageReason =>
  value === 'maintenance' || value === 'stopped';

/** Picks out the edge's "closed" answer from a 503 body. Anything else is null. */
export const outageFrom = (status: number | undefined, payload: unknown): Outage | null => {
  if (status !== SERVICE_UNAVAILABLE || !payload || typeof payload !== 'object') return null;
  const body = payload as Record<string, unknown>;
  if (body.error !== 'service_unavailable' || !isOutageReason(body.reason)) return null;
  return {
    reason: body.reason,
    title: text(body.title),
    body: text(body.body),
    message: text(body.message),
    until: text(body.until),
  };
};

type Listener = () => void;

let current: Outage | null = null;
const listeners = new Set<Listener>();

const sameOutage = (a: Outage | null, b: Outage | null): boolean => JSON.stringify(a) === JSON.stringify(b);

const publish = (next: Outage | null): void => {
  if (sameOutage(current, next)) return;
  current = next;
  listeners.forEach((listener) => listener());
};

/** The current outage, or null when open. */
export const currentOutage = (): Outage | null => current;

export const subscribeOutage = (listener: Listener): (() => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** The edge said it is closed. */
export const reportOutage = (outage: Outage): void => publish(outage);

/** Found to be open again. */
export const reportReopened = (): void => publish(null);

/**
 * Re-checks whether it is closed and records the answer (unchanged when unreachable).
 *
 * Any answer that is not the edge's 503 and not a server failure means the edge let it through = open.
 * ⚠ Never use a stored answer (the edge sends no-store too, but just in case).
 */
export const checkService = async (fetcher: typeof fetch = fetch): Promise<ServiceState> => {
  let response: Response;
  try {
    response = await fetcher(PROBE_PATH, { cache: 'no-store', credentials: 'same-origin' });
  } catch {
    return 'unknown';
  }
  if (response.status < 500) {
    reportReopened();
    return 'open';
  }
  const outage = outageFrom(response.status, await response.json().catch(() => null));
  if (!outage) return 'unknown';
  reportOutage(outage);
  return 'closed';
};

/** Test only: back to the initial state. */
export const resetOutageForTests = (): void => {
  current = null;
  listeners.clear();
};
