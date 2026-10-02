import React, { useCallback, useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, ToggleButton, useMediaQuery } from '@mui/material';
import ChecklistIcon from '@mui/icons-material/Checklist';
import { useTheme } from '@mui/material/styles';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useI18n } from '../i18n';
import type { Task } from '../types';
import { getTasks } from '../api/tasks';
import { getMilestones } from '../api/milestones';
import { inScope } from '../projects/projectScope';
import { useProjectScope } from '../projects/useProjectScope';
import { getCategories } from '../api/categories';
import { getOccurrences, sendCalendarRequest } from '../api/calendar';
import { getDayOffMarks, getImportedOccurrences } from '../api/calendars';
import { buildDayOffView } from '../calendar/daysOff';
import SchedulerCalendar from '../components/calendar/SchedulerCalendar';
import TaskSchedulePanel from '../components/calendar/TaskSchedulePanel';
import CalendarVisibilityMenu from '../components/calendar/CalendarVisibilityMenu';
import { calendarForNewEvent, filterVisibleOccurrences } from '../calendar/calendarSelection';
import { useCalendarEditing } from '../components/calendar/useCalendarEditing';
import { useHeightToViewportBottom } from '../components/useHeightToViewportBottom';
import type { WeekSlot } from '../components/calendar/weekSlotLocator';
import type { CreateRange, TaskDropPreview } from '../components/calendar/calendarInteractions';
import type { CalendarDeadline } from '../calendar/taskDeadlines';
import { buildDeadlines } from '../calendar/taskDeadlines';
import { DAY_OFF_MARKS_QUERY, IMPORTED_OCCURRENCES_QUERY, OCCURRENCES_QUERY } from '../calendar/calendarQueries';
import { withImportedOccurrences } from '../calendar/importedOccurrences';
import { resolveTimeZone } from '../calendar/zonedTime';
import type { TaskEventDraft } from '../calendar/taskScheduling';
import {
  SCHEDULE_TASK_PARAM, buildLinkedTasks, draftFromDrop, draftFromSlot, parseScheduleTaskParam, schedulableTasks,
  taskEventRequest,
} from '../calendar/taskScheduling';
import { formatTimingRange } from '../calendar/weekGestures';
import { categoryColor } from '../theme';

type VisibleRange = { from: string; to: string };

/** 「時間を取る」で枠を押しただけのとき・日の一覧の「＋」から作るときの開始（9:00） */
const DEFAULT_SLOT_START_MINUTE = 9 * 60;

// 広い画面でタスクの一覧（右の列）をしまったか。端末ごとの好み（localStorage）。読めなければ出す。
const TASKS_HIDDEN_KEY = 'wbs.calendar.taskPanelHidden';
const readTasksHidden = (): boolean => {
  try {
    return window.localStorage.getItem(TASKS_HIDDEN_KEY) === '1';
  } catch {
    return false;
  }
};
const writeTasksHidden = (hidden: boolean) => {
  try {
    if (hidden) window.localStorage.setItem(TASKS_HIDDEN_KEY, '1');
    else window.localStorage.removeItem(TASKS_HIDDEN_KEY);
  } catch {
    // 覚えられなくても、この画面の間は効く
  }
};

/**
 * カレンダー（task #157）。予定 API（ADR-0009）の回と祝日を表示している期間ごとに取り、
 * タスク・マイルストーンの期限も終日の帯に出す。ドラッグで動かした回は API へ書き、
 * 元に戻す・やり直しも API 越しに行う（ADR-0013）。
 */
