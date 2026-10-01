import React, { useCallback, useMemo, useRef, useState } from 'react';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Snackbar, useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import type { CalendarEvent, CalendarOccurrence, Task } from '../types';
import { getTasks } from '../api/tasks';
import { getMilestones } from '../api/milestones';
import { getCategories } from '../api/categories';
import {
  getBusinessCalendars, getEvent, getHolidays, getOccurrences, sendCalendarRequest,
} from '../api/calendar';
import SchedulerCalendar from '../components/calendar/SchedulerCalendar';
import EventEditDialog from '../components/calendar/EventEditDialog';
import type { EventEditTarget } from '../components/calendar/EventEditDialog';
import RecurringScopeDialog from '../components/calendar/RecurringScopeDialog';
import TaskSchedulePanel from '../components/calendar/TaskSchedulePanel';
import { useHeightToViewportBottom } from '../components/useHeightToViewportBottom';
import type { WeekSlot } from '../components/calendar/weekSlotLocator';
import type { CreateRange, OccurrenceReschedule, TaskDropPreview } from '../components/calendar/calendarInteractions';
import type { CalendarDeadline } from '../calendar/taskDeadlines';
import { buildDeadlines } from '../calendar/taskDeadlines';
import { formFromEvent, newEventForm, planOccurrenceDelete } from '../calendar/eventForm';
import type { RecurringScope } from '../calendar/eventForm';
import type { RescheduleEntry } from '../calendar/calendarRequests';
import {
  applyScheduleToOccurrences, errorDetailOf, isConflictError, redoRequest, rescheduleEntryOf, rescheduleRequest,
  undoRequest, withEventVersion, withOccurrenceEventVersion,
} from '../calendar/calendarRequests';
import type { OperationHistory } from '../calendar/operationHistory';
import {
  canRedo, canUndo, emptyHistory, recordOperation, redoOperation, undoOperation,
} from '../calendar/operationHistory';
import { resolveTimeZone, toZonedPoint } from '../calendar/zonedTime';
import type { TaskEventDraft } from '../calendar/taskScheduling';
import {
  SCHEDULE_TASK_PARAM, buildLinkedTasks, draftFromDrop, draftFromSlot, parseScheduleTaskParam, schedulableTasks,
  taskEventRequest,
} from '../calendar/taskScheduling';
import { formatTimingRange } from '../calendar/weekGestures';
import { categoryColor } from '../theme';

type VisibleRange = { from: string; to: string };

interface Notice {
  message: string;
  severity: 'success' | 'info' | 'warning' | 'error';
}

