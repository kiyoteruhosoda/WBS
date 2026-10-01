import React, { useMemo, useState } from 'react';
import { Alert, Box, FormControlLabel, Switch } from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import { darkTheme, theme } from '../theme';
import { useI18n } from '../i18n';
import type { CalendarHoliday, CalendarOccurrence, EventColorKey } from '../types';
import SchedulerCalendar from '../components/calendar/SchedulerCalendar';
import { sundayOf } from '../calendar/calendarNavigation';
import { addDays, firstOfMonth, formatMinute, fromZonedPoint, resolveTimeZone, toZonedPoint } from '../calendar/zonedTime';
import type { OperationHistory } from '../calendar/operationHistory';
import {
  canRedo, canUndo, emptyHistory, recordOperation, redoOperation, undoOperation,
} from '../calendar/operationHistory';
import { formatTimingRange } from '../calendar/weekGestures';
import type { CreateRange, OccurrenceReschedule } from '../components/calendar/calendarInteractions';

// 確かめ用の見本ページ（task #157 第 1 段・#158）。予定の API ができたら CalendarPage を置き換えて、このページは消す。
// ドラッグの意図は API の代わりにこのページの状態へ当てる（元に戻す・やり直しもこのページの履歴）。

/** 見本ページの 1 操作: 回を `before` から `after` へ（null は「無い」。作ったときの before）。 */
interface PreviewOperation {
  id: string;
  before: CalendarOccurrence | null;
  after: CalendarOccurrence | null;
}

const putOccurrence = (list: readonly CalendarOccurrence[], id: string, value: CalendarOccurrence | null): CalendarOccurrence[] => {
  const rest = list.filter((o) => o.id !== id);
  return value ? [...rest, value] : rest;
};

interface PreviewState {
  base: readonly CalendarOccurrence[];
  occurrences: CalendarOccurrence[];
  history: OperationHistory<PreviewOperation>;
  created: number;
}

const freshState = (base: readonly CalendarOccurrence[]): PreviewState => ({
  base, occurrences: [...base], history: emptyHistory<PreviewOperation>(), created: 0,
});

interface SampleSpec {
  eventId: number;
  title: string;
  date: string;
  startMinute: number;
  durationMinutes: number;
  color?: EventColorKey;
  location?: string;
  recurring?: boolean;
  moved?: boolean;
}

const toOccurrence = (s: SampleSpec, timeZone: string): CalendarOccurrence => {
  const isAllDay = s.startMinute === 0 && s.durationMinutes === 24 * 60;
  return {
    id: `${s.eventId}:${s.date}T${formatMinute(s.startMinute)}`,
    event_id: s.eventId,
    title: s.title,
    start: new Date(fromZonedPoint(s.date, s.startMinute, timeZone)).toISOString(),
    duration_minutes: s.durationMinutes,
    date: s.date,
    is_all_day: isAllDay,
    color_key: s.color ?? 'DEFAULT',
    location: s.location ?? null,
    task_id: null,
    is_recurring: s.recurring ?? false,
    is_moved: s.moved ?? false,
    is_overridden: false,
    series_key: s.recurring ? { date: s.date, start_time: formatMinute(s.startMinute) } : null,
  };
};

