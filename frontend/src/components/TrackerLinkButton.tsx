import React, { useEffect } from 'react';
import { Box, Button, Tooltip } from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { useI18n } from '../i18n';
import { trackerHostOf, trackerLinkOf } from '../tracker/trackerMove';
import { usePendingPresses, usePressNotice, useTimerWrites } from '../timer/useTimer';
import PressNoticeView from './PressNotice';

/**
 * 打刻を Tracker へ移した後の、上部の打刻ボタンの代わり（task #526 / ADR-0053）。押すと Tracker を開く。
 *
 * 移す前に端末へ溜めた打刻があれば 1 度だけ送る。サーバは 409（Tracker に移りました）で断るので、
 * 「記録できませんでした」と理由を出して捨てる（黙って溜めたままにしない）。
 */
const TrackerLinkButton: React.FC<{ url: string }> = ({ url }) => {
  const { t } = useI18n();
  const pending = usePendingPresses();
  const { sendPending } = useTimerWrites();
  const { notice, clear } = usePressNotice();
  const hasPending = pending.length > 0;

  useEffect(() => {
    if (hasPending && navigator.onLine) void sendPending();
  }, [hasPending, sendPending]);

  return (
    <>
      <Tooltip title={t('tracker.openHint', { host: trackerHostOf(url) })} enterTouchDelay={0}>
        <Button
          variant="outlined"
          color="success"
          href={trackerLinkOf(url)}
          target="_blank"
          rel="noopener"
          endIcon={<OpenInNewIcon sx={{ fontSize: 16 }} />}
          aria-label={t('tracker.open')}
          sx={{ minHeight: 44, whiteSpace: 'nowrap', flexShrink: 0, fontWeight: 700, px: { xs: '10px', sm: '20px' } }}
        >
          {/* スマホ幅は短く（上の帯を 390px に収める。task #639） */}
          <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>{t('tracker.open')}</Box>
          <Box component="span" sx={{ display: { xs: 'inline', sm: 'none' } }}>{t('tracker.openShort')}</Box>
        </Button>
      </Tooltip>
      <PressNoticeView notice={notice} onClose={clear} />
    </>
  );
};

export default TrackerLinkButton;
