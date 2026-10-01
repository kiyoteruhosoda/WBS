import React from 'react';
import { Alert, Box, Snackbar } from '@mui/material';
import { useI18n } from '../i18n';
import type { TimerFailure } from '../timer/timerState';

/**
 * 打刻の書き込みの失敗を知らせる。409（いまは書き込めない状態。確定済みの締めの期間に掛かるなど）は
 * 押し直しても通らないので、「もう一度」とは言わずにサーバの理由を添える。
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
        {failure?.conflict && failure.detail && (
          <Box component="span" sx={{ display: 'block', mt: '4px', fontSize: 12, opacity: 0.85 }}>{failure.detail}</Box>
        )}
      </Alert>
    </Snackbar>
  );
};

export default TimerFailureNotice;
