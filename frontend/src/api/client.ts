import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { oneAtATime, renewInFrame } from '../auth/silentRenewal';
import { forgetSilentMarks, markSilentAttempt, signedOutHere } from '../auth/silentSignIn';
import { continueSession, type ContinuationOutcome } from './sessionContinuation';

const client = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  // トークンは HttpOnly Cookie。同一オリジン（nginx 経由）なので既定でも送られるが、
  // 意図を明示しておく。
  withCredentials: true,
});

type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler | null = null;

/**
 * ログイン切れ（続けることも断られた 401）を受け取ったときの後始末を登録する。
 * 画面のどこで起きても、ログイン画面へ戻せるようにするための一本道（書きかけは `sessionDraft` が残す）。
 */
export const setUnauthorizedHandler = (handler: UnauthorizedHandler | null): void => {
  onUnauthorized = handler;
};

const ME_PATH = '/auth/me';

/** 今の Cookie でまだ通るか（ほかのタブが先に続けていたか）。届かなければ投げる。 */
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
 * ログインを続ける（ADR-0071）。SSO で入ったログインはリフレッシュトークンを持たないので、
 * 見えない枠で IdP へ `prompt=none` で問い合わせる。⚠ **同時に 401 になった要求は 1 本を待つ。**
 * トークンは行きも帰りも Cookie なので、ここでは何も持ち回さない。
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
  /** 続けたあとの再試行 */
  continuedOnce?: boolean;
  /** 続けるかを確かめる問い合わせ（{@link stillSignedIn}）。答えは呼んだ側が読む */
  probe?: boolean;
};

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
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
