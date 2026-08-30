import axios from 'axios';

const client = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  // セッションは HttpOnly Cookie。同一オリジン（nginx 経由）なので既定でも送られるが、
  // 意図を明示しておく。
  withCredentials: true,
});

type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler | null = null;

/**
 * セッション切れ（401）を受け取ったときの後始末を登録する。
 * 画面のどこで起きても、ログイン画面へ戻せるようにするための一本道。
 */
export const setUnauthorizedHandler = (handler: UnauthorizedHandler | null): void => {
  onUnauthorized = handler;
};

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      onUnauthorized?.();
    }
    return Promise.reject(error);
  },
);

export default client;
