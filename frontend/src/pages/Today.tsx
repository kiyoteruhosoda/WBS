import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, ButtonBase, CircularProgress, IconButton, Tooltip, useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import AddIcon from '@mui/icons-material/Add';
import UndoIcon from '@mui/icons-material/Undo';
import RedoIcon from '@mui/icons-material/Redo';
import CheckBoxIcon from '@mui/icons-material/CheckBox';
import CheckBoxOutlineBlankIcon from '@mui/icons-material/CheckBoxOutlineBlank';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import type { CalendarOccurrence, Category, Task, TimeEntry, TodaySummary } from '../types';
import { TODAY_SUMMARY_KEY, getTodaySummary } from '../api/today';
import { getOccurrences } from '../api/calendar';
import { getTasks } from '../api/tasks';
import { getCategories } from '../api/categories';
import { getMilestones } from '../api/milestones';
import { getDashboardKpi } from '../api/dashboard';
import WeekView from '../components/calendar/WeekView';
import { useCalendarEditing } from '../components/calendar/useCalendarEditing';
import CategoryDot from '../components/CategoryDot';
import { useHeightToViewportBottom } from '../components/useHeightToViewportBottom';
import { PlayIcon, StopIcon } from '../components/icons';
import { categoryColor, ds } from '../theme';
import { groupSegmentsByDate } from '../calendar/daySegments';
import type { DaySegment } from '../calendar/daySegments';
import type { DayBand } from '../calendar/weekLayout';
import { buildDeadlines } from '../calendar/taskDeadlines';
import { DAY_OFF_MARKS_QUERY, OCCURRENCES_QUERY } from '../calendar/calendarQueries';
import { getDayOffMarks } from '../api/calendars';
import { buildDayOffView } from '../calendar/daysOff';
import { DEFAULT_DURATION_MINUTES } from '../calendar/eventForm';
import type { LinkedTask } from '../calendar/taskScheduling';
import { buildLinkedTasks, scheduleTaskPath } from '../calendar/taskScheduling';
import { formatMinute, resolveTimeZone, toZonedPoint } from '../calendar/zonedTime';
import { elapsedOf } from '../timer/timerState';
import type { CurrentSnapshot } from '../timer/timerState';
import { useProjectedTimeEntry, useTimerWrites } from '../timer/useTimer';
import type { TaskUrgency } from '../today/todayView';
import {
  TASKS_SHOWN_FIRST, currentAndNext, entryBands, liveActuals, nextFreeStartMinute, occurrenceStartOf, routineTasksOf,
  taskUrgencyOf,
} from '../today/todayView';
import { formatClockDuration, formatExactDuration, formatHours } from '../utils/format';

// 「今日」の画面（task #160、ADR-0015）。朝に開いて 1 画面で済むように 3 層で並べる:
//   1. いま（走っている打刻・いまの予定から Start）と、今日の予定のグリッド（打刻の帯を重ねる）
//   2. 今日やるべきタスクのうち、まだ時間を取っていないもの（押すと「時間を取る」）
//   3. 今日の実績（打刻の合計、タスク別）と全体の KPI
// スマホ幅では上から この順。広い画面では左にグリッド、右に残りを積む。
// グリッドではカレンダーの週表示と同じ操作で予定を作る・動かす・直す（task #185、ADR-0022）。
// 予定の分類が「タスク」の今日の回（毎日の定常業務など）は「今日やること」に並べ、済みのチェックと ▶ を付ける
// （task #190、ADR-0025）。無い日はこのカードを出さない。

const UNASSIGNED_COLOR = ds.todoGray;
/** グリッドを開いたとき、今の何分前を上端にするか（狭い画面でも今と次の予定が見える） */
const SCROLL_LEAD_MINUTES = 60;

const card = {
  bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', overflow: 'hidden',
} as const;
const cardHeader = {
  display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '8px',
  px: '14px', py: '10px', borderBottom: `1px solid ${ds.borderPale}`,
} as const;
const sectionTitle = { fontSize: 14, fontWeight: 700, color: ds.text } as const;
const ellipsis = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } as const;