/** 今週と今月のまわりに、重なり・日またぎ・終日・長さ 0・あふれを揃えた見本。 */
const buildSamples = (today: string, timeZone: string): { occurrences: CalendarOccurrence[]; holidays: CalendarHoliday[] } => {
  const w = sundayOf(today);
  const d = (n: number) => addDays(w, n);
  const h = (hour: number, minute = 0) => hour * 60 + minute;
  const specs: SampleSpec[] = [
    // 月曜: 3 つ重なる・15 分
    { eventId: 1, title: '定例', date: d(1), startMinute: h(9), durationMinutes: 60, color: 'BLUEBERRY', recurring: true },
    { eventId: 2, title: '設計レビュー', date: d(1), startMinute: h(9, 30), durationMinutes: 90, color: 'TOMATO', location: '会議室A' },
    { eventId: 3, title: '1on1', date: d(1), startMinute: h(10), durationMinutes: 30, color: 'SAGE' },
    { eventId: 4, title: '短い確認', date: d(1), startMinute: h(13), durationMinutes: 15 },
    // 火曜: 終日・ローカル 0:00 をまたぐ
    { eventId: 5, title: '出張', date: d(2), startMinute: 0, durationMinutes: 24 * 60, color: 'BASIL' },
    { eventId: 6, title: '夜間メンテナンス', date: d(2), startMinute: h(22), durationMinutes: 240, color: 'GRAPHITE' },
    // 水曜（祝日）: 長さ 0
    { eventId: 7, title: 'リマインド', date: d(3), startMinute: h(12), durationMinutes: 0, color: 'BANANA' },
    // 木曜から 36 時間
    { eventId: 8, title: '合宿', date: d(4), startMinute: h(8), durationMinutes: 36 * 60, color: 'GRAPE', location: '研修所' },
    // 金曜: 振替
    { eventId: 1, title: '定例（振替）', date: d(5), startMinute: h(15), durationMinutes: 60, color: 'PEACOCK', recurring: true, moved: true },
    // 土曜: 終日が 2 つ
    { eventId: 9, title: '家族の用事', date: d(6), startMinute: 0, durationMinutes: 24 * 60, color: 'LAVENDER' },
    { eventId: 10, title: '誕生日', date: d(6), startMinute: 0, durationMinutes: 24 * 60, color: 'TANGERINE' },
    // 今日: 月表示で「+N 件」になる数
    ...[7, 8, 11, 14, 16, 18, 20].map((hour, i): SampleSpec => ({
      eventId: 20 + i, title: `今日の予定 ${i + 1}`, date: today, startMinute: h(hour), durationMinutes: 45,
      color: (['DEFAULT', 'SAGE', 'TOMATO', 'PEACOCK', 'BANANA', 'GRAPE', 'BASIL'] as const)[i],
    })),
    // 前後の週
    { eventId: 30, title: '先週の振り返り', date: d(-4), startMinute: h(16), durationMinutes: 60, color: 'GRAPHITE' },
    { eventId: 31, title: '来週の計画', date: d(9), startMinute: h(10), durationMinutes: 120, color: 'PEACOCK' },
  ];
  // 今月の中に 3 日おきに 1 件
  const month = firstOfMonth(today);
  for (let i = 0; i < 31; i += 3) {
    const date = addDays(month, i);
    if (firstOfMonth(date) !== month) break;
    specs.push({ eventId: 100 + i, title: `月の予定 ${i + 1}`, date, startMinute: h(19), durationMinutes: 60, color: 'LAVENDER', recurring: true });
  }
  const holidays: CalendarHoliday[] = [
    { date: d(3), name: '見本の祝日' },
    { date: d(10), name: '見本の休日' },
  ];
  return { occurrences: specs.map((s) => toOccurrence(s, timeZone)), holidays };
};