const OCCURRENCES = 'calendar-occurrences';
const HOLIDAYS = 'calendar-holidays';
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
  const qc = useQueryClient();
  const timeZone = resolveTimeZone(timezone);

  const [range, setRange] = useState<VisibleRange | null>(null);
  const onVisibleRangeChange = useCallback((next: VisibleRange) => {
    setRange((prev) => (prev && prev.from === next.from && prev.to === next.to ? prev : next));
  }, []);

  const occurrencesKey = useMemo(() => [OCCURRENCES, range?.from, range?.to, timeZone] as const, [range, timeZone]);
  const occurrencesQuery = useQuery({
    queryKey: occurrencesKey,
    queryFn: () => getOccurrences(range as VisibleRange, timeZone),
    enabled: range != null,
    placeholderData: keepPreviousData,
  });
  const holidaysQuery = useQuery({
    queryKey: [HOLIDAYS, range?.from, range?.to],
    queryFn: () => getHolidays(range as VisibleRange),
    enabled: range != null,
    placeholderData: keepPreviousData,
  });
  const { data: tasks } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });
  const { data: milestones } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  const { data: businessCalendars } = useQuery({ queryKey: ['business-calendars'], queryFn: getBusinessCalendars });

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

  const deadlines = useMemo(
    () => (range ? buildDeadlines(tasks ?? [], milestones ?? [], categories ?? [], range) : []),
    [tasks, milestones, categories, range],
  );

  const [history, setHistory] = useState<OperationHistory<RescheduleEntry>>(() => emptyHistory<RescheduleEntry>());
  const [editTarget, setEditTarget] = useState<EventEditTarget | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CalendarOccurrence | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);

  const today = () => toZonedPoint(Date.now(), timeZone).date;
  const notify = (key: TranslationKey, severity: Notice['severity'], params?: Record<string, string | number>) =>
    setNotice({ message: t(key, params), severity });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: [OCCURRENCES] });
    void qc.invalidateQueries({ queryKey: [HOLIDAYS] });
  };

  /** 409: ほかで変わっていた。最新を取り直し、履歴は捨てる（古い版の操作は当てられない）。 */
  const onConflict = () => {
    setHistory(emptyHistory<RescheduleEntry>());
    refresh();
    notify('calendar.conflict', 'warning');
  };

  const onFailure = (error: unknown) => {
    if (isConflictError(error)) { onConflict(); return; }
    refresh();
    notify('calendar.saveFailed', 'error', { detail: errorDetailOf(error) ?? '' });
  };

  /** 書き込みを 1 つずつ（ドラッグ中に次の書き込みを重ねない）。 */
  const exclusive = async (run: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      await run();
    } catch (error) {
      onFailure(error);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const patchOccurrences = (patch: (list: CalendarOccurrence[]) => CalendarOccurrence[]) =>
    qc.setQueryData<CalendarOccurrence[]>(occurrencesKey, (list) => (list ? patch(list) : list));

  const afterWrite = (eventId: number, written: CalendarEvent | null) => {
    if (written) patchOccurrences((list) => withOccurrenceEventVersion(list, eventId, written.version));
    refresh();
  };

  // ── ドラッグ ──────────────────────────────────────────────────────────

  const reschedule = (change: OccurrenceReschedule) => exclusive(async () => {
    const eventId = change.occurrence.event_id;
    // 応答を待たずに新しい位置で見せる（失敗したら取り直して戻る）。
    patchOccurrences((list) => applyScheduleToOccurrences(list, change.occurrence.id, change.after, change.scope === 'occurrence'));
    const event = change.scope === 'event' ? await getEvent(eventId) : null;
    const written = await sendCalendarRequest(rescheduleRequest(change, event));
    if (!written) return;
    setHistory((h) => withEventVersion(recordOperation(h, rescheduleEntryOf(change, written.version)), eventId, written.version));
    afterWrite(eventId, written);
  });

  const undo = () => exclusive(async () => {
    const step = undoOperation(history);
    if (!step) return;
    const { entry } = step;
    const event = entry.scope === 'event' ? await getEvent(entry.eventId) : null;
    const written = await sendCalendarRequest(undoRequest(entry, event));
    if (!written) return;
    setHistory(withEventVersion(step.history, entry.eventId, written.version));
    afterWrite(entry.eventId, written);
    notify('calendar.undone', 'info');
  });

  const redo = () => exclusive(async () => {
    const step = redoOperation(history);
    if (!step) return;
    const { entry } = step;
    const event = entry.scope === 'event' ? await getEvent(entry.eventId) : null;
    const written = await sendCalendarRequest(redoRequest(entry, event));
    if (!written) return;
    setHistory(withEventVersion(step.history, entry.eventId, written.version));
    afterWrite(entry.eventId, written);
    notify('calendar.redone', 'info');
  });

  // ── 作る・直す・消す ──────────────────────────────────────────────────

  const calendarIds = (businessCalendars ?? []).map((c) => c.id);

  const openCreate = (date: string, startMinute?: number, endMinute?: number) => setEditTarget({
    form: newEventForm({ date, startMinute, endMinute, timeZone, today: today(), calendarIds }),
    context: { mode: 'create' },
  });

  const openEdit = (occurrence: CalendarOccurrence) => exclusive(async () => {
    const event = await getEvent(occurrence.event_id);
    setEditTarget(formFromEvent(event, occurrence, today()));
  });

  /** 編集画面で保存・削除したら、ドラッグの履歴は捨てる（版が進み、古い操作は当てられない）。 */
  const afterDialogWrite = (key: TranslationKey) => {
    setEditTarget(null);
    setHistory(emptyHistory<RescheduleEntry>());
    refresh();
    notify(key, 'success');
  };

  const deleteOccurrence = (occurrence: CalendarOccurrence, scope: RecurringScope | null) => {
    const request = planOccurrenceDelete(occurrence, scope);
    setDeleteTarget(null);
    if (!request) return;
    void exclusive(async () => {
      await sendCalendarRequest(request);
      afterDialogWrite('calendar.deleted');
    });
  };

  // ── タスクから作る（task #159） ─────────────────────────────────────

  const createTaskEvent = (draft: TaskEventDraft) => exclusive(async () => {
    await sendCalendarRequest(taskEventRequest(draft, timeZone));
    setSchedulingTask(null);
    refresh();
    // 「予定済みの時間」が変わる
    void qc.invalidateQueries({ queryKey: ['tasks'] });
    void qc.invalidateQueries({ queryKey: ['task'] });
    void qc.invalidateQueries({ queryKey: ['today'] });
    notify('calendar.taskScheduled', 'success', { title: draft.title, range: formatTimingRange(draft) });
  });

  const onCreateEvent = (date: string, minute?: number) => {
    if (schedulingTask) {
      void createTaskEvent(draftFromSlot(schedulingTask, { date, startMinute: minute ?? DEFAULT_SLOT_START_MINUTE }));
      return;
    }
    openCreate(date, minute);
  };

  const onCreateRange = (r: CreateRange) => {
    if (schedulingTask) {
      void createTaskEvent(draftFromSlot(schedulingTask, r));
      return;
    }
    openCreate(r.date, r.startMinute, r.endMinute);
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

  const askDeleteScope = deleteTarget != null && deleteTarget.is_recurring && deleteTarget.series_key != null;
  // 広い画面はカレンダーとタスクの一覧を画面の下端まで（下の余白は main の 24px）。狭い画面は縦に積んでページごと送る。
  const wide = useMediaQuery(useTheme().breakpoints.up('md'));
  const fill = useHeightToViewportBottom<HTMLDivElement>(24, wide);

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
        <Box sx={{
          order: { xs: 2, md: 1 }, flex: { xs: '0 0 auto', md: 1 }, minWidth: 0,
          height: { xs: 'calc(100svh - 140px)', md: '100%' }, minHeight: { xs: 480 },
        }}>
          <SchedulerCalendar
            occurrences={occurrencesQuery.data ?? []}
            holidays={holidaysQuery.data ?? []}
            deadlines={deadlines}
            timeZone={timeZone}
            onVisibleRangeChange={onVisibleRangeChange}
            onCreateEvent={onCreateEvent}
            onCreateRange={onCreateRange}
            linkedTasks={linkedTasks}
            dropPreview={dropPreview}
            onEditOccurrence={(o) => void openEdit(o)}
            onDeleteOccurrence={setDeleteTarget}
            onOpenDeadline={openDeadline}
            onRescheduleOccurrence={(change) => void reschedule(change)}
            onUndo={() => void undo()}
            onRedo={() => void redo()}
            canUndo={!busy && canUndo(history)}
            canRedo={!busy && canRedo(history)}
          />
        </Box>
      </Box>

      {editTarget && (
        <EventEditDialog
          target={editTarget}
          viewerTimeZone={timeZone}
          tasks={tasks ?? []}
          businessCalendars={businessCalendars ?? []}
          onClose={() => setEditTarget(null)}
          onSaved={() => afterDialogWrite('calendar.saved')}
          onConflict={() => { setEditTarget(null); onConflict(); }}
          onDelete={setDeleteTarget}
        />
      )}

      <RecurringScopeDialog
        open={askDeleteScope}
        purpose="delete"
        onCancel={() => setDeleteTarget(null)}
        onChoose={(scope) => deleteTarget && deleteOccurrence(deleteTarget, scope)}
      />
      <Dialog open={deleteTarget != null && !askDeleteScope} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('calendar.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>{t('calendar.deleteConfirm', { title: deleteTarget?.title ?? '' })}</DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>{t('calendar.cancel')}</Button>
          <Button color="error" variant="contained" onClick={() => deleteTarget && deleteOccurrence(deleteTarget, null)}>
            {t('calendar.delete')}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={notice != null}
        autoHideDuration={4000}
        onClose={() => setNotice(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={notice?.severity ?? 'info'} onClose={() => setNotice(null)} sx={{ width: '100%' }}>
          {notice?.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default CalendarPage;