interface SummarySnapshot {
  summary: TodaySummary;
  receivedAt: number;
}

const fetchSummary = async (): Promise<SummarySnapshot> => ({ summary: await getTodaySummary(), receivedAt: Date.now() });

/** 1 分ごと（帯の伸び・今の線・実績の足し込み）に進む時計。 */
const useMinuteClock = (): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
};

const urgencyKey: Record<TaskUrgency, TranslationKey> = {
  overdue: 'today.urgency.overdue',
  today: 'today.urgency.today',
  tomorrow: 'today.urgency.tomorrow',
  doing: 'today.urgency.doing',
  started: 'today.urgency.started',
};

// ── 1. いま ────────────────────────────────────────────────────────────

const RunningElapsed: React.FC<{ snapshot: CurrentSnapshot; entry: TimeEntry }> = ({ snapshot, entry }) => {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return <>{formatExactDuration(elapsedOf(snapshot, entry, nowMs) / 1000)}</>;
};

const NowPanel: React.FC<{
  snapshot: CurrentSnapshot | undefined;
  timeZone: string;
  totalSeconds: number;
  current: DaySegment | null;
  next: DaySegment | null;
  linkedTasks: ReadonlyMap<number, LinkedTask>;
  busy: boolean;
  /** 走っている打刻が端末に溜まった Start で、タスクをサーバに任せた（送ったときに決まる） */
  taskDecidedOnSend: boolean;
  onStart: (taskId: number) => void;
  onStop: () => void;
}> = ({ snapshot, timeZone, totalSeconds, current, next, linkedTasks, busy, taskDecidedOnSend, onStart, onStop }) => {
  const { t } = useI18n();
  const entry = snapshot?.current.entry ?? null;
  const taskTitle = (taskId: number | null) => (taskId != null ? linkedTasks.get(taskId)?.title : undefined);

  // 走っていないとき: いまの予定（無ければ次の予定）のタスクで始める口を大きく出す
  const suggested = current ?? next;
  const suggestion = suggested && occurrenceStartOf(suggested.occurrence, entry);

  return (
    <Box sx={{ ...card, gridArea: 'now', border: `1px solid ${entry ? ds.primaryPaleBorder : ds.border}` }} data-testid="today-now">
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: '10px', px: '14px', py: '10px',
        bgcolor: entry ? ds.primaryPale : ds.paper,
      }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {entry && snapshot ? (
            <>
              <Box sx={{ fontSize: 12, color: ds.primary, fontWeight: 700 }}>
                {t('today.running')}・{t('today.since', { time: formatMinute(toZonedPoint(Date.parse(entry.started_at), timeZone).minute) })}
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: '10px', minWidth: 0 }}>
                <Box sx={{ fontSize: 16, fontWeight: 700, color: ds.text, ...ellipsis }}>
                  {entry.task_title ?? t(taskDecidedOnSend ? 'timer.taskOnSend' : 'timer.unassigned')}
                </Box>
                <Box sx={{ fontSize: 16, fontWeight: 700, color: ds.primary, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
                  <RunningElapsed snapshot={snapshot} entry={entry} />
                </Box>
              </Box>
            </>
          ) : (
            <Box sx={{ fontSize: 14, color: ds.textSub }}>{t('today.stopped')}</Box>
          )}
        </Box>
        <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
          <Box sx={{ fontSize: 11, color: ds.textMuted }}>{t('today.totalToday')}</Box>
          <Box sx={{ fontSize: 16, fontWeight: 700, color: ds.text, fontVariantNumeric: 'tabular-nums' }}>
            {formatClockDuration(totalSeconds)}
          </Box>
        </Box>
        {entry && (
          <ButtonBase
            onClick={onStop}
            disabled={busy}
            aria-label={t('timer.stop')}
            sx={{
              height: 44, px: '12px', borderRadius: '8px', gap: '6px', color: '#fff', bgcolor: ds.dangerText,
              fontSize: 14, fontWeight: 700, flexShrink: 0, '&:hover': { bgcolor: '#A32116' },
            }}
          >
            <StopIcon size={16} />
            <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>{t('timer.stop')}</Box>
          </ButtonBase>
        )}
      </Box>
      {suggested && suggestion !== 'running' && (
        <Box sx={{
          display: 'flex', alignItems: 'center', gap: '10px', px: '14px', py: '8px', borderTop: `1px solid ${ds.borderPale}`,
        }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ fontSize: 11, color: ds.textMuted }}>
              {suggested === current
                ? t('today.currentEvent')
                : t('today.nextEvent', { time: formatMinute(suggested.startMinute) })}
            </Box>
            <Box sx={{ fontSize: 14, color: ds.text, ...ellipsis }}>{suggested.occurrence.title}</Box>
          </Box>
          {suggestion && suggested.occurrence.task_id != null && (
            <Button
              variant={entry ? 'outlined' : 'contained'}
              color="success"
              size="small"
              disabled={busy}
              startIcon={<PlayIcon size={14} />}
              onClick={() => onStart(suggested.occurrence.task_id as number)}
              sx={{ minHeight: 40, maxWidth: '55%', flexShrink: 0, ...ellipsis, display: 'inline-flex' }}
            >
              <Box component="span" sx={ellipsis}>
                {t(suggestion === 'switch' ? 'today.switchTask' : 'today.startTask', {
                  title: taskTitle(suggested.occurrence.task_id) ?? suggested.occurrence.title,
                })}
              </Box>
            </Button>
          )}
        </Box>
      )}
      {!suggested && !entry && (
        <Box sx={{ px: '14px', py: '8px', borderTop: `1px solid ${ds.borderPale}`, fontSize: 13, color: ds.textMuted }}>
          {t('today.noEvents')}
        </Box>
      )}
    </Box>
  );
};

