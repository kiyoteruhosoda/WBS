import React from 'react';
import { Alert, Box, Button, Paper, Typography } from '@mui/material';
import { ds } from '../theme';
import { translate } from '../i18n';
import { CheckIcon } from '../components/icons';

interface Props {
  providerName: string | null;
  sessionExpired: boolean;
  onSignIn: () => void;
}

/** コールバックが失敗したときに付けてくる `?error=` を読む。 */
const callbackError = (): string | null => new URLSearchParams(window.location.search).get('error');

const errorMessage = (error: string): string => {
  if (error === 'access_denied') return translate('login.errorAccessDenied');
  if (error === 'authentication_failed') return translate('login.errorFailed');
  return translate('login.errorGeneric');
};

/**
 * ログイン画面。IdP へ送り出すボタンだけを置く。
 * パスワード欄は無い（このアプリはパスワードを持たない）。
 */
const LoginPage: React.FC<Props> = ({ providerName, sessionExpired, onSignIn }) => {
  const error = callbackError();

  return (
    <Box sx={{ minHeight: '100svh', display: 'grid', placeItems: 'center', bgcolor: ds.canvas, p: 2 }}>
      <Paper
        elevation={0}
        sx={{
          width: '100%', maxWidth: 380, p: '32px', borderRadius: '12px',
          border: `1px solid ${ds.border}`, textAlign: 'center',
        }}
      >
        <Box sx={{
          width: 44, height: 44, borderRadius: '10px', bgcolor: ds.primary, color: '#fff',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', mb: '16px',
        }}>
          <CheckIcon size={24} />
        </Box>
        <Typography sx={{ fontSize: 18, fontWeight: 700, color: ds.text }}>
          {translate('app.name')}
        </Typography>
        <Typography sx={{ fontSize: 14, color: ds.textMuted, mt: '6px', mb: '24px' }}>
          {translate('login.subtitle')}
        </Typography>

        {sessionExpired && !error && (
          <Alert severity="info" sx={{ mb: '16px', textAlign: 'left' }}>
            {translate('login.sessionExpired')}
          </Alert>
        )}
        {error && (
          <Alert severity="error" sx={{ mb: '16px', textAlign: 'left' }}>
            {errorMessage(error)}
          </Alert>
        )}

        <Button variant="contained" fullWidth onClick={onSignIn} sx={{ py: '10px' }}>
          {providerName
            ? translate('login.signInWith', { provider: providerName })
            : translate('login.signIn')}
        </Button>
      </Paper>
    </Box>
  );
};

export default LoginPage;