const CalendarPreviewPage: React.FC = () => {
  const { t, timezone } = useI18n();
  const timeZone = resolveTimeZone(timezone);
  const [dark, setDark] = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [openedAt] = useState(() => Date.now());
  const today = toZonedPoint(openedAt, timeZone).date;
  const samples = useMemo(() => buildSamples(today, timeZone), [today, timeZone]);
  const holidays = samples.holidays;
  const [state, setState] = useState<PreviewState>(() => freshState(samples.occurrences));
  // タイムゾーンの設定が後から届いたら、見本を作り直して履歴も捨てる。
  if (state.base !== samples.occurrences) setState(freshState(samples.occurrences));

  const report = (action: string, title: string) => setLastAction(t('calendar.previewAction', { action, title }));

  const apply = (operation: PreviewOperation, value: CalendarOccurrence | null, history: OperationHistory<PreviewOperation>) =>
    setState((s) => ({ ...s, occurrences: putOccurrence(s.occurrences, operation.id, value), history }));

  const createRange = (range: CreateRange) => {
    const n = state.created + 1;
    const created: CalendarOccurrence = {
      ...toOccurrence({
        eventId: 1000 + n, title: t('calendar.previewNewEvent'), date: range.date,
        startMinute: range.startMinute, durationMinutes: range.endMinute - range.startMinute,
      }, timeZone),
      id: `new-${n}`,
    };
    const operation: PreviewOperation = { id: created.id, before: null, after: created };
    setState((s) => ({
      ...s, created: n, occurrences: putOccurrence(s.occurrences, created.id, created), history: recordOperation(s.history, operation),
    }));
    report(t('calendar.addEvent'), `${range.date} ${formatMinute(range.startMinute)} – ${formatMinute(range.endMinute)}`);
  };

  const reschedule = (change: OccurrenceReschedule) => {
    const before = change.occurrence;
    const after: CalendarOccurrence = {
      ...before,
      start: change.after.start,
      duration_minutes: change.after.durationMinutes,
      date: change.after.date,
      is_all_day: false,
      // 繰り返しの回は「この回だけ移動」（振替の印で出す）。
      is_moved: change.scope === 'occurrence' ? true : before.is_moved,
    };
    const operation: PreviewOperation = { id: before.id, before, after };
    setState((s) => ({ ...s, occurrences: putOccurrence(s.occurrences, before.id, after), history: recordOperation(s.history, operation) }));
    const action = change.scope === 'occurrence'
      ? t('calendar.previewMovedOccurrence')
      : t(change.kind === 'move' ? 'calendar.previewMoved' : 'calendar.previewResized');
    report(action, `${before.title} ${change.after.date} ${formatTimingRange(change.after)}`);
  };

  const undo = () => {
    const step = undoOperation(state.history);
    if (!step) return;
    apply(step.entry, step.entry.before, step.history);
    report(t('calendar.undo'), (step.entry.before ?? step.entry.after)?.title ?? '');
  };

  const redo = () => {
    const step = redoOperation(state.history);
    if (!step) return;
    apply(step.entry, step.entry.after, step.history);
    report(t('calendar.redo'), (step.entry.after ?? step.entry.before)?.title ?? '');
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <Alert severity="info">{t('calendar.previewNote')}</Alert>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
        <FormControlLabel
          control={<Switch checked={dark} onChange={(e) => setDark(e.target.checked)} />}
          label={t('calendar.previewDark')}
        />
        <Box sx={{ fontSize: 13, color: 'text.secondary' }}>{timeZone}</Box>
        {lastAction && <Box data-testid="preview-last-action" sx={{ fontSize: 13 }}>{lastAction}</Box>}
      </Box>
      <ThemeProvider theme={dark ? darkTheme : theme}>
        <Box sx={{ height: { xs: 'calc(100vh - 200px)', md: 'calc(100vh - 220px)' }, minHeight: 640 }}>
          <SchedulerCalendar
            occurrences={state.occurrences}
            holidays={holidays}
            timeZone={timeZone}
            onCreateEvent={(date, minute) => report(t('calendar.addEvent'), minute == null ? date : `${date} ${formatMinute(minute)}`)}
            onEditOccurrence={(o) => report(t('calendar.editEvent'), o.title)}
            onDeleteOccurrence={(o) => report(t('calendar.deleteEvent'), o.title)}
            onCreateRange={createRange}
            onRescheduleOccurrence={reschedule}
            onUndo={undo}
            onRedo={redo}
            canUndo={canUndo(state.history)}
            canRedo={canRedo(state.history)}
          />
        </Box>
      </ThemeProvider>
    </Box>
  );
};

export default CalendarPreviewPage;
