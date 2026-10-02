import React from 'react';
import { Alert, Box, Snackbar } from '@mui/material';
import { useI18n } from '../i18n';
import type { PressNotice } from '../timer/useTimer';

/**
 * 端末に溜めた打刻（Start / Stop）を送った結果の知らせ（task #192・ADR-0028）。
 * - failure: 端末に残せなかった（押下は記録されていない。もう一度押してもらう）
 * - kept: つながっているのに送れなかった（5xx 等）。端末に残してあり、あとで送り直す（押し直さなくてよい）
 * - dropped: サーバが受け取らなかった（重なり・確定済みの締めの期間・7 日より前）。捨てたので締めの画面で直す
 * つながらないだけのときは知らせない（打刻ボタンの横の「未送信 n 件」で足りる）。
 */
const PressNoticeView: React.FC<{ notice: PressNotice | null; onClose: () => void }> = ({ notice, onClose }) => {
  const { t } = useI18n();
  const severity = notice?.kind === 'kept' ? 'info' : 'warning';
  const text = (() => {
    switch (notice?.kind) {
      case 'failure': return t('timer.error');
      case 'kept': return t('timer.kept');
      case 'dropped': return t('timer.dropped', { count: notice.count });
      default: return '';
    }
  })();
  return (
    <Snackbar
      open={notice != null}
      autoHideDuration={notice?.kind === 'dropped' ? 15000 : 6000}
      onClose={onClose}
      anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
    >
      <Alert severity={notice?.kind === 'failure' ? 'error' : severity} onClose={onClose} sx={{ width: '100%' }}>
        {text}
        {notice?.kind === 'dropped' && notice.detail && (
          <Box component="span" sx={{ display: 'block', mt: '4px', fontSize: 12, opacity: 0.85 }}>{notice.detail}</Box>
        )}
      </Alert>
    </Snackbar>
  );
};

export default PressNoticeView;
