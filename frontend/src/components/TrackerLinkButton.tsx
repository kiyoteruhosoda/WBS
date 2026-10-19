import React, { useEffect } from 'react';
import { Button, Tooltip } from '@mui/material';
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
          sx={{ minHeight: 44, whiteSpace: 'nowrap', flexShrink: 0, fontWeight: 700 }}
        >
          {t('tracker.open')}
        </Button>
      </Tooltip>
      <PressNoticeView notice={notice} onClose={clear} />
    </>
  );
};

export default TrackerLinkButton;
