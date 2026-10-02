import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { QueryKey } from '@tanstack/react-query';
import {
  Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Snackbar,
} from '@mui/material';
import { useI18n } from '../../i18n';
import type { TranslationKey } from '../../i18n/translations';
import type { CalendarEvent, CalendarOccurrence, Task } from '../../types';
import { getEvent, getOccurrences, sendCalendarRequest } from '../../api/calendar';
import { getCalendars, getDayOffMarks } from '../../api/calendars';
import { dayOffReasonsOn, notifiesDayOff } from '../../calendar/daysOff';
import { formatDate } from '../../utils/format';
import { calendarForNewEvent } from '../../calendar/calendarSelection';
import { formatOccurrenceTimeRange } from '../../calendar/daySegments';
import EventEditDialog from './EventEditDialog';
import type { EventEditTarget } from './EventEditDialog';
import RecurringScopeDialog from './RecurringScopeDialog';
import type { OccurrenceReschedule } from './calendarInteractions';
import { formFromEvent, newEventForm, planOccurrenceDelete } from '../../calendar/eventForm';
import type { RecurringScope } from '../../calendar/eventForm';
import type { RescheduleEntry } from '../../calendar/calendarRequests';
import {
  applyScheduleToOccurrences, errorDetailOf, isConflictError, occurrenceDoneRequest, redoRequest, rescheduleEntryOf,
  rescheduleRequest, undoRequest, withEventVersion, withOccurrenceDone, withOccurrenceEventVersion,
} from '../../calendar/calendarRequests';
import type { OperationHistory } from '../../calendar/operationHistory';
import {
  canRedo, canUndo, emptyHistory, recordOperation, redoOperation, undoOperation,
} from '../../calendar/operationHistory';
import { CALENDARS_QUERY, OCCURRENCES_QUERY, queriesAfterEventWrite } from '../../calendar/calendarQueries';
import { addDays, toZonedPoint } from '../../calendar/zonedTime';

/** 繰り返しを書いたとき、休みの日に当たる回を何日先まで見るか。 */
const WARN_RECURRING_DAYS = 62;

export interface CalendarNotice {
  message: string;
  severity: 'success' | 'info' | 'warning' | 'error';
}

interface Options {
  /** 画面が回を取っている問い合わせのキー（ドラッグした回を応答を待たずに動かす先） */
  occurrencesKey: QueryKey;
  /** 閲覧者のタイムゾーン */
  timeZone: string;
  /** 編集画面で結べるタスク */
  tasks: readonly Task[];
}

/**
 * 予定を作る・直す・消す・ドラッグで動かす・元に戻す（task #157・#158、ADR-0013）の書き込みと、
 * そのための画面（編集・範囲の確認・削除の確認・知らせ）。カレンダーと「今日」の画面（task #185）で
 * 同じものを使う。書いたら回と、タスクの予定済みの時間・「今日」の要約を読み直させる。
 *
 * 返す `dialogs` を画面のどこかに置く。
 *
 * 取り込んだカレンダーの回（`is_imported`、ADR-0037）は読み取り専用: 押すと中身だけを見せ、動かす・直す・
 * 消す・済みは何もしない。
 */