// ── 予定のブロックの Start ─────────────────────────────────────────────

const BlockStart: React.FC<{
  occurrence: CalendarOccurrence;
  running: TimeEntry | null;
  title: string;
  busy: boolean;
  onStart: (taskId: number) => void;
}> = ({ occurrence, running, title, busy, onStart }) => {
  const { t } = useI18n();
  const intent = occurrenceStartOf(occurrence, running);
  if (intent == null) return null;
  if (intent === 'running') {
    return (
      <Box
        component="span"
        role="img"
        aria-label={t('today.runningTask')}
        title={t('today.runningTask')}
        sx={{ width: 8, height: 8, mx: '3px', borderRadius: '50%', bgcolor: '#fff', flexShrink: 0 }}
      />
    );
  }
  const label = t(intent === 'switch' ? 'today.switchTask' : 'today.startTask', { title });
  return (
    <ButtonBase
      aria-label={label}
      title={label}
      disabled={busy}
      onClick={(e) => { e.stopPropagation(); onStart(occurrence.task_id as number); }}
      onPointerDown={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      sx={{
        flexShrink: 0, width: 22, height: 18, borderRadius: '4px', color: '#fff',
        bgcolor: 'rgba(0,0,0,0.28)', '&:hover': { bgcolor: 'rgba(0,0,0,0.45)' },
      }}
    >
      <PlayIcon size={12} />
    </ButtonBase>
  );
};

// ── 今日やること（タスクの分類の回、ADR-0025）─────────────────────────

const RoutineList: React.FC<{
  occurrences: readonly CalendarOccurrence[];
  timeZone: string;
  running: TimeEntry | null;
  titleOf: (occurrence: CalendarOccurrence) => string;
  busy: boolean;
  onToggleDone: (occurrence: CalendarOccurrence) => void;
  onStart: (taskId: number) => void;
  onOpen: (occurrence: CalendarOccurrence) => void;
}> = ({ occurrences, timeZone, running, titleOf, busy, onToggleDone, onStart, onOpen }) => {
  const { t } = useI18n();
  const done = occurrences.filter((o) => o.is_done).length;
  return (
    <Box sx={{ ...card, gridArea: 'routine' }} data-testid="today-routine">
      <Box sx={cardHeader}>
        <Box sx={sectionTitle}>{t('today.routine')}</Box>
        <Box sx={{ fontSize: 12, color: done === occurrences.length ? ds.success : ds.textSub, fontVariantNumeric: 'tabular-nums' }}>
          {t('today.routineCount', { done, total: occurrences.length })}
        </Box>
      </Box>
      {occurrences.map((o) => {
        const intent = o.is_done ? null : occurrenceStartOf(o, running);
        const startLabel = intent && intent !== 'running'
          ? t(intent === 'switch' ? 'today.switchTask' : 'today.startTask', { title: titleOf(o) })
          : null;
        const startMinute = toZonedPoint(Date.parse(o.start), timeZone).minute;
        return (
          <Box key={o.id} sx={{
            display: 'flex', alignItems: 'center', gap: '4px', pl: '4px', pr: '10px', py: '2px',
            borderBottom: `1px solid ${ds.hairline}`, '&:last-of-type': { borderBottom: 'none' },
          }}>
            <IconButton
              role="checkbox"
              aria-checked={o.is_done}
              aria-label={t(o.is_done ? 'calendar.markUndone' : 'calendar.markDone')}
              onClick={() => onToggleDone(o)}
              sx={{ width: 44, height: 44, color: o.is_done ? ds.success : ds.textSub, flexShrink: 0 }}
            >
              {o.is_done ? <CheckBoxIcon /> : <CheckBoxOutlineBlankIcon />}
            </IconButton>
            <Box
              component="button"
              onClick={() => onOpen(o)}
              sx={{
                flex: 1, minWidth: 0, p: 0, border: 'none', bgcolor: 'transparent', font: 'inherit', textAlign: 'left',
                cursor: 'pointer', display: 'flex', alignItems: 'baseline', gap: '8px',
              }}
            >
              <Box component="span" sx={{
                fontSize: 12, color: ds.textMuted, fontVariantNumeric: 'tabular-nums', flexShrink: 0, minWidth: 34,
              }}>
                {o.is_all_day ? t('today.routineAllDay') : formatMinute(startMinute)}
              </Box>
              <Box component="span" sx={{
                fontSize: 14, ...ellipsis, color: o.is_done ? ds.textMuted : ds.text,
                textDecoration: o.is_done ? 'line-through' : 'none',
              }}>
                {o.title}
              </Box>
            </Box>
            {intent === 'running' && (
              <Box component="span" sx={{ fontSize: 11, color: ds.primary, fontWeight: 700, flexShrink: 0 }}>
                {t('today.runningTask')}
              </Box>
            )}
            {startLabel && (
              <IconButton
                aria-label={startLabel}
                title={startLabel}
                disabled={busy}
                onClick={() => onStart(o.task_id as number)}
                sx={{ width: 40, height: 40, color: ds.success, flexShrink: 0 }}
              >
                <PlayIcon size={16} />
              </IconButton>
            )}
          </Box>
        );
      })}
    </Box>
  );
};

// ── 2. まだ時間を取っていないタスク ───────────────────────────────────

const ToScheduleList: React.FC<{
  tasks: readonly Task[];
  today: string;
  categories: Category[] | undefined;
  shownFirst: number;
}> = ({ tasks, today, categories, shownFirst }) => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? tasks : tasks.slice(0, shownFirst);
  const hidden = tasks.length - shown.length;

  return (
    <Box sx={{ ...card, gridArea: 'tasks' }} data-testid="today-to-schedule">
      <Box sx={cardHeader}>
        <Box sx={sectionTitle}>{t('today.toSchedule')}</Box>
        <Box sx={{ fontSize: 12, color: ds.textSub }}>{t('today.count', { count: tasks.length })}</Box>
      </Box>
      {tasks.length === 0 && (
        <Box sx={{ px: '14px', py: '12px', fontSize: 13, color: ds.textMuted }}>{t('today.toScheduleEmpty')}</Box>
      )}
      {shown.map((task) => {
        const urgency = taskUrgencyOf(task, today);
        const urgent = urgency === 'overdue' || urgency === 'today';
        return (
          <Box key={task.id} sx={{
            display: 'flex', alignItems: 'center', gap: '10px', px: '14px', py: '6px',
            borderBottom: `1px solid ${ds.hairline}`, '&:last-of-type': { borderBottom: 'none' },
          }}>
            <CategoryDot categoryId={task.category_id} categories={categories} size={8} />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Box
                component="button"
                onClick={() => navigate(`/tasks/${task.id}`)}
                sx={{
                  display: 'block', maxWidth: '100%', p: 0, border: 'none', bgcolor: 'transparent', font: 'inherit',
                  textAlign: 'left', cursor: 'pointer', fontSize: 14, color: ds.text, ...ellipsis,
                  '&:hover': { color: ds.primary },
                }}
              >
                {task.title}
              </Box>
              <Box sx={{ display: 'flex', gap: '8px', fontSize: 12 }}>
                <Box component="span" sx={{ color: urgent ? ds.dangerText : ds.textSub, fontWeight: urgent ? 700 : 400 }}>
                  {t(urgencyKey[urgency])}
                </Box>
                <Box component="span" sx={{ color: ds.textMuted }}>
                  {task.unscheduled_hours != null
                    ? t('today.unscheduled', { hours: formatHours(task.unscheduled_hours) })
                    : t('today.remainingUnknown')}
                </Box>
              </Box>
            </Box>
            <Button
              variant="outlined"
              size="small"
              onClick={() => navigate(scheduleTaskPath(task.id))}
              sx={{ flexShrink: 0, minHeight: 36, px: '12px', whiteSpace: 'nowrap' }}
            >
              {t('today.schedule')}
            </Button>
          </Box>
        );
      })}
      {(hidden > 0 || expanded) && tasks.length > shownFirst && (
        <ButtonBase
          onClick={() => setExpanded(!expanded)}
          sx={{ width: '100%', py: '10px', fontSize: 13, color: ds.primary, borderTop: `1px solid ${ds.hairline}` }}
        >
          {expanded ? t('today.showLess') : t('today.showMore', { count: hidden })}
        </ButtonBase>
      )}
    </Box>
  );
};

