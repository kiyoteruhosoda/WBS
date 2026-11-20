import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { oneAtATime, renewInFrame } from '../auth/silentRenewal';
import { forgetSilentMarks, markSilentAttempt, signedOutHere } from '../auth/silentSignIn';
import { continueSession, type ContinuationOutcome } from './sessionContinuation';
import { currentOutage, outageFrom, reportOutage, reportReopened } from '../pwa/maintenance';

const client = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  // Tokens are HttpOnly cookies. Same origin (via nginx), so they are sent by default,
  // but state the intent explicitly.
  withCredentials: true,
});

type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler | null = null;

/**
 * Register the cleanup for a session expiry (a 401 where continuing was also refused).
 * A single path back to the sign-in page wherever it happens (drafts are kept by `sessionDraft`).
 */
export const setUnauthorizedHandler = (handler: UnauthorizedHandler | null): void => {
  onUnauthorized = handler;
};

const ME_PATH = '/auth/me';

/** Whether the current cookies still work (another tab may have continued first). Throws when unreachable. */
const stillSignedIn = async (): Promise<boolean> => {
  try {
    await client.get(ME_PATH, { probe: true } as RetriableConfig);
    return true;
  } catch (error) {
    const status = (error as AxiosError).response?.status;
    if (status !== undefined && status < 500) return false;
    throw error;
  }
};

let continuing: Promise<ContinuationOutcome> | null = null;

/**
 * Continue the session (ADR-0071). SSO sessions have no refresh token, so
 * ask the IdP with `prompt=none` in a hidden frame. ⚠ **Concurrent 401 requests wait for a single one.**
 * Tokens travel as cookies both ways, so nothing is passed around here.
 */
const tryContinue = (): Promise<ContinuationOutcome> => {
  continuing ??= continueSession({
    signedOutHere,
    oneAtATime,
    stillSignedIn,
    renewInFrame: () => renewInFrame(),
    onRenewed: forgetSilentMarks,
    onDeclined: () => {
      markSilentAttempt();
    },
  }).finally(() => {
    continuing = null;
  });
  return continuing;
};

type RetriableConfig = InternalAxiosRequestConfig & {
  /** Retry after continuing */
  continuedOnce?: boolean;
  /** The check whether to continue ({@link stillSignedIn}). The caller reads the answer */
  probe?: boolean;
};

client.interceptors.response.use(
  (response) => {
    // An answer came back = the edge is open (puts the maintenance screen away if it is up; ADR-0075)
    if (currentOutage()) reportReopened();
    return response;
  },
  async (error: AxiosError) => {
    // The edge's "closed" 503 switches the whole app to the maintenance screen (ADR-0075).
    // The error is still thrown, so the caller stops as before
    const outage = outageFrom(error.response?.status, error.response?.data);
    if (outage) {
      reportOutage(outage);
      throw error;
    }
    const config = error.config as RetriableConfig | undefined;
    if (error.response?.status !== 401) throw error;
    if (config?.probe) throw error;
    if (!config || config.continuedOnce) {
      onUnauthorized?.();
      throw error;
    }
    const outcome = await tryContinue();
    if (outcome.kind === 'continued') {
      return client.request({ ...config, continuedOnce: true } as RetriableConfig);
    }
    if (outcome.kind === 'unavailable') throw outcome.error;
    onUnauthorized?.();
    throw error;
  },
);

export default client;
