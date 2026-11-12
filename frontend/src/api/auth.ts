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

/** Send the user to the IdP sign-in page, passing the current page as the return target. */
export const startLogin = (config: AuthConfig, nextPath: string): void => {
  if (!config.login_path) return;
  window.location.href = `${config.login_path}?next=${encodeURIComponent(nextPath)}`;
};

/**
 * Check whether the user is already signed in at the IdP without showing any UI (ADR-0062).
 * If so, returns via the same path as `startLogin`; otherwise back to `/login?sso_silent=1` (with `next`).
 * Not kept in history (so "back" doesn't trigger the check again).
 */
export const startSilentLogin = (config: AuthConfig, nextPath: string): void => {
  if (!config.login_path) return;
  window.location.replace(`${config.login_path}?silent=1&next=${encodeURIComponent(nextPath)}`);
};
