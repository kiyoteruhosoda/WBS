// Saved copy of the last signed-in user (task #192, ADR-0028). Used to show the app shell when opened offline
// even though sign-in can't be verified ("offline" banner and time entries queued on the device).
//
// Only the display name and sign-in settings are kept, no secrets (the session stays in an HttpOnly cookie).
// Once connected the server's answer wins (an expired session leads to the sign-in page). Cleared on sign-out.

import type { AuthConfig, CurrentUser } from '../types';

const STORAGE_KEY = 'wbs.lastSession';

export interface LastSession {
  config: AuthConfig;
  user: CurrentUser;
}

/** Read the saved copy. Treat wrong-shaped or corrupt data as absent */
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
    // If it can't be saved, the shell just won't show when opened offline
  }
};

export const forgetSession = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Same as above
  }
};
