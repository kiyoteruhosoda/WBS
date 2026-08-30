import client from './client';
import type { AuthConfig, CurrentUser, LogoutResult } from '../types';

export const getAuthConfig = async (): Promise<AuthConfig> => {
  const { data } = await client.get('/auth/config');
  return data;
};

export const getCurrentUser = async (): Promise<CurrentUser> => {
  const { data } = await client.get('/auth/me');
  return data;
};

export const logout = async (): Promise<LogoutResult> => {
  const { data } = await client.post('/auth/logout');
  return data;
};

/** IdP のログイン画面へ送り出す。戻り先に今いる画面を渡す。 */
export const startLogin = (config: AuthConfig, nextPath: string): void => {
  if (!config.login_path) return;
  window.location.href = `${config.login_path}?next=${encodeURIComponent(nextPath)}`;
};
