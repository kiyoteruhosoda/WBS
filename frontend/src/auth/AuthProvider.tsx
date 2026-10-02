import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Button, CircularProgress } from '@mui/material';
import { getAuthConfig, getCurrentUser, logout as requestLogout, startLogin } from '../api/auth';
import { setUnauthorizedHandler } from '../api/client';
import LoginPage from '../pages/LoginPage';
import { translate } from '../i18n';
import { isNetworkFailure } from '../pwa/connectivity';
import { forgetSession, lastSession, rememberSession } from './lastSession';
import type { AuthConfig, CurrentUser } from '../types';

interface AuthContextValue {
  /** SSO を使わない配備では null（ログイン導線そのものが無い）。 */
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

/** ログイン後に戻る先。ログイン画面そのものへは戻さない。 */
const currentPath = (): string => {
  const { pathname, search } = window.location;
  return pathname === '/login' ? '/' : `${pathname}${search}`;
};

const Centered: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Box sx={{ minHeight: '100svh', display: 'grid', placeItems: 'center' }}>{children}</Box>
);

/**
 * 認証状態を確かめてから中身を描く。
 *
 * - `AUTH_MODE=single_user` の配備では素通し（従来どおりログイン画面は出ない）
 * - SSO 有効かつ未ログインなら、経路にかかわらずログイン画面を出す
 * - つながらない（オフラインで開いた）ときは、最後にログインしていた人の控えで中身を描く（task #192 / ADR-0028）。
 *   データは取れないので各画面が失敗を出し、上に「オフラインです」が出る。つながったらサーバの答えが勝つ
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient();
  const [sessionExpired, setSessionExpired] = useState(false);

  const { data: fetchedConfig, isPending: configPending, error: configError } = useQuery<AuthConfig>({
    queryKey: ['auth', 'config'],
    queryFn: getAuthConfig,
    retry: false,
    staleTime: Infinity,
  });

  // オフラインで開いたときの控え（つながらなかったときだけ使う。4xx / 5xx では使わない）
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

  const user = fetchedUser ?? (isNetworkFailure(userError) ? lastSession()?.user : undefined);

  // 確かめられた人を控える（次にオフラインで開いたときに使う）
  useEffect(() => {
    if (fetchedConfig?.sso_enabled && fetchedUser) rememberSession({ config: fetchedConfig, user: fetchedUser });
  }, [fetchedConfig, fetchedUser]);

  // どの画面の通信で 401 が出ても、ログイン画面へ戻す。
  // ただし「まだ一度もログインしていない」ときの 401 は期限切れではないので、
  // 本人が判明したあと（＝セッションがあった）に受けた 401 だけを期限切れとして扱う。
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
    queryClient.clear();
    // IdP 側のセッションも切る。切らないと「ログアウト → ログイン」で
    // 何も聞かれずに同じ人で入り直してしまい、別の人に代われない。
    window.location.href = result.end_session_url ?? '/login';
  }, [queryClient]);

  if (configPending) {
    return <Centered><CircularProgress /></Centered>;
  }

  // オフラインで開いたが、控えが無い（この端末で一度もログインしていない）
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

  if (userPending && !user) {
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
