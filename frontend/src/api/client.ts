import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

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
 * ログイン切れ（更新も断られた 401）を受け取ったときの後始末を登録する。
 * 画面のどこで起きても、ログイン画面へ戻せるようにするための一本道。
 */
export const setUnauthorizedHandler = (handler: UnauthorizedHandler | null): void => {
  onUnauthorized = handler;
};

const REFRESH_PATH = '/auth/refresh';

type RefreshOutcome =
  | { kind: 'refreshed' }
  /** 更新の口が断った。ログインは終わっている */
  | { kind: 'expired' }
  /** 更新の口に届かない・口が落ちている。⚠ ログアウト扱いにしない（Cookie は残っていて、戻れば続く） */
  | { kind: 'unavailable'; error: unknown };

let refreshing: Promise<RefreshOutcome> | null = null;

const sendRefresh = async (): Promise<RefreshOutcome> => {
  try {
    await client.post(REFRESH_PATH);
    return { kind: 'refreshed' };
  } catch (error) {
    const status = (error as AxiosError).response?.status;
    if (status !== undefined && status < 500) return { kind: 'expired' };
    return { kind: 'unavailable', error };
  }
};

/**
 * トークンを更新する。⚠ **同時に 401 になった要求は 1 本の更新を待つ**（ADR-0069）。
 * トークンは行きも帰りも Cookie なので、ここでは何も持ち回さない。
 */
const tryRefresh = (): Promise<RefreshOutcome> => {
  refreshing ??= sendRefresh().finally(() => {
    refreshing = null;
  });
  return refreshing;
};

type RetriableConfig = InternalAxiosRequestConfig & { refreshedOnce?: boolean };

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined;
    // 更新そのものの失敗は tryRefresh が読む
    if (config?.url === REFRESH_PATH) throw error;
    if (error.response?.status !== 401) throw error;
    if (!config || config.refreshedOnce) {
      onUnauthorized?.();
      throw error;
    }
    const outcome = await tryRefresh();
    if (outcome.kind === 'refreshed') {
      return client.request({ ...config, refreshedOnce: true } as RetriableConfig);
    }
    if (outcome.kind === 'unavailable') throw outcome.error;
    onUnauthorized?.();
    throw error;
  },
);

export default client;