// ── 3. 実績と KPI ──────────────────────────────────────────────────────

const ActualsCard: React.FC<{
  totalSeconds: number;
  actuals: TodaySummary['actuals'];
  colorOf: (taskId: number | null) => string;
}> = ({ totalSeconds, actuals, colorOf }) => {
  const { t } = useI18n();
  const longest = actuals.reduce((m, a) => Math.max(m, a.seconds), 0);
  return (
    <Box sx={{ ...card, gridArea: 'actuals' }} data-testid="today-actuals">
      <Box sx={cardHeader}>
        <Box sx={sectionTitle}>{t('today.actuals')}</Box>
        <Box sx={{ fontSize: 14, fontWeight: 700, color: ds.text, fontVariantNumeric: 'tabular-nums' }}>
          {formatClockDuration(totalSeconds)}
        </Box>
      </Box>
      {actuals.length === 0 && (
        <Box sx={{ px: '14px', py: '12px', fontSize: 13, color: ds.textMuted }}>{t('today.actualsEmpty')}</Box>
      )}
      {actuals.map((a) => (
        <Box key={a.task_id ?? 'unassigned'} sx={{ px: '14px', py: '6px' }}>
          <Box sx={{ display: 'flex', alignItems: 'baseline', gap: '8px', fontSize: 13 }}>
            <Box sx={{ flex: 1, minWidth: 0, color: a.task_id == null ? ds.textSub : ds.text, ...ellipsis }}>
              {a.task_title ?? t('timer.unassigned')}
            </Box>
            <Box sx={{ fontVariantNumeric: 'tabular-nums', color: ds.text, flexShrink: 0 }}>{formatClockDuration(a.seconds)}</Box>
          </Box>
          <Box sx={{ mt: '3px', height: 4, borderRadius: '2px', bgcolor: ds.track, overflow: 'hidden' }}>
            <Box sx={{
              height: '100%', width: `${longest > 0 ? (a.seconds / longest) * 100 : 0}%`, bgcolor: colorOf(a.task_id),
            }} />
          </Box>
        </Box>
      ))}
    </Box>
  );
};

