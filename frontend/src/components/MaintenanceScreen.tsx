import React, { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { Box, Button, CircularProgress, Paper, Typography } from '@mui/material';
import { ds } from '../theme';
import { storedLang, translate } from '../i18n';
import { currentOutage, subscribeOutage, type Outage } from '../pwa/maintenance';

/**
 * The "under maintenance" / "stopped" screen (task #655, ADR-0075).
 *
 * Shown instead of the app while the edge says it is closed. Heading and text are the edge's declaration;
 * when missing (older edges) the app's own text is used. The expected return time is drawn in the viewer's time zone
 * with its UTC offset.
 *
 * Re-checks every minute and whenever the tab comes back to the front. Once open, the state clears and
 * `main.tsx` shows the app again. The check is passed in (tests pass a fake).
 * It sits outside sign-in and user settings, so its text comes from `translate`.
 */

/** How often to re-check. */
export const RECHECK_INTERVAL_MS = 60 * 1000;

type Check = () => Promise<unknown>;

/** "UTC+9" / "UTC+5:30" / "UTC" for the given date in the viewer's time zone. */
export const utcOffsetLabel = (at: Date): string => {
  const minutes = -at.getTimezoneOffset();
  if (minutes === 0) return 'UTC';
  const sign = minutes > 0 ? '+' : '-';
  const hours = Math.floor(Math.abs(minutes) / 60);
  const rest = Math.abs(minutes) % 60;
  return `UTC${sign}${hours}${rest ? `:${String(rest).padStart(2, '0')}` : ''}`;
};

/** Expected return in the viewer's time zone. Null for an unreadable value. */
export const formatUntil = (until: string | null, locale: string): string | null => {
  if (!until) return null;
  const at = new Date(until);
  if (Number.isNaN(at.getTime())) return null;
  const local = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(at);
  return `${local} (${utcOffsetLabel(at)})`;
};

const useRecheck = (check: Check): [boolean, () => void] => {
  const [checking, setChecking] = useState(false);

  const run = useCallback(() => {
    setChecking(true);
    void check().finally(() => setChecking(false));
  }, [check]);

  useEffect(() => {
    const timer = window.setInterval(() => void check(), RECHECK_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void check();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [check]);

  return [checking, run];
};

export const MaintenanceScreen: React.FC<{ outage: Outage; check: Check }> = ({ outage, check }) => {
  const [checking, recheck] = useRecheck(check);
  const stopped = outage.reason === 'stopped';
  const until = formatUntil(outage.until, storedLang() === 'en' ? 'en-US' : 'ja-JP');

  return (
    <Box
      component="main"
      role="alert"
      sx={{ minHeight: '100svh', display: 'grid', placeItems: 'center', p: '16px', bgcolor: ds.canvas }}
    >
      <Paper variant="outlined" sx={{ width: '100%', maxWidth: '32rem', p: '24px', borderColor: ds.border }}>
        <Typography component="h1" sx={{ fontSize: '1.4rem', fontWeight: 700, mb: '12px', color: ds.text }}>
          {outage.title ?? translate(stopped ? 'maintenance.stoppedTitle' : 'maintenance.title')}
        </Typography>
        <Typography sx={{ mb: '12px', overflowWrap: 'anywhere', color: ds.text }}>
          {outage.body ?? translate(stopped ? 'maintenance.stoppedBody' : 'maintenance.body')}
        </Typography>
        {outage.message && (
          <Typography sx={{ mb: '12px', fontSize: '0.9rem', color: ds.textSub, overflowWrap: 'anywhere' }}>
            {translate('maintenance.reason', { reason: outage.message })}
          </Typography>
        )}
        {until && (
          <Typography sx={{ mb: '12px', fontWeight: 600, color: ds.text }}>
            {translate('maintenance.until', { time: until })}
          </Typography>
        )}
        <Typography sx={{ mb: '16px', fontSize: '0.9rem', color: ds.textSub }}>
          {translate('maintenance.autoCheck')}
        </Typography>
        <Button
          variant="outlined"
          onClick={recheck}
          disabled={checking}
          startIcon={checking ? <CircularProgress size={16} /> : undefined}
        >
          {translate('maintenance.checkNow')}
        </Button>
      </Paper>
    </Box>
  );
};

/** Renders the screen only while closed. */
export const MaintenanceGate: React.FC<{ check: Check }> = ({ check }) => {
  const outage = useSyncExternalStore(subscribeOutage, currentOutage);
  if (!outage) return null;
  return <MaintenanceScreen outage={outage} check={check} />;
};
