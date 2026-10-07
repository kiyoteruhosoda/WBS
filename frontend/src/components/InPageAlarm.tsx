import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, Button } from '@mui/material';
import { getAlarms } from '../api/calendar';
import type { CalendarAlarm } from '../api/calendar';
import {
  FETCH_EVERY_MS, alarmWindow, blinkingTitle, dueAlarms, noticeLead, withNotice,
} from '../alarms/inPageAlarm';
import { Chime, claimRingOnThisDevice, openAlarmChannel, startTicker } from '../alarms/browserAlarm';
import { usePushCoversAlarms } from '../alarms/usePushCoversAlarms';
import { useInPageAlarmSetting } from '../preferences/inPageAlarm';
import { useClockStyle } from '../preferences/clockStyle';
import { formatClockTime } from '../clock/clockFace';
import { resolveTimeZone, toZonedPoint } from '../calendar/zonedTime';
import { useI18n } from '../i18n';
import { ds } from '../theme';

/** 音を出せないタブは、出せるタブに先を譲ってから鳴らす役を取りに行く */
const YIELD_TO_AUDIBLE_TAB_MS = 3000;

/**
 * 画面の中で予定を知らせる（task #312、ADR-0041）。ブラウザの通知が使えない端末でも、WBS を開いている間は
 * 予定の通知の時刻に画面の上へ知らせを出し、音を鳴らし、裏のタブなら題名を点滅させる。
 * 設定の「画面の中で知らせる」を切った端末と、Web Push で受け取っている端末では何もしない。
 */
