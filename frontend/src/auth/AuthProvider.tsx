import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Button, CircularProgress } from '@mui/material';
import {
  getAuthConfig,
  getCurrentUser,
  logout as requestLogout,
  startLogin,
  startSilentLogin,
} from '../api/auth';
import { setUnauthorizedHandler } from '../api/client';
import LoginPage from '../pages/LoginPage';
import { translate } from '../i18n';
import { isNetworkFailure, isServerFailure } from '../pwa/connectivity';
import { forgetSession, lastSession, rememberSession } from './lastSession';
import { clearSessionDrafts } from './sessionDraft';
import {
  forgetSilentMarks,
  markSilentAttempt,
  rememberSignedOut,
  returnPathOf,
  shouldTrySilently,
} from './silentSignIn';
import type { AuthConfig, CurrentUser } from '../types';

interface AuthContextValue {
  /** null in deployments without SSO (there is no sign-in flow at all). */
  user: CurrentUser | null;
  ssoEnabled: boolean;
  providerName: string | null;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  ssoEnabled: false,
  providerName: null,
  signOut: async () => {},
});

export const useAuth = (): AuthContextValue => useContext(AuthContext);

/** Where to return after sign-in. Never back to the sign-in page itself (use its `next` instead). */
const currentPath = (): string => returnPathOf(window.location);

const Centered: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Box sx={{ minHeight: '100svh', display: 'grid', placeItems: 'center' }}>{children}</Box>
);

/**
 * Checks auth state before rendering the content.
 *
 * - Pass-through in `AUTH_MODE=single_user` deployments (no sign-in page, as before)
 * - With SSO enabled and not signed in, shows the sign-in page regardless of route
 * - When unreachable (opened offline), renders the content from the saved copy of the last signed-in user (task #192 / ADR-0028).
 *   Data can't be fetched, so each screen shows its failure and an "offline" banner appears on top. Once connected, the server's answer wins
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient();
  const [sessionExpired, setSessionExpired] = useState(false);
  // Went to the IdP for a silent check (ADR-0062). Don't render until navigating away
  const [silentStarted, setSilentStarted] = useState(false);
  const [silentUnavailable, setSilentUnavailable] = useState(false);

  const { data: fetchedConfig, isPending: configPending, error: configError } = useQuery<AuthConfig>({
    queryKey: ['auth', 'config'],
    queryFn: getAuthConfig,
    retry: false,
    staleTime: Infinity,
  });

  // Saved copy for offline opening (used only when unreachable; not on 4xx / 5xx)
  const offlineSession = isNetworkFailure(configError) ? lastSession() : null;
  const config = fetchedConfig ?? offlineSession?.config;
  const ssoEnabled = config?.sso_enabled ?? false;

  const { data: fetchedUser, isPending: userPending, error: userError } = useQuery<CurrentUser>({
    queryKey: ['auth', 'me'],
    queryFn: getCurrentUser,
    enabled: ssoEnabled,
    retry: false,
    staleTime: 5 * 60_000,
  });

  // If we merely couldn't check (unreachable or server down), the session isn't over. Render from the saved copy (ADR-0069)
  const userUnconfirmed = isNetworkFailure(userError) || isServerFailure(userError);
  const user = fetchedUser ?? (userUnconfirmed ? lastSession()?.user : undefined);

  // Save the verified user (used the next time it's opened offline).
  // Signed in, so also clear the silent-check marker (next time the session ends, one more try is allowed)
  useEffect(() => {
    if (fetchedConfig?.sso_enabled && fetchedUser) {
      rememberSession({ config: fetchedConfig, user: fetchedUser });
      forgetSilentMarks();
    }
  }, [fetchedConfig, fetchedUser]);

  // Once known to be signed out, do a silent check at the IdP before rendering the sign-in page (ADR-0062).
  // Don't try when the session ended mid-use (sessionExpired) —— navigating away by itself would lose what was being typed.
  // ⚠ Only when the marker could be stored. Otherwise it would retry on every return and loop
  const silentPlanned =
    ssoEnabled &&
    !userPending &&
    !user &&
    !sessionExpired &&
    !silentUnavailable &&
    !userUnconfirmed &&
    Boolean(fetchedConfig?.login_path) &&
    shouldTrySilently(window.location);
  useEffect(() => {
    if (!silentPlanned || !fetchedConfig) return;
    if (!markSilentAttempt()) {
      setSilentUnavailable(true);
      return;
    }
    setSilentStarted(true);
    startSilentLogin(fetchedConfig, currentPath());
  }, [silentPlanned, fetchedConfig]);

  // A 401 from any screen's request (after the continuation round trip is also refused; ADR-0071) returns to the sign-in page.
  // Drafts stay in sessionStorage and come back when signing in again and opening the same screen.
  // However, a 401 before ever signing in is not an expiry,
  // so only a 401 received after the user was known (= there was a session) is treated as expiry.
  const hadSession = Boolean(user);
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (hadSession) setSessionExpired(true);
    });
    return () => setUnauthorizedHandler(null);
  }, [hadSession]);

  const signOut = useCallback(async () => {
    const result = await requestLogout();
    forgetSession();
    // So the sign-in page doesn't do a silent check at the IdP (ADR-0062)
    rememberSignedOut();
    // Also clear drafts (someone else may sign in on the same tab. ADR-0071)
    clearSessionDrafts();
    queryClient.clear();
    // Also end the IdP session. Otherwise "sign out → sign in"
    // signs the same user back in without asking, and you can't switch to another user.
    window.location.href = result.end_session_url ?? '/login';
  }, [queryClient]);

  if (configPending) {
    return <Centered><CircularProgress /></Centered>;
  }

  // Opened offline with no saved copy (never signed in on this device)
  if (!config && isNetworkFailure(configError)) {
    return (
      <Centered>
        <Box sx={{ textAlign: 'center', display: 'grid', gap: '12px', px: '16px' }}>
          <Box>{translate('offline.noSession')}</Box>
          <Box><Button variant="outlined" onClick={() => window.location.reload()}>{translate('offline.retry')}</Button></Box>
        </Box>
      </Centered>
    );
  }

  if (!ssoEnabled) {
    return (
      <AuthContext.Provider value={{ user: null, ssoEnabled: false, providerName: null, signOut }}>
        {children}
      </AuthContext.Provider>
    );
  }

  if ((userPending && !user) || silentPlanned || silentStarted) {
    return <Centered><CircularProgress /></Centered>;
  }

  if (!user || sessionExpired) {
    return (
      <LoginPage
        providerName={config?.provider_name ?? null}
        sessionExpired={sessionExpired}
        onSignIn={() => config && startLogin(config, currentPath())}
      />
    );
  }

  return (
    <AuthContext.Provider
      value={{ user, ssoEnabled: true, providerName: config?.provider_name ?? null, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
};
