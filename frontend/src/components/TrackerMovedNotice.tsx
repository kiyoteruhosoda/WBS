import React from 'react';
import { Alert, Box, Button } from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { useLocation } from 'react-router-dom';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import { trackerHostOf, trackerLinkOf } from '../tracker/trackerMove';
import { useTrackerMove } from '../tracker/useTrackerMove';

/**
 * 「記録は Tracker に移りました」の案内（task #526 / ADR-0053）。押すと Tracker の同じ画面を開く。
 * 締め・規則の画面はこれに替わり、「今日」は打刻の欄の代わりに出す。
 */
export const TrackerMovedNotice: React.FC<{ url: string; bodyKey: TranslationKey; path?: string; sx?: object }> = ({
  url, bodyKey, path = '/', sx,
}) => {
  const { t } = useI18n();
  return (
    <Alert
      severity="info"
      data-testid="tracker-moved"
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
          href={trackerLinkOf(url, path)}
          target="_blank"
          rel="noopener"
          endIcon={<OpenInNewIcon sx={{ fontSize: 14 }} />}
          sx={{ whiteSpace: 'nowrap', flexShrink: 0, minHeight: 40 }}
        >
          {t('tracker.openPage')}
        </Button>
      )}
    >
      <Box sx={{ fontWeight: 700 }}>{t('tracker.movedTitle')}</Box>
      <Box sx={{ fontSize: 13 }}>{t(bodyKey, { host: trackerHostOf(url) })}</Box>
    </Alert>
  );
};

/** 打刻まわりの画面（締め・規則）。移した後は Tracker の同じ画面への案内に替える */
export const MovedToTrackerGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { moved, url } = useTrackerMove();
  const location = useLocation();
  if (!moved) return <>{children}</>;
  return <TrackerMovedNotice url={url} bodyKey="tracker.movedBody" path={`${location.pathname}${location.search}`} />;
};