const KpiCard: React.FC = () => {
  const { t } = useI18n();
  const { data: kpi } = useQuery({ queryKey: ['kpi'], queryFn: getDashboardKpi });
  if (!kpi) return null;
  const total = kpi.total_tasks;
  const done = total - kpi.incomplete_tasks;
  const donePct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <Box sx={{ ...card, gridArea: 'kpi', p: '12px 14px', display: 'flex', alignItems: 'center', gap: '14px' }} data-testid="today-kpi">
      <Box sx={{
        width: 52, height: 52, borderRadius: '50%', flexShrink: 0,
        background: `conic-gradient(${ds.success} ${donePct}%, ${ds.track} 0)`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Box sx={{
          width: 38, height: 38, borderRadius: '50%', bgcolor: ds.paper, display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontSize: 12, fontWeight: 700, color: ds.text,
        }}>
          {donePct}%
        </Box>
      </Box>
      <Box sx={{ fontSize: 12, color: ds.textSub, lineHeight: 1.7, minWidth: 0 }}>
        <Box sx={{ fontWeight: 700, color: ds.text }}>{t('dashboard.overall')}</Box>
        <Box>{t('dashboard.completedOfTotal', { done, total })}</Box>
        <Box>
          {t('dashboard.thisWeekDone')} <Box component="span" sx={{ fontWeight: 700, color: ds.primary }}>{kpi.this_week_completed}</Box>
          {'　'}
          {t('dashboard.overdueCount')}{' '}
          <Box component="span" sx={{ fontWeight: 700, color: kpi.overdue_tasks > 0 ? ds.dangerText : ds.text }}>{kpi.overdue_tasks}</Box>
        </Box>
      </Box>
    </Box>
  );
};

// ── 画面 ──────────────────────────────────────────────────────────────

const Today: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useI18n();
  const qc = useQueryClient();
  const theme = useTheme();
  const wide = useMediaQuery(theme.breakpoints.up('md'));
  // 広い画面の時間グリッドは画面の下端まで（上に締めの知らせが出ても、ページ全体ははみ出さない）
  const fill = useHeightToViewportBottom<HTMLDivElement>(24, wide);
  const nowMs = useMinuteClock();

  const summaryQuery = useQuery({ queryKey: TODAY_SUMMARY_KEY, queryFn: fetchSummary, refetchInterval: 60_000 });
  const snapshot = summaryQuery.data;
  const summary = snapshot?.summary;
  // 今日の区切りはサーバの要約（利用者のタイムゾーン）を正とする
  const timeZone = resolveTimeZone(summary?.time_zone);
  const date = summary?.date ?? null;
  const now = toZonedPoint(nowMs, timeZone);

  // 日付が変わったら要約を取り直す
  useEffect(() => {
    if (date != null && now.date !== date) void qc.invalidateQueries({ queryKey: TODAY_SUMMARY_KEY });
  }, [date, now.date, qc]);

  const range = date ? { from: date, to: date } : null;
  const occurrencesKey = useMemo(() => [OCCURRENCES_QUERY, date, date, timeZone] as const, [date, timeZone]);
  const occurrencesQuery = useQuery({
    queryKey: occurrencesKey,
    queryFn: () => getOccurrences(range as { from: string; to: string }, timeZone),
    enabled: range != null,
  });
  // 休みの 4 層（ADR-0029）。「今日」は全部のカレンダーを出すので、層も全部重ねる
  const holidaysQuery = useQuery({
    queryKey: [DAY_OFF_MARKS_QUERY, date, date],
    queryFn: () => getDayOffMarks(range as { from: string; to: string }),
    enabled: range != null,
  });
  const dayOffView = useMemo(
    () => buildDayOffView(holidaysQuery.data ?? [], undefined, { weeklyLabel: t('calendar.weeklyDayOffBand') }),
    [holidaysQuery.data, t],
  );
  const { data: tasks } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  const { data: milestones } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });
  // 端末に溜まった押下（オフラインで押した Start / Stop）を重ねた控え（ADR-0028）
  const { snapshot: current, pendingStart } = useProjectedTimeEntry();
  const writes = useTimerWrites();
  // 予定の書き込みと編集の画面はカレンダーと同じもの（task #185）
  const editing = useCalendarEditing({ occurrencesKey, timeZone, tasks: tasks ?? [] });

  const linkedTasks = useMemo(
    () => buildLinkedTasks(tasks ?? [], categories ?? [], categoryColor),
    [tasks, categories],
  );
  const colorOf = useMemo(
    () => (taskId: number | null) => (taskId == null ? UNASSIGNED_COLOR : linkedTasks.get(taskId)?.color ?? UNASSIGNED_COLOR),
    [linkedTasks],
  );
  const segmentsByDate = useMemo(
    () => groupSegmentsByDate(occurrencesQuery.data ?? [], timeZone),
    [occurrencesQuery.data, timeZone],
  );
  const deadlines = useMemo(
    () => (date ? buildDeadlines(tasks ?? [], milestones ?? [], categories ?? [], { from: date, to: date }) : []),
    [tasks, milestones, categories, date],
  );
  const bands = useMemo(() => {
    if (!summary || !date) return new Map<string, DayBand[]>();
    return new Map([[date, entryBands(summary.entries, date, timeZone, nowMs, colorOf, t('timer.unassigned'))]]);
  }, [summary, date, timeZone, nowMs, colorOf, t]);

  if (summaryQuery.isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  if (summaryQuery.isError || !summary || !snapshot || !date) return <Alert severity="error">{t('common.loadError')}</Alert>;

  const running = current?.current.entry ?? null;
  const live = liveActuals(summary, snapshot.receivedAt, nowMs);
  const todaySegments = segmentsByDate.get(date) ?? [];
  const routine = routineTasksOf(occurrencesQuery.data ?? [], date);
  const hasRoutine = routine.length > 0;
  const { current: currentSegment, next: nextSegment } = currentAndNext(todaySegments, now.date === date ? now.minute : -1);
  const taskTitle = (taskId: number | null) => (taskId != null ? linkedTasks.get(taskId)?.title : undefined);
  const start = (taskId: number) => writes.start(taskId, taskTitle(taskId));
  // 「予定を作る」: 今の後で空いている最初の 15 分刻みから（今日を見ていないときは編集画面の既定の 9:00）
  const addEvent = () => editing.openCreate(
    date,
    now.date === date ? nextFreeStartMinute(todaySegments, now.minute, DEFAULT_DURATION_MINUTES) : undefined,
  );
  // 予定を押したら編集（カレンダーは選んで日の一覧を出し二度押しで編集するが、ここには日の一覧が無い）
  const editSegment = (segment: DaySegment) => editing.openEdit(segment.occurrence);
  const toolButton = { width: 36, height: 36, color: ds.textSub } as const;

  return (
    <Box ref={fill.ref} sx={{
      display: 'grid', gap: '12px', alignItems: 'start',
      // 広い画面は箱ごと画面の下端まで。高さを決めずに時間グリッドだけに高さを持たせると、右の列の最後の
      // 1fr の行がグリッドの高さぶん伸びて、ページの下に数百 px の空きができる。
      height: { md: fill.height != null ? `${fill.height}px` : 'calc(100vh - 140px)' }, minHeight: { md: 560 },
      gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'minmax(0, 1fr) minmax(300px, 380px)' },
      gridTemplateAreas: hasRoutine
        ? {
          xs: '"now" "routine" "grid" "tasks" "actuals" "kpi"',
          md: '"grid now" "grid routine" "grid tasks" "grid actuals" "grid kpi" "grid ."',
        }
        : {
          xs: '"now" "grid" "tasks" "actuals" "kpi"',
          md: '"grid now" "grid tasks" "grid actuals" "grid kpi" "grid ."',
        },
      // 右の列の行は中身の高さ（auto だと、overflow: hidden のカードは最小が 0 とみなされ、行が詰められて重なる）
      gridTemplateRows: { md: `${'max-content '.repeat(hasRoutine ? 5 : 4)}1fr` },
    }}>
      <NowPanel
        snapshot={current}
        timeZone={timeZone}
        totalSeconds={live.totalSeconds}
        current={currentSegment}
        next={nextSegment}
        linkedTasks={linkedTasks}
        busy={writes.busy}
        taskDecidedOnSend={pendingStart != null && pendingStart.taskId === undefined}
        onStart={start}
        onStop={writes.stop}
      />

      {hasRoutine && (
        <RoutineList
          occurrences={routine}
          timeZone={timeZone}
          running={running}
          titleOf={(o) => taskTitle(o.task_id) ?? o.title}
          busy={writes.busy}
          onToggleDone={editing.toggleDone}
          onStart={start}
          onOpen={editing.openEdit}
        />
      )}

      <Box sx={{
        ...card, gridArea: 'grid', display: 'flex', flexDirection: 'column',
        height: { xs: '46vh', md: 'auto' }, minHeight: { xs: 300 }, alignSelf: { md: 'stretch' },
      }} data-testid="today-grid">
        <Box sx={{ ...cardHeader, alignItems: 'center', py: '4px', pr: '8px', flexShrink: 0 }}>
          <Box sx={sectionTitle}>{t('today.events')}</Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
            <Tooltip title={t('calendar.undo')}>
              <span>
                <IconButton aria-label={t('calendar.undo')} onClick={editing.undo} disabled={!editing.canUndo} sx={toolButton}>
                  <UndoIcon sx={{ fontSize: 18 }} />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title={t('calendar.redo')}>
              <span>
                <IconButton aria-label={t('calendar.redo')} onClick={editing.redo} disabled={!editing.canRedo} sx={toolButton}>
                  <RedoIcon sx={{ fontSize: 18 }} />
                </IconButton>
              </span>
            </Tooltip>
            <Button
              size="small"
              startIcon={<AddIcon />}
              onClick={addEvent}
              disabled={editing.busy}
              data-testid="today-add-event"
              sx={{ minHeight: 36, ml: '4px', whiteSpace: 'nowrap' }}
            >
              {t('calendar.addEvent')}
            </Button>
          </Box>
        </Box>
        {occurrencesQuery.isError && <Alert severity="error" sx={{ borderRadius: 0 }}>{t('common.loadError')}</Alert>}
        <Box sx={{ flex: 1, minHeight: 0 }}>
          <WeekView
            dates={[date]}
            timeZone={timeZone}
            segmentsByDate={segmentsByDate}
            holidays={dayOffView.holidays}
            nonWorkdays={dayOffView.nonWorkdays}
            deadlines={deadlines}
            today={now.date}
            nowMinute={now.minute}
            selectedDate={null}
            selectedSegmentKey={null}
            onSelectDate={() => undefined}
            onSelectSegment={editSegment}
            onOpenDeadline={(d) => navigate(d.kind === 'task' ? `/tasks/${d.id}` : '/milestones')}
            onCreateEvent={editing.openCreate}
            onCreateRange={(r) => editing.openCreate(r.date, r.startMinute, r.endMinute)}
            onRescheduleOccurrence={editing.reschedule}
            onToggleDone={editing.toggleDone}
            linkedTasks={linkedTasks}
            bands={bands}
            scrollLeadMinutes={SCROLL_LEAD_MINUTES}
            occurrenceAction={(o) => (
              <BlockStart
                occurrence={o}
                running={running}
                title={taskTitle(o.task_id) ?? o.title}
                busy={writes.busy}
                onStart={start}
              />
            )}
          />
        </Box>
      </Box>

      <ToScheduleList
        tasks={summary.tasks_to_schedule}
        today={date}
        categories={categories}
        shownFirst={wide ? 8 : TASKS_SHOWN_FIRST}
      />
      <ActualsCard totalSeconds={live.totalSeconds} actuals={live.actuals} colorOf={colorOf} />
      <KpiCard />

      {editing.dialogs}
    </Box>
  );
};

export default Today;
