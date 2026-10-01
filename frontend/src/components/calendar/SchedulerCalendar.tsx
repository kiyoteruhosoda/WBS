import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useI18n } from '../../i18n';
import type { CalendarHoliday, CalendarOccurrence } from '../../types';
import type { CalendarMode, CalendarPosition } from '../../calendar/calendarNavigation';
import {
  containsDate, goToday, initialPosition, navigate, switchMode, visibleDates, visibleRange,
} from '../../calendar/calendarNavigation';
import type { DaySegment } from '../../calendar/daySegments';
import { groupSegmentsByDate } from '../../calendar/daySegments';
import { buildMonthCells } from '../../calendar/monthCells';
import { formatCalendarTitle } from '../../calendar/calendarTitles';
import { resolveTimeZone, toZonedPoint } from '../../calendar/zonedTime';
import CalendarHeader from './CalendarHeader';
import MonthView from './MonthView';
import WeekView from './WeekView';
import SelectedDayPanel from './SelectedDayPanel';
import type { CalendarInteractions } from './calendarInteractions';

export interface SchedulerCalendarProps extends CalendarInteractions {
  /** 表示している期間の回（API の応答をそのまま） */
  occurrences: readonly CalendarOccurrence[];
  holidays?: readonly CalendarHoliday[];
  /** 閲覧者のタイムゾーン（利用者設定）。省くとブラウザのもの */
  timeZone?: string | null;
  initialMode?: CalendarMode;
  /** 固定の「今」（見本・試験用）。省くと 1 分ごとに進む時計 */
  now?: Date;
  /** 表示する期間が変わった（API に問い直す口。両端を含む閲覧者のローカル日） */
  onVisibleRangeChange?: (range: { from: string; to: string }) => void;
}

const useClock = (fixed: Date | undefined): number => {
  const [live, setLive] = useState(() => Date.now());
  useEffect(() => {
    if (fixed) return;
    const id = window.setInterval(() => setLive(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, [fixed]);
  return fixed ? fixed.getTime() : live;
};

const EMPTY_HOLIDAYS: readonly CalendarHoliday[] = [];

/**
 * カレンダー（月・週・平日）。移植元 NolumiaScheduler の CalendarPage に寄せた外枠。
 * データの取り方は持たない（`occurrences` を受けて描くだけ）。
 */
const SchedulerCalendar: React.FC<SchedulerCalendarProps> = ({
  occurrences, holidays = EMPTY_HOLIDAYS, timeZone: requestedTimeZone, initialMode = 'week', now: fixedNow,
  onVisibleRangeChange, ...interactions
}) => {
  const { t, weekdays, lang } = useI18n();
  const c = useTheme().palette.calendar;
  const timeZone = resolveTimeZone(requestedTimeZone);
  const nowMs = useClock(fixedNow);
  const { date: today, minute: nowMinute } = toZonedPoint(nowMs, timeZone);

  const [position, setPosition] = useState<CalendarPosition>(() => initialPosition(initialMode, today));
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedSegmentKey, setSelectedSegmentKey] = useState<string | null>(null);

  // 日付が変わったとき、今週を見ていたら新しい週へ送る（移植元 RefreshCurrentTime）。
  const previousToday = useRef(today);
  useEffect(() => {
    const before = previousToday.current;
    previousToday.current = today;
    if (before === today) return;
    setPosition((p) => (p.mode !== 'month' && containsDate(p, before) ? goToday(p, today) : p));
  }, [today]);

  const range = useMemo(() => visibleRange(position), [position]);
  useEffect(() => {
    onVisibleRangeChange?.(range);
  }, [range, onVisibleRangeChange]);

  const segmentsByDate = useMemo(() => groupSegmentsByDate(occurrences, timeZone), [occurrences, timeZone]);
  const dates = useMemo(() => visibleDates(position), [position]);

  const clearSelection = () => {
    setSelectedDate(null);
    setSelectedSegmentKey(null);
  };
  const move = (next: CalendarPosition) => {
    clearSelection();
    setPosition(next);
  };
  const selectDate = (date: string) => {
    setSelectedDate(date);
    setSelectedSegmentKey(null);
  };
  const selectSegment = (segment: DaySegment) => {
    setSelectedDate(segment.date);
    setSelectedSegmentKey(segment.key);
  };

  return (
    <Box
      data-testid="scheduler-calendar"
      data-mode={position.mode}
      sx={{
        display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0,
        bgcolor: c.surface, color: c.textPrimary, border: `1px solid ${c.border}`, borderRadius: '10px', overflow: 'hidden',
      }}
    >
      <CalendarHeader
        mode={position.mode}
        title={formatCalendarTitle(position, t, weekdays, lang)}
        onModeChange={(mode) => setPosition((p) => switchMode(p, mode))}
        onPrev={() => move(navigate(position, -1))}
        onNext={() => move(navigate(position, 1))}
        onToday={() => move(goToday(position, today))}
        onUndo={interactions.onUndo}
        onRedo={interactions.onRedo}
        canUndo={interactions.canUndo}
        canRedo={interactions.canRedo}
      />
      <Box sx={{ height: '1px', bgcolor: c.border, flexShrink: 0 }} />
      <Box sx={{ flex: 1, minHeight: 0, overflow: position.mode === 'month' ? 'auto' : 'hidden' }}>
        {position.mode === 'month' ? (
          <MonthView
            cells={buildMonthCells(position.month, today, segmentsByDate, holidays)}
            selectedDate={selectedDate}
            timeZone={timeZone}
            onSelectDate={selectDate}
          />
        ) : (
          <WeekView
            dates={dates}
            timeZone={timeZone}
            segmentsByDate={segmentsByDate}
            holidays={holidays}
            today={today}
            nowMinute={nowMinute}
            selectedDate={selectedDate}
            selectedSegmentKey={selectedSegmentKey}
            onSelectDate={selectDate}
            onSelectSegment={selectSegment}
            onCreateRange={interactions.onCreateRange}
            onRescheduleOccurrence={interactions.onRescheduleOccurrence}
            onEditOccurrence={interactions.onEditOccurrence}
            onCreateEvent={interactions.onCreateEvent}
          />
        )}
      </Box>
      {selectedDate && (
        <SelectedDayPanel
          date={selectedDate}
          segments={segmentsByDate.get(selectedDate) ?? []}
          holidays={holidays}
          timeZone={timeZone}
          selectedSegmentKey={selectedSegmentKey}
          onClose={clearSelection}
          onCreateEvent={interactions.onCreateEvent}
          onEditOccurrence={interactions.onEditOccurrence}
          onDeleteOccurrence={interactions.onDeleteOccurrence}
        />
      )}
    </Box>
  );
};

export default SchedulerCalendar;
