import React, { useCallback, useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, useMediaQuery } from '@mui/material';
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
import { getDayOffMarks } from '../api/calendars';
import { buildDayOffView } from '../calendar/daysOff';
import SchedulerCalendar from '../components/calendar/SchedulerCalendar';
import TaskSchedulePanel from '../components/calendar/TaskSchedulePanel';
import CalendarListPanel from '../components/calendar/CalendarListPanel';
import { calendarForNewEvent, filterVisibleOccurrences } from '../calendar/calendarSelection';
import { useCalendarEditing } from '../components/calendar/useCalendarEditing';
import { useHeightToViewportBottom } from '../components/useHeightToViewportBottom';
import type { WeekSlot } from '../components/calendar/weekSlotLocator';
import type { CreateRange, TaskDropPreview } from '../components/calendar/calendarInteractions';
import type { CalendarDeadline } from '../calendar/taskDeadlines';
import { buildDeadlines } from '../calendar/taskDeadlines';
import { DAY_OFF_MARKS_QUERY, OCCURRENCES_QUERY } from '../calendar/calendarQueries';
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
    () => buildDayOffView(holidaysQuery.data ?? [], editing.calendars),
    [holidaysQuery.data, editing.calendars],
  );
  const visibleOccurrences = useMemo(
    () => filterVisibleOccurrences(occurrencesQuery.data ?? [], editing.calendars),
    [occurrencesQuery.data, editing.calendars],
  );

  // ── タスクから作る（task #159） ─────────────────────────────────────

  const createTaskEvent = (draft: TaskEventDraft) => editing.exclusive(async () => {
    await sendCalendarRequest(taskEventRequest(draft, timeZone, calendarForNewEvent(editing.calendars)));
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

  // 広い画面はカレンダーとタスクの一覧を画面の下端まで（下の余白は main の 24px）。狭い画面は縦に積む。
  const wide = useMediaQuery(useTheme().breakpoints.up('md'));
  const fill = useHeightToViewportBottom<HTMLDivElement>(24, wide);
  // 狭い画面もカレンダーの箱を画面の下端まで（下の余白は main の 16px）。上の高さを決め打ちすると、文字の大きさや
  // タスクの帯の高さ次第でページが数 px はみ出し、時間グリッドを送り切ったところでページごと動く（アドレスバーも出入りする）。
  const fillNarrow = useHeightToViewportBottom<HTMLDivElement>(16, !wide);

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
      <Box
        ref={fill.ref}
        sx={{
          display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: '12px', alignItems: 'stretch',
          height: { md: fill.height != null ? `${fill.height}px` : 'calc(100vh - 160px)' }, minHeight: { md: 640 },
        }}
      >
        {/* カレンダーの一覧と表示の選択（広い画面は左、狭い画面はいちばん上で折りたたむ） */}
        <Box sx={{ order: { xs: 0, md: 0 }, width: { xs: '100%', md: 220 }, flexShrink: 0, height: { md: '100%' } }}>
          <CalendarListPanel
            calendars={editing.calendars ?? []}
            onError={(detail) => editing.notify('calendar.saveFailed', 'error', { detail })}
          />
        </Box>
        {/* タスクの一覧（広い画面は右、狭い画面は上で折りたたむ） */}
        <Box sx={{ order: { xs: 1, md: 2 }, width: { xs: '100%', md: 260 }, flexShrink: 0, height: { md: '100%' } }}>
          <TaskSchedulePanel
            tasks={panelTasks}
            categories={categories ?? []}
            selectedTaskId={schedulingTask?.id ?? null}
            onSelectTask={(task) => setSchedulingTask(task.id === schedulingTask?.id ? null : task.id)}
            onDragOver={onTaskDragOver}
            onDragEnd={() => setDropPreview(null)}
            onDropTask={onTaskDrop}
          />
        </Box>
        {/* 狭い画面（縦に積む）で flex: 1 にすると、高さの指定より中身の高さ（1 日 1440px）が勝って
            時間グリッドが内側でスクロールしなくなる（今の時刻へ送れず 0:00 から出る）。広い画面だけ伸ばす。 */}
        <Box ref={fillNarrow.ref} sx={{
          order: { xs: 2, md: 1 }, flex: { xs: '0 0 auto', md: 1 }, minWidth: 0,
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
          />
        </Box>
      </Box>

      {editing.dialogs}
    </Box>
  );
};

export default CalendarPage;