export const useCalendarEditing = ({ occurrencesKey, timeZone, tasks }: Options) => {
  const { t } = useI18n();
  const qc = useQueryClient();
  // 予定のカレンダー（ADR-0027）。編集画面で選ぶ・新しい予定の入れ先を決める
  const { data: calendars } = useQuery({ queryKey: [CALENDARS_QUERY], queryFn: getCalendars });

  const [history, setHistory] = useState<OperationHistory<RescheduleEntry>>(() => emptyHistory<RescheduleEntry>());
  const [editTarget, setEditTarget] = useState<EventEditTarget | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CalendarOccurrence | null>(null);
  const [importedTarget, setImportedTarget] = useState<CalendarOccurrence | null>(null);
  const [notice, setNotice] = useState<CalendarNotice | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);

  const today = () => toZonedPoint(Date.now(), timeZone).date;
  const notify = (key: TranslationKey, severity: CalendarNotice['severity'], params?: Record<string, string | number>) =>
    setNotice({ message: t(key, params), severity });

  /**
   * 休みの日に置いたら知らせる（止めはしない。ADR-0029）。休みかどうかは表示に関係なく「休みとして数える」で決まる。
   * 知らせるのはタスクだけ（分類がタスクの予定・「時間を取る」で落としたタスク。2026-10-02 の決定）。予定は知らせない。
   * 知らせは添えものなので、取れなくても黙る（書き込みは済んでいる）。
   */
  const warnDaysOff = async (dates: readonly string[]) => {
    const unique = [...new Set(dates)].sort();
    if (unique.length === 0) return;
    try {
      const marks = await getDayOffMarks({ from: unique[0], to: unique[unique.length - 1] });
      const hits = unique
        .map((date) => ({ date, reasons: dayOffReasonsOn(date, marks, calendars, t('calendar.weeklyDayOff')) }))
        .filter((h) => h.reasons != null);
      if (hits.length === 0) return;
      notify(hits.length === 1 ? 'calendar.placedOnDayOff' : 'calendar.placedOnDaysOff', 'warning', {
        date: formatDate(hits[0].date), reasons: hits[0].reasons ?? '', count: hits.length,
      });
    } catch {
      // 知らせだけ出さない
    }
  };

  /** 書いた予定の回の日（繰り返しは今日か先頭の回から 62 日ぶん）。 */
  const datesOfWritten = async (written: CalendarEvent): Promise<string[]> => {
    const first = toZonedPoint(Date.parse(written.start), timeZone).date;
    const from = written.kind === 'RECURRING' && first < today() ? today() : first;
    const span = written.kind === 'RECURRING' ? WARN_RECURRING_DAYS : Math.ceil(written.duration_minutes / 1440);
    const occurrences = await getOccurrences({ from, to: addDays(from, span) }, timeZone);
    return occurrences.filter((o) => o.event_id === written.id).map((o) => o.date);
  };

  const warnDaysOffOf = (written: CalendarEvent | null) => {
    if (!written || !notifiesDayOff(written.event_type)) return;
    void datesOfWritten(written).then(warnDaysOff, () => undefined);
  };

  const refresh = () => {
    for (const queryKey of queriesAfterEventWrite()) void qc.invalidateQueries({ queryKey });
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
    if (change.occurrence.is_imported) return;
    const eventId = change.occurrence.event_id;
    // 応答を待たずに新しい位置で見せる（失敗したら取り直して戻る）。
    patchOccurrences((list) => applyScheduleToOccurrences(list, change.occurrence.id, change.after, change.scope === 'occurrence'));
    const event = change.scope === 'event' ? await getEvent(eventId) : null;
    const written = await sendCalendarRequest(rescheduleRequest(change, event));
    if (!written) return;
    setHistory((h) => withEventVersion(recordOperation(h, rescheduleEntryOf(change, written.version)), eventId, written.version));
    afterWrite(eventId, written);
    if (change.after.date !== change.occurrence.date && notifiesDayOff(change.occurrence.event_type)) {
      void warnDaysOff([change.after.date]);
    }
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

  // ── 済み（タスクの分類の回、ADR-0025）──────────────────────────────────

  /** 済みを切り替える。応答を待たずに見せ、失敗したら取り直して戻る。予定の版は進まない（履歴はそのまま）。 */
  const toggleDone = (occurrence: CalendarOccurrence) => exclusive(async () => {
    if (occurrence.is_imported) return;
    const done = !occurrence.is_done;
    patchOccurrences((list) => withOccurrenceDone(list, occurrence.id, done));
    await sendCalendarRequest(occurrenceDoneRequest(occurrence, done));
    void qc.invalidateQueries({ queryKey: [OCCURRENCES_QUERY] });
  });

  // ── 作る・直す・消す ──────────────────────────────────────────────────

  const openCreate = (date: string, startMinute?: number, endMinute?: number) => setEditTarget({
    form: newEventForm({
      date, startMinute, endMinute, timeZone, today: today(), calendarId: calendarForNewEvent(calendars),
    }),
    context: { mode: 'create' },
  });

  const openEdit = (occurrence: CalendarOccurrence) => exclusive(async () => {
    if (occurrence.is_imported) {
      setImportedTarget(occurrence);
      return;
    }
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

  const askDeleteScope = deleteTarget != null && deleteTarget.is_recurring && deleteTarget.series_key != null;

  const dialogs = (
    <>
      {editTarget && (
        <EventEditDialog
          target={editTarget}
          viewerTimeZone={timeZone}
          tasks={tasks}
          calendars={(calendars ?? []).filter((c) => c.kind === 'EVENTS')}
          onClose={() => setEditTarget(null)}
          onSaved={(written) => { afterDialogWrite('calendar.saved'); warnDaysOffOf(written); }}
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

      {/* 取り込んだ予定は読み取り専用（ADR-0037）。中身と、どこで直すかだけを見せる */}
      <Dialog open={importedTarget != null} onClose={() => setImportedTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ wordBreak: 'break-word' }}>{importedTarget?.title}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: 14 }}>
          {importedTarget && (
            <>
              <div>
                {formatDate(importedTarget.date)}
                {'  '}
                {formatOccurrenceTimeRange(importedTarget, timeZone) ?? t('calendar.allDay')}
              </div>
              {importedTarget.location && <div>{importedTarget.location}</div>}
              <div>
                {t('calendar.importedFrom', {
                  name: (calendars ?? []).find((c) => c.id === importedTarget.calendar_id)?.name ?? '',
                })}
              </div>
              <div style={{ fontSize: 12, opacity: 0.75 }}>{t('calendar.importedReadOnly')}</div>
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportedTarget(null)}>{t('calendar.close')}</Button>
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
    </>
  );

  return {
    busy,
    canUndo: !busy && canUndo(history),
    canRedo: !busy && canRedo(history),
    reschedule: (change: OccurrenceReschedule) => void reschedule(change),
    undo: () => void undo(),
    redo: () => void redo(),
    openCreate,
    openEdit: (occurrence: CalendarOccurrence) => void openEdit(occurrence),
    toggleDone: (occurrence: CalendarOccurrence) => void toggleDone(occurrence),
    askDelete: (occurrence: CalendarOccurrence) => { if (!occurrence.is_imported) setDeleteTarget(occurrence); },
    exclusive,
    refresh,
    notify,
    dialogs,
    /** 予定のカレンダー（読み込み前は undefined） */
    calendars,
    /** 休みの日に置いたら知らせる（タスクの一覧から落としたときなど） */
    warnDaysOff: (dates: readonly string[]) => void warnDaysOff(dates),
  };
};
