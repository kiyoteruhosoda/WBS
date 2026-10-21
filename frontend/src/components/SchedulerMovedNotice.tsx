import React from 'react';
import { Alert, Box, Button } from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { useLocation } from 'react-router-dom';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import { schedulerHostOf, schedulerLinkOf } from '../scheduler/schedulerMove';
import { useSchedulerMove } from '../scheduler/useSchedulerMove';

/**
 * 「予定は Scheduler に移りました」の案内（task #535 / ADR-0054。TrackerMovedNotice と同じ形）。押すと Scheduler の同じ画面を開く。
 * カレンダー・カレンダーの設定の画面はこれに替わり、「今日」は予定の欄の代わりに、実績の画面は上に出す。
 */
export const SchedulerMovedNotice: React.FC<{ url: string; bodyKey: TranslationKey; path?: string; sx?: object }> = ({
  url, bodyKey, path = '/', sx,
}) => {
  const { t } = useI18n();
  return (
    <Alert
      severity="info"
      data-testid="scheduler-moved"
      sx={{
        alignItems: 'center',
        // スマホの幅ではボタンを本文の下へ（右に置くと本文が細い列に押し込まれ、宛先が切れる。task #640）
        flexWrap: { xs: 'wrap', sm: 'nowrap' },
        '& .MuiAlert-message': { flex: { xs: '1 1 0', sm: '0 1 auto' }, minWidth: 0, overflowWrap: 'anywhere' },
        '& .MuiAlert-action': { pt: 0, alignItems: 'center', ml: { xs: '34px', sm: 'auto' }, flexBasis: { xs: '100%', sm: 'auto' } },
        ...sx,
      }}
      action={(
        <Button
          color="inherit"
          size="small"
          href={schedulerLinkOf(url, path)}
          target="_blank"
          rel="noopener"
          endIcon={<OpenInNewIcon sx={{ fontSize: 14 }} />}
          sx={{ whiteSpace: 'nowrap', flexShrink: 0, minHeight: 40 }}
        >
          {t('scheduler.openPage')}
        </Button>
      )}
    >
      <Box sx={{ fontWeight: 700 }}>{t('scheduler.movedTitle')}</Box>
      <Box sx={{ fontSize: 13 }}>{t(bodyKey, { host: schedulerHostOf(url) })}</Box>
    </Alert>
  );
};

/** 予定まわりの画面（カレンダー・カレンダーの設定）。移した後は Scheduler の同じ画面への案内に替える */
export const MovedToSchedulerGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { moved, url } = useSchedulerMove();
  const location = useLocation();
  if (!moved) return <>{children}</>;
  return <SchedulerMovedNotice url={url} bodyKey="scheduler.movedBody" path={`${location.pathname}${location.search}`} />;
};