const InPageAlarm: React.FC = () => {
  const { t, timezone } = useI18n();
  const { style } = useClockStyle();
  const { enabled } = useInPageAlarmSetting();
  const covered = usePushCoversAlarms();
  const active = enabled && !covered;

  const [shown, setShown] = useState<CalendarAlarm[]>([]);
  const [soundBlocked, setSoundBlocked] = useState(false);

  const activeRef = useRef(active);
  const alarmsRef = useRef<CalendarAlarm[]>([]);
  const lastFetchRef = useRef(0);
  const fetchingRef = useRef(false);
  const seenRef = useRef(new Set<string>());
  const shownRef = useRef<CalendarAlarm[]>([]);
  const beatRef = useRef(0);
  const originalTitleRef = useRef<string | null>(null);
  const [chime] = useState(() => new Chime());
  const channelRef = useRef<ReturnType<typeof openAlarmChannel> | null>(null);

  useEffect(() => {
    shownRef.current = shown;
  }, [shown]);

  useEffect(() => {
    activeRef.current = active;
    if (active) lastFetchRef.current = 0; // 入れたらすぐ引く
    else setShown([]);
  }, [active]);

  // 画面を押したら音を出せるようにしておく（ブラウザは押した後でないと音を出させない）
  useEffect(() => {
    const unlock = () => {
      chime.unlock();
      setSoundBlocked(false);
    };
    window.addEventListener('pointerdown', unlock);
    window.addEventListener('keydown', unlock);
    return () => {
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
    };
  }, [chime]);

  useEffect(() => {
    const channel = openAlarmChannel(({ occurrenceId, alarmId }) => {
      seenRef.current.add(alarmId);
      setShown((current) => current.filter((notice) => notice.occurrence_id !== occurrenceId));
    });
    channelRef.current = channel;
    return () => channel.close();
  }, []);

  const ring = useCallback(async (alarm: CalendarAlarm) => {
    if (!chime.ready) await new Promise((resolve) => { window.setTimeout(resolve, YIELD_TO_AUDIBLE_TAB_MS); });
    if (!(await claimRingOnThisDevice(alarm.id, Date.now()))) return;
    if (!(await chime.play())) setSoundBlocked(true);
  }, [chime]);

  const fetchAlarms = useCallback(async (nowMs: number) => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    lastFetchRef.current = nowMs;
    try {
      alarmsRef.current = await getAlarms(alarmWindow(nowMs));
    } catch {
      // 引けなければ前の一覧のまま（先の 20 分を持っている）
    } finally {
      fetchingRef.current = false;
    }
  }, []);

  const blink = useCallback(() => {
    const notices = shownRef.current;
    const watching = document.visibilityState === 'visible' && document.hasFocus();
    if (notices.length === 0 || watching) {
      if (originalTitleRef.current != null) {
        document.title = originalTitleRef.current;
        originalTitleRef.current = null;
      }
      return;
    }
    originalTitleRef.current ??= document.title;
    beatRef.current += 1;
    document.title = blinkingTitle(originalTitleRef.current, `🔔 ${notices[notices.length - 1].title}`, beatRef.current);
  }, []);

  useEffect(() => {
    const tick = () => {
      blink();
      if (!activeRef.current) return;
      const now = Date.now();
      if (now - lastFetchRef.current >= FETCH_EVERY_MS) void fetchAlarms(now);
      for (const alarm of dueAlarms(alarmsRef.current, now, seenRef.current)) {
        seenRef.current.add(alarm.id);
        setShown((current) => withNotice(current, alarm));
        void ring(alarm);
      }
    };
    // 表に戻ったら引き直す（裏にいた間に予定が変わっているかもしれない）
    const onVisible = () => {
      if (document.visibilityState === 'visible') lastFetchRef.current = 0;
    };
    document.addEventListener('visibilitychange', onVisible);
    const stop = startTicker(tick);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisible);
      if (originalTitleRef.current != null) document.title = originalTitleRef.current;
    };
  }, [blink, fetchAlarms, ring]);

  const dismiss = (alarm: CalendarAlarm) => {
    setShown((current) => current.filter((notice) => notice.occurrence_id !== alarm.occurrence_id));
    channelRef.current?.post({ type: 'dismiss', occurrenceId: alarm.occurrence_id, alarmId: alarm.id });
  };

  if (shown.length === 0) return null;

  const zone = resolveTimeZone(timezone);
  const startTime = (alarm: CalendarAlarm) => formatClockTime(
    toZonedPoint(Date.parse(alarm.starts_at), zone).minute, style, { am: t('clock.am'), pm: t('clock.pm') },
  );

  return (
    <Box
      sx={{
        position: 'fixed', top: 'calc(12px + env(safe-area-inset-top))', left: '50%', transform: 'translateX(-50%)',
        zIndex: 1500, width: 'min(440px, calc(100vw - 32px))', display: 'flex', flexDirection: 'column', gap: '8px',
      }}
    >
      {shown.map((alarm) => {
        const lead = noticeLead(alarm);
        return (
          <Box
            key={alarm.occurrence_id}
            role="alert"
            sx={{
              bgcolor: ds.paper, border: `2px solid ${ds.primary}`, borderRadius: '12px',
              boxShadow: '0 10px 32px rgba(0,0,0,0.28)', p: '14px 16px',
              display: 'flex', flexDirection: 'column', gap: '6px',
            }}
          >
            <Box sx={{ fontSize: 12, fontWeight: 700, color: ds.primary }}>
              {'🔔 '}
              {t(lead.key, lead.params)}
            </Box>
            <Box sx={{ fontSize: 17, fontWeight: 700, color: ds.text, overflowWrap: 'anywhere' }}>{alarm.title}</Box>
            <Box sx={{ fontSize: 13, color: ds.textSub }}>
              {t('inPageAlarm.startsAt', { time: startTime(alarm) })}
              {alarm.location ? ` ・ ${alarm.location}` : ''}
            </Box>
            {soundBlocked && <Box sx={{ fontSize: 12, color: ds.textSub }}>{t('inPageAlarm.soundBlocked')}</Box>}
            <Button
              variant="contained"
              size="small"
              onClick={() => dismiss(alarm)}
              sx={{ alignSelf: 'flex-end', minHeight: 36, px: '18px' }}
            >
              {t('inPageAlarm.dismiss')}
            </Button>
          </Box>
        );
      })}
    </Box>
  );
};

export default InPageAlarm;
