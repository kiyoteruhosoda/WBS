import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, ClickAwayListener } from '@mui/material';
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
import type { CalendarInteractions, TaskDropPreview } from './calendarInteractions';
import type { LinkedTask } from '../../calendar/taskScheduling';
import type { CalendarDeadline } from '../../calendar/taskDeadlines';
import { groupDeadlinesByDate } from '../../calendar/taskDeadlines';
import type { DayTapTarget } from '../../calendar/dayPanel';
import { nextSelectedDate } from '../../calendar/dayPanel';

// 日の一覧の外を押したとき、閉じずに残す場所: 日付の見出し・月のマス（押した日へ移す・同じ日なら閉じるのは
// そちらの仕事）と、一覧から開いたダイアログ・メニュー（MUI はポータルで body の直下に出す）。
const KEEP_PANEL_SELECTOR = '[data-day-select], .MuiModal-root, .MuiPopover-root, .MuiPopper-root';

export interface SchedulerCalendarProps extends CalendarInteractions {
  /** 表示している期間の回（API の応答をそのまま） */
  occurrences: readonly CalendarOccurrence[];
  holidays?: readonly CalendarHoliday[];
  /** タスク・マイルストーンの期限（終日の帯に、予定とは違う見た目で出す） */
  deadlines?: readonly CalendarDeadline[];
  /** 閲覧者のタイムゾーン（利用者設定）。省くとブラウザのもの */
  timeZone?: string | null;
  initialMode?: CalendarMode;
  /** 固定の「今」（試験用）。省くと 1 分ごとに進む時計 */
  now?: Date;
  /** 表示する期間が変わった（API に問い直す口。両端を含む閲覧者のローカル日） */
  onVisibleRangeChange?: (range: { from: string; to: string }) => void;
  /** 予定に結んだタスクの印（色・題名。task #159） */
  linkedTasks?: ReadonlyMap<number, LinkedTask>;
  /** タスクの一覧から週表示へ引いている途中の行き先 */
  dropPreview?: TaskDropPreview | null;
  /** 曜日の休み（営業日の層が表示のとき。ADR-0029） */
  nonWorkdays?: ReadonlySet<string> | null;
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
const EMPTY_DEADLINES: readonly CalendarDeadline[] = [];

/**
 * カレンダー（月・週・平日）。移植元 NolumiaScheduler の CalendarPage に寄せた外枠。
 * データの取り方は持たない（`occurrences` を受けて描くだけ）。
 */
const SchedulerCalendar: React.FC<SchedulerCalendarProps> = ({
  occurrences, holidays = EMPTY_HOLIDAYS, deadlines = EMPTY_DEADLINES, timeZone: requestedTimeZone, initialMode = 'week', now: fixedNow,
  onVisibleRangeChange, linkedTasks, dropPreview, nonWorkdays, ...interactions
}) => {
  const { t, weekdays, lang } = useI18n();
  const c = useTheme().palette.calendar;
  const timeZone = resolveTimeZone(requestedTimeZone);
  const nowMs = useClock(fixedNow);
  const { date: today, minute: nowMinute } = toZonedPoint(nowMs, timeZone);

  const [position, setPosition] = useState<CalendarPosition>(() => initialPosition(initialMode, today));
  // 日の一覧（SelectedDayPanel）を開いている日。開くのは日付の見出し・月のマスを押したときだけ（ADR-0034）
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

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
  const deadlinesByDate = useMemo(() => groupDeadlinesByDate(deadlines), [deadlines]);
  const dates = useMemo(() => visibleDates(position), [position]);

  const clearSelection = () => setSelectedDate(null);
  const move = (next: CalendarPosition) => {
    clearSelection();
    setPosition(next);
  };
  const tapDate = (target: DayTapTarget) => (date: string) => setSelectedDate((current) => nextSelectedDate(current, target, date));
  // 予定・タスクのブロックは押せば編集を開く（「今日」と同じ。ADR-0022）。日の一覧は開かない
  const openSegment = (segment: DaySegment) => interactions.onEditOccurrence?.(segment.occurrence);

  // Esc で日の一覧を閉じる（一覧から開いたダイアログの Esc はダイアログだけを閉じる）
  useEffect(() => {
    if (!selectedDate) return undefined;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return;
      if (e.target instanceof Element && e.target.closest('.MuiModal-root')) return;
      if (document.querySelector('.MuiModal-root')) return;
      setSelectedDate(null);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [selectedDate]);

  const onClickAway = (e: MouseEvent | TouchEvent) => {
    if (e.target instanceof Element && e.target.closest(KEEP_PANEL_SELECTOR)) return;
    clearSelection();
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
            cells={buildMonthCells(position.month, today, segmentsByDate, holidays, deadlinesByDate)}
            selectedDate={selectedDate}
            timeZone={timeZone}
            onSelectDate={tapDate('month-cell')}
            linkedTasks={linkedTasks}
            nonWorkdays={nonWorkdays}
          />
        ) : (
          <WeekView
            dates={dates}
            timeZone={timeZone}
            segmentsByDate={segmentsByDate}
            holidays={holidays}
            deadlines={deadlines}
            today={today}
            nowMinute={nowMinute}
            selectedDate={selectedDate}
            selectedSegmentKey={null}
            onSelectDate={tapDate('day-header')}
            onSelectSegment={openSegment}
            onCreateRange={interactions.onCreateRange}
            onRescheduleOccurrence={interactions.onRescheduleOccurrence}
            onCreateEvent={interactions.onCreateEvent}
            onToggleDone={interactions.onToggleDone}
            onOpenDeadline={interactions.onOpenDeadline}
            linkedTasks={linkedTasks}
            dropPreview={dropPreview}
            nonWorkdays={nonWorkdays}
          />
        )}
      </Box>
      {selectedDate && (
        <ClickAwayListener onClickAway={onClickAway} touchEvent={false}>
        <SelectedDayPanel
          date={selectedDate}
          segments={segmentsByDate.get(selectedDate) ?? []}
          deadlines={deadlinesByDate.get(selectedDate) ?? []}
          holidays={holidays}
          timeZone={timeZone}
          selectedSegmentKey={null}
          onClose={clearSelection}
          onCreateEvent={interactions.onCreateEvent}
          onEditOccurrence={interactions.onEditOccurrence}
          onDeleteOccurrence={interactions.onDeleteOccurrence}
          onToggleDone={interactions.onToggleDone}
          onOpenDeadline={interactions.onOpenDeadline}
          linkedTasks={linkedTasks}
        />
        </ClickAwayListener>
      )}
    </Box>
  );
};

export default SchedulerCalendar;