const CalendarPage: React.FC = () => {
  const { t, timezone } = useI18n();
  const navigate = useNavigate();
  const timeZone = resolveTimeZone(timezone);

  const [range, setRange] = useState<VisibleRange | null>(null);
  const onVisibleRangeChange = useCallback((next: VisibleRange) => {
    setRange((prev) => (prev && prev.from === next.from && prev.to === next.to ? prev : next));
  }, []);

  const occurrencesKey = useMemo(() => [OCCURRENCES_QUERY, range?.from, range?.to, timeZone] as const, [range, timeZone]);
  const occurrencesQuery = useQuery({
    queryKey: occurrencesKey,
    queryFn: () => getOccurrences(range as VisibleRange, timeZone),
    enabled: range != null,
    placeholderData: keepPreviousData,
  });
  // 休みの 4 層（ADR-0029）。表示中の層だけ塗る（営業日の判定は表示に関係しない）
  const holidaysQuery = useQuery({
    queryKey: [DAY_OFF_MARKS_QUERY, range?.from, range?.to],
    queryFn: () => getDayOffMarks(range as VisibleRange),
    enabled: range != null,
    placeholderData: keepPreviousData,
  });
  // 取り込んだカレンダーの回（ADR-0037）。読み取り専用で予定に重ねる。取れなくても予定は出す
  const importedQuery = useQuery({
    queryKey: [IMPORTED_OCCURRENCES_QUERY, range?.from, range?.to, timeZone],
    queryFn: () => getImportedOccurrences(range as VisibleRange, timeZone),
    enabled: range != null,
    placeholderData: keepPreviousData,
  });
  const { data: tasks } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });
  const { data: milestones } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });

  const linkedTasks = useMemo(
    () => buildLinkedTasks(tasks ?? [], categories ?? [], categoryColor),
    [tasks, categories],
  );
  const panelTasks = useMemo(() => schedulableTasks(tasks ?? []), [tasks]);

  // 「時間を取る」の最中のタスク（task #159）。URL のクエリで持つ（タスクの画面から渡ってくる）。
  const [searchParams, setSearchParams] = useSearchParams();
  const schedulingTaskId = parseScheduleTaskParam(searchParams.get(SCHEDULE_TASK_PARAM));
  const schedulingTask = schedulingTaskId != null ? (tasks ?? []).find((t) => t.id === schedulingTaskId) ?? null : null;
  const setSchedulingTask = useCallback((taskId: number | null) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (taskId == null) next.delete(SCHEDULE_TASK_PARAM);
      else next.set(SCHEDULE_TASK_PARAM, String(taskId));
      return next;
    }, { replace: true });
  }, [setSearchParams]);
  const [dropPreview, setDropPreview] = useState<TaskDropPreview | null>(null);

  // 期限（タスク・マイルストーン）はサイドバーで選んだプロジェクト（と子孫）のものだけ（task #187、ADR-0024）
  const { scope, projects } = useProjectScope();
  const deadlines = useMemo(
    () => (range
      ? buildDeadlines(
        (tasks ?? []).filter((x) => inScope(x.project_id, scope, projects)),
        (milestones ?? []).filter((m) => inScope(m.project_id, scope, projects)),
        categories ?? [], range,
      )
      : []),
    [tasks, milestones, categories, range, scope, projects],
  );

  const editing = useCalendarEditing({ occurrencesKey, timeZone, tasks: tasks ?? [] });
  // 表示にしているカレンダーの回だけ（ADR-0027。選んだ状態はサーバーが覚えている）
  const dayOffView = useMemo(
    () => buildDayOffView(holidaysQuery.data ?? [], editing.calendars, { weeklyLabel: t('calendar.weeklyDayOffBand') }),
    [holidaysQuery.data, editing.calendars, t],
  );
  const visibleOccurrences = useMemo(
    () => filterVisibleOccurrences(
      withImportedOccurrences(occurrencesQuery.data, importedQuery.data, t('calendar.importedNoTitle')),
      editing.calendars,
    ),
    [occurrencesQuery.data, importedQuery.data, editing.calendars, t],
  );

  // ── タスクから作る（task #159） ─────────────────────────────────────

  const createTaskEvent = (draft: TaskEventDraft) => editing.exclusive(async () => {
    await sendCalendarRequest(taskEventRequest(draft, timeZone, calendarForNewEvent(editing.calendars, { forTask: true })));
    setSchedulingTask(null);
    // 「予定済みの時間」も変わる（読み直させるものに入っている）
    editing.refresh();
    editing.notify('calendar.taskScheduled', 'success', { title: draft.title, range: formatTimingRange(draft) });
    editing.warnDaysOff([draft.date]);
  });

  const onCreateEvent = (date: string, minute?: number) => {
    if (schedulingTask) {
      void createTaskEvent(draftFromSlot(schedulingTask, { date, startMinute: minute ?? DEFAULT_SLOT_START_MINUTE }));
      return;
    }
    editing.openCreate(date, minute);
  };

  const onCreateRange = (r: CreateRange) => {
    if (schedulingTask) {
      void createTaskEvent(draftFromSlot(schedulingTask, r));
      return;
    }
    editing.openCreate(r.date, r.startMinute, r.endMinute);
  };

  const onTaskDragOver = (task: Task, slot: WeekSlot | null) => {
    const draft = slot ? draftFromDrop(task, slot) : null;
    const next: TaskDropPreview | null = draft
      ? { date: draft.date, startMinute: draft.startMinute, durationMinutes: draft.durationMinutes, title: draft.title }
      : null;
    setDropPreview((prev) => {
      if (prev === next) return prev;
      if (prev && next && prev.date === next.date && prev.startMinute === next.startMinute
        && prev.durationMinutes === next.durationMinutes && prev.title === next.title) return prev;
      return next;
    });
  };

  const onTaskDrop = (task: Task, slot: WeekSlot) => {
    setDropPreview(null);
    void createTaskEvent(draftFromDrop(task, slot));
  };

  const openDeadline = (deadline: CalendarDeadline) =>
    navigate(deadline.kind === 'task' ? `/tasks/${deadline.id}` : '/milestones');

  // 広い画面はカレンダーとタスクの一覧を画面の下端まで（下の余白は main の 24px）。狭い画面はカレンダーだけ。
  const wide = useMediaQuery(useTheme().breakpoints.up('md'));
  const fill = useHeightToViewportBottom<HTMLDivElement>(24, wide);
  // 狭い画面もカレンダーの箱を画面の下端まで（下の余白は main の 16px）。上の高さを決め打ちすると、文字の大きさや
  // 知らせの高さ次第でページが数 px はみ出し、時間グリッドを送り切ったところでページごと動く（アドレスバーも出入りする）。
  const fillNarrow = useHeightToViewportBottom<HTMLDivElement>(16, !wide);

  // 「時間を取る」のタスクの一覧（ADR-0035）。広い画面は右の列で既定は出す（予定を組むときに引いて落とす元。
  // しまえば時間グリッドが広がり、端末に覚える）。狭い画面は既定はしまい、出すとカレンダーの見出しの下に出る。
  const [wideTasksHidden, setWideTasksHidden] = useState(readTasksHidden);
  const [narrowTasksOpen, setNarrowTasksOpen] = useState(false);
  const tasksOpen = wide ? !wideTasksHidden : narrowTasksOpen;
  const toggleTasks = () => {
    if (wide) {
      setWideTasksHidden((hidden) => {
        writeTasksHidden(!hidden);
        return !hidden;
      });
    } else {
      setNarrowTasksOpen((open) => !open);
    }
  };
  const selectPanelTask = (task: Task) => {
    setSchedulingTask(task.id === schedulingTask?.id ? null : task.id);
    // 狭い画面は選んだら一覧をしまう（置く先の時間グリッドを広く見せる。上の知らせに選んだタスクが出る）
    if (!wide) setNarrowTasksOpen(false);
  };

  const taskPanel = (variant: 'column' | 'inline') => (
    <TaskSchedulePanel
      variant={variant}
      tasks={panelTasks}
      categories={categories ?? []}
      selectedTaskId={schedulingTask?.id ?? null}
      onSelectTask={selectPanelTask}
      onDragOver={onTaskDragOver}
      onDragEnd={() => setDropPreview(null)}
      onDropTask={onTaskDrop}
    />
  );

  const tasksToggle = (
    <ToggleButton
      size="small"
      value="tasks"
      selected={tasksOpen}
      onChange={toggleTasks}
      title={t('calendar.taskPanelToggle')}
      aria-expanded={tasksOpen}
      data-testid="calendar-tasks-toggle"
      sx={{ px: '8px', py: '3px', gap: '4px', fontSize: 12, fontWeight: 700, textTransform: 'none', whiteSpace: 'nowrap' }}
    >
      <ChecklistIcon sx={{ fontSize: 16 }} />
      {t('calendar.taskPanelTitle', { count: panelTasks.length })}
    </ToggleButton>
  );

  const visibilityMenu = (
    <CalendarVisibilityMenu
      calendars={editing.calendars ?? []}
      onError={(detail) => editing.notify('calendar.saveFailed', 'error', { detail })}
    />
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {(occurrencesQuery.isError || holidaysQuery.isError) && (
        <Alert severity="error">{t('common.loadError')}</Alert>
      )}
      {schedulingTask && (
        <Alert
          severity="info"
          data-testid="scheduling-task-banner"
          action={<Button color="inherit" size="small" onClick={() => setSchedulingTask(null)}>{t('calendar.schedulingStop')}</Button>}
        >
          {t('calendar.schedulingTask', { title: schedulingTask.title })}
        </Alert>
      )}
      {/* カレンダーがいちばん左・いちばん広く。表示の切り替えは常時の列をやめ、見出しの端から開く（ADR-0035） */}
      <Box
        ref={fill.ref}
        sx={{
          display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: '12px', alignItems: 'stretch',
          height: { md: fill.height != null ? `${fill.height}px` : 'calc(100vh - 160px)' }, minHeight: { md: 640 },
        }}
      >
        {/* 狭い画面（縦に積む）で flex: 1 にすると、高さの指定より中身の高さ（1 日 1440px）が勝って
            時間グリッドが内側でスクロールしなくなる（今の時刻へ送れず 0:00 から出る）。広い画面だけ伸ばす。 */}
        <Box ref={fillNarrow.ref} sx={{
          flex: { xs: '0 0 auto', md: 1 }, minWidth: 0,
          height: { xs: fillNarrow.height != null ? `${fillNarrow.height}px` : 'calc(100svh - 140px)', md: '100%' }, minHeight: { xs: 480 },
        }}>
          <SchedulerCalendar
            occurrences={visibleOccurrences}
            holidays={dayOffView.holidays}
            nonWorkdays={dayOffView.nonWorkdays}
            deadlines={deadlines}
            timeZone={timeZone}
            onVisibleRangeChange={onVisibleRangeChange}
            onCreateEvent={onCreateEvent}
            onCreateRange={onCreateRange}
            linkedTasks={linkedTasks}
            dropPreview={dropPreview}
            onEditOccurrence={editing.openEdit}
            onDeleteOccurrence={editing.askDelete}
            onToggleDone={editing.toggleDone}
            onOpenDeadline={openDeadline}
            onRescheduleOccurrence={editing.reschedule}
            onUndo={editing.undo}
            onRedo={editing.redo}
            canUndo={editing.canUndo}
            canRedo={editing.canRedo}
            toolbarStart={tasksToggle}
            toolbarEnd={visibilityMenu}
            beneathHeader={!wide && tasksOpen ? taskPanel('inline') : null}
          />
        </Box>
        {/* タスクの一覧（広い画面の右の列。しまえばカレンダーが広がる） */}
        {wide && tasksOpen && (
          <Box sx={{ width: 260, flexShrink: 0, height: '100%' }}>{taskPanel('column')}</Box>
        )}
      </Box>

      {editing.dialogs}
    </Box>
  );
};

export default CalendarPage;
