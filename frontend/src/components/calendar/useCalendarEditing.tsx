import React, { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { QueryKey } from '@tanstack/react-query';
import {
  Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Snackbar,
} from '@mui/material';
import { useI18n } from '../../i18n';
import type { TranslationKey } from '../../i18n/translations';
import type { CalendarEvent, CalendarOccurrence, Task } from '../../types';
import { getBusinessCalendars, getEvent, sendCalendarRequest } from '../../api/calendar';
import EventEditDialog from './EventEditDialog';
import type { EventEditTarget } from './EventEditDialog';
import RecurringScopeDialog from './RecurringScopeDialog';
import type { OccurrenceReschedule } from './calendarInteractions';
import { formFromEvent, newEventForm, planOccurrenceDelete } from '../../calendar/eventForm';
import type { RecurringScope } from '../../calendar/eventForm';
import type { RescheduleEntry } from '../../calendar/calendarRequests';
import {
  applyScheduleToOccurrences, errorDetailOf, isConflictError, redoRequest, rescheduleEntryOf, rescheduleRequest,
  undoRequest, withEventVersion, withOccurrenceEventVersion,
} from '../../calendar/calendarRequests';
import type { OperationHistory } from '../../calendar/operationHistory';
import {
  canRedo, canUndo, emptyHistory, recordOperation, redoOperation, undoOperation,
} from '../../calendar/operationHistory';
import { queriesAfterEventWrite } from '../../calendar/calendarQueries';
import { toZonedPoint } from '../../calendar/zonedTime';

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
 */
export const useCalendarEditing = ({ occurrencesKey, timeZone, tasks }: Options) => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data: businessCalendars } = useQuery({ queryKey: ['business-calendars'], queryFn: getBusinessCalendars });

  const [history, setHistory] = useState<OperationHistory<RescheduleEntry>>(() => emptyHistory<RescheduleEntry>());
  const [editTarget, setEditTarget] = useState<EventEditTarget | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CalendarOccurrence | null>(null);
  const [notice, setNotice] = useState<CalendarNotice | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);

  const today = () => toZonedPoint(Date.now(), timeZone).date;
  const notify = (key: TranslationKey, severity: CalendarNotice['severity'], params?: Record<string, string | number>) =>
    setNotice({ message: t(key, params), severity });

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

  const askDeleteScope = deleteTarget != null && deleteTarget.is_recurring && deleteTarget.series_key != null;

  const dialogs = (
    <>
      {editTarget && (
        <EventEditDialog
          target={editTarget}
          viewerTimeZone={timeZone}
          tasks={tasks}
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
    askDelete: setDeleteTarget,
    exclusive,
    refresh,
    notify,
    dialogs,
  };
};
