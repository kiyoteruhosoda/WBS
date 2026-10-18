import React from 'react';
import { Alert, Box, Snackbar } from '@mui/material';
import { useI18n } from '../i18n';
import type { TimerFailure } from '../timer/timerState';

/**
 * 打刻の書き込みの失敗を知らせる。409（いまは書き込めない状態。確定済みの締めの期間に掛かるなど）は
 * 押し直しても通らないので、「もう一度」とは言わずに理由を添える（サーバの英語の文は出さない。task #499）。
 */
const TimerFailureNotice: React.FC<{ failure: TimerFailure | null; onClose: () => void }> = ({ failure, onClose }) => {
  const { t } = useI18n();
  return (
    <Snackbar
      open={failure != null}
      autoHideDuration={failure?.conflict ? 10000 : 5000}
      onClose={onClose}
      anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
    >
      <Alert severity={failure?.conflict ? 'warning' : 'error'} onClose={onClose} sx={{ width: '100%' }}>
        {failure?.conflict ? t('timer.conflict') : t('timer.error')}
        {failure?.conflict && failure.reason && (
          <Box component="span" sx={{ display: 'block', mt: '4px', fontSize: 12, opacity: 0.85 }}>{t(failure.reason.key, failure.reason.params)}</Box>
        )}
      </Alert>
    </Snackbar>
  );
};

export default TimerFailureNotice;
