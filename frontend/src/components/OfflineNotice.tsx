import React from 'react';
import { Alert } from '@mui/material';
import { useI18n } from '../i18n';
import { useOffline } from '../pwa/connectivity';

/**
 * "You are offline" (task #192, ADR-0028). The Service Worker serves the app shell, but data can't be fetched.
 * Shown when the device reports no network or the last fetch failed without a response; hidden once any fetch succeeds.
 */
const OfflineNotice: React.FC = () => {
  const { t } = useI18n();
  const offline = useOffline();
  if (!offline) return null;
  return (
    <Alert severity="warning" role="status" sx={{ mb: '12px' }}>
      {t('offline.notice')}
    </Alert>
  );
};

export default OfflineNotice;
