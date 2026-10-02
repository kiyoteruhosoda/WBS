import React from 'react';
import { Alert } from '@mui/material';
import { useI18n } from '../i18n';
import { useOffline } from '../pwa/connectivity';

/**
 * 「オフラインです」（task #192・ADR-0028）。画面の殻は Service Worker が出すが、データは取れない。
 * 端末が電波なしと言うか、直前の取得が応答なしで落ちたときに出し、何か 1 つ取れたら消える。
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
