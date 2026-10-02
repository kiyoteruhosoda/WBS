// 最後にログインしていた人の控え（task #192・ADR-0028）。オフラインで開いたとき、ログインを確かめられなくても
// 画面の殻を出す（「オフラインです」と、端末に溜める打刻）ために使う。
//
// 控えるのは画面に出す名前とログインの設定だけで、秘密は持たない（セッションは HttpOnly の Cookie のまま）。
// つながったらサーバの答えが勝つ（ログインが切れていればログイン画面になる）。ログアウトで消す。

import type { AuthConfig, CurrentUser } from '../types';

const STORAGE_KEY = 'wbs.lastSession';

export interface LastSession {
  config: AuthConfig;
  user: CurrentUser;
}

/** 控えを読む。形が違う・壊れているものは無いことにする */
export const parseLastSession = (raw: string | null): LastSession | null => {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<LastSession> | null;
    const config = value?.config;
    const user = value?.user;
    if (!config || typeof config.sso_enabled !== 'boolean') return null;
    if (!user || typeof user.user_id !== 'number' || typeof user.display_name !== 'string') return null;
    return { config, user };
  } catch {
    return null;
  }
};

export const lastSession = (): LastSession | null => {
  try {
    return parseLastSession(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
};

export const rememberSession = (session: LastSession): void => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // 控えられなくても、オフラインで開いたときに殻が出ないだけ
  }
};

export const forgetSession = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // 同上
  }
};
