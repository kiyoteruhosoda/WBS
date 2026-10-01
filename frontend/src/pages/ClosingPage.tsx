import React, { useEffect, useMemo, useRef, useState } from 'react';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, MenuItem, Popover, Select,
  Snackbar, ToggleButton, Tooltip,
} from '@mui/material';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import type { CalendarOccurrence, TimeEntry } from '../types';
import {
  CLOSING_BOARD_KEY, PENDING_CLOSINGS_KEY, getClosingBoard, getPendingClosings, sendClosingRequest, sendClosingRequests,
} from '../api/closing';
import { getTasks } from '../api/tasks';
import { TODAY_SUMMARY_KEY } from '../api/today';
import { ACTUALS_KEY } from '../api/actuals';
import { getCategories } from '../api/categories';
import { categoryColor, ds } from '../theme';
import { buildLinkedTasks } from '../calendar/taskScheduling';
import { formatOccurrenceTimeRange, groupSegmentsByDate } from '../calendar/daySegments';
import { resolveTimeZone, toZonedPoint } from '../calendar/zonedTime';
import {
  PERIOD_PARAM, nextPeriod, parsePeriodParam, periodDates, periodLabelParts, periodOf, previousPeriod,
} from '../closing/closingPeriods';
import type { FindingItem } from '../closing/closingBoard';
import {
  assignCandidates, buildFindingItems, buildTotalsTable, canTurnIntoEntry, entriesOverlappingOccurrence, entryEndMs,
  entryMarksOf, entryStartMs, groupEntrySegmentsByDate, missedOccurrenceIds,
} from '../closing/closingBoard';
import type { ClosingRequest, EntryRange } from '../closing/closingRequests';
import {
  assignTaskRequest, closePeriodRequest, closingFailureOf, createEntryRequest, deleteEntriesRequests, editEntryRequest,
  fromOccurrenceRequest, mergeEntriesRequest, reopenPeriodRequest, rescheduleEntryRequest, splitEntryRequest,
} from '../closing/closingRequests';
import { splitInstantAt } from '../closing/entryGestures';
import ClosingGrid from '../components/closing/ClosingGrid';
import FindingsPanel from '../components/closing/FindingsPanel';
import TotalsTable from '../components/closing/TotalsTable';
import AssignTaskDialog from '../components/closing/AssignTaskDialog';
import EntryEditDialog from '../components/closing/EntryEditDialog';
import { entryElementId, occurrenceElementId } from '../components/closing/closingElementIds';
import { ChevronLeftIcon, ChevronRightIcon } from '../components/icons';

interface Notice {
  message: string;
  severity: 'success' | 'info' | 'warning' | 'error';
}

/** 一覧から飛んだ打刻・回を目立たせておく長さ。 */
const FOCUS_MS = 2500;

/**
 * 締め（task #161 / ADR-0012・ADR-0016）。普段は Start / Stop しかさせない代わりに、ここで打刻を楽に直して
 * 期間を確定する。左に予定・右に打刻の時間グリッド、気付かせる物の一覧、日ごと・タスクごとの合計。
 */
const ClosingPage: React.FC = () => {
  const { t, timezone } = useI18n();
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const userTimeZone = resolveTimeZone(timezone);

  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const pendingQuery = useQuery({ queryKey: PENDING_CLOSINGS_KEY, queryFn: getPendingClosings });
  const requested = parsePeriodParam(searchParams.get(PERIOD_PARAM));
  const currentFirstDay = pendingQuery.data?.current.first_day
    ?? periodOf(toZonedPoint(nowMs, userTimeZone).date).first_day;
  // 指定が無ければ、いちばん古い未確定の期間（無ければ今の期間）
  const firstDay = requested
    ?? (pendingQuery.isPending ? null : pendingQuery.data?.pending[0]?.first_day ?? currentFirstDay);

  const boardQuery = useQuery({
    queryKey: [CLOSING_BOARD_KEY, firstDay],
    queryFn: () => getClosingBoard(firstDay as string),
    enabled: firstDay != null,
    placeholderData: keepPreviousData,
  });
  const board = boardQuery.data && boardQuery.data.period.first_day === firstDay ? boardQuery.data : null;
  const { data: tasks } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });

  const timeZone = resolveTimeZone(board?.period.time_zone ?? userTimeZone);
  const readOnly = board?.period.status === 'closed';
  const dates = useMemo(() => (board ? periodDates(board.period) : []), [board]);

  const linkedTasks = useMemo(() => buildLinkedTasks(tasks ?? [], categories ?? [], categoryColor), [tasks, categories]);
  const occurrenceSegments = useMemo(
    () => groupSegmentsByDate((board?.occurrences ?? []).filter((o) => !o.is_all_day), timeZone),
    [board, timeZone],
  );
  const entrySegments = useMemo(
    () => groupEntrySegmentsByDate(board?.entries ?? [], timeZone, nowMs, dates),
    [board, timeZone, nowMs, dates],
  );
  const findings = useMemo(() => (board ? buildFindingItems(board, nowMs) : []), [board, nowMs]);
  const marks = useMemo(() => (board ? entryMarksOf(board) : { unassigned: new Set<number>(), longRunning: new Set<number>(), overlapping: new Set<number>() }), [board]);
  const missed = useMemo(() => (board ? missedOccurrenceIds(board) : new Set<string>()), [board]);
  const totals = useMemo(() => buildTotalsTable(board?.daily_totals ?? [], dates), [board, dates]);

  // ── 選択・目立たせ ─────────────────────────────────────────────────────
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [focused, setFocused] = useState<{ entryIds: ReadonlySet<number>; occurrenceId: string | null }>({ entryIds: new Set(), occurrenceId: null });
  const focusTimer = useRef<number | null>(null);
  const [splitMode, setSplitMode] = useState(false);

  // 期間を変えたら選択を捨てる。打刻が消えたら選択からも外す。
  useEffect(() => { setSelected(new Set()); setSplitMode(false); }, [firstDay]);
  const entriesById = useMemo(() => new Map((board?.entries ?? []).map((e) => [e.id, e])), [board]);
  const selectedEntries = useMemo(
    () => [...selected].map((id) => entriesById.get(id)).filter((e): e is TimeEntry => e != null),
    [selected, entriesById],
  );

  const focus = (entryIds: number[], occurrenceId: string | null) => {
    if (focusTimer.current != null) window.clearTimeout(focusTimer.current);
    setFocused({ entryIds: new Set(entryIds), occurrenceId });
    focusTimer.current = window.setTimeout(() => setFocused({ entryIds: new Set(), occurrenceId: null }), FOCUS_MS);
    const target = entryIds.length > 0 ? entryElementId(entryIds[0]) : occurrenceId ? occurrenceElementId(occurrenceId) : null;
    if (target) {
      window.requestAnimationFrame(() => document.getElementById(target)?.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' }));
    }
  };
  useEffect(() => () => { if (focusTimer.current != null) window.clearTimeout(focusTimer.current); }, []);

  // ── 書き込み ─────────────────────────────────────────────────────────
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const notify = (key: TranslationKey, severity: Notice['severity'], params?: Record<string, string | number>) =>
    setNotice({ message: t(key, params), severity });

  const refresh = (periodChanged = false) => {
    void qc.invalidateQueries({ queryKey: [CLOSING_BOARD_KEY] });
    // 上部の打刻ボタン（いま走っている打刻）と「今日」の要約も打刻を見ている（timer/useTimer.ts と同じ）
    void qc.invalidateQueries({ queryKey: ['time-entries'] });
    void qc.invalidateQueries({ queryKey: TODAY_SUMMARY_KEY });
    if (periodChanged) {
      void qc.invalidateQueries({ queryKey: PENDING_CLOSINGS_KEY });
      // 実績（work_logs）が変わる
      void qc.invalidateQueries({ queryKey: ['tasks'] });
      void qc.invalidateQueries({ queryKey: ['task'] });
      void qc.invalidateQueries({ queryKey: ['worklogs'] });
      void qc.invalidateQueries({ queryKey: ['kpi'] });
      // 実績の見える化（残を見直す・期間ごと・ガントの実績の帯。task #162）
      void qc.invalidateQueries({ queryKey: ACTUALS_KEY });
    }
  };

  /** 書き込みを 1 つずつ。成功したら true（失敗の理由は知らせに出し、理由に出てきた打刻を選ぶ）。 */
  const run = async (write: () => Promise<void>, done?: TranslationKey, periodChanged = false): Promise<boolean> => {
    if (busyRef.current) return false;
    busyRef.current = true;
    setBusy(true);
    try {
      await write();
      if (done) notify(done, 'success');
      return true;
    } catch (error) {
      const failure = closingFailureOf(error);
      setNotice({ message: t(failure.key, failure.params), severity: 'error' });
      if (failure.entryIds.length > 0) {
        setSelected(new Set(failure.entryIds));
        focus(failure.entryIds, null);
      }
      return false;
    } finally {
      busyRef.current = false;
      setBusy(false);
      refresh(periodChanged);
    }
  };

  const send = (request: ClosingRequest | null, done?: TranslationKey): Promise<boolean> => {
    if (!request) return Promise.resolve(false);
    return run(async () => { await sendClosingRequest(request); }, done);
  };

  const clearSelectionIf = (ok: boolean) => { if (ok) setSelected(new Set()); };

  const onReschedule = (entryId: number, range: EntryRange) => void send(rescheduleEntryRequest(entryId, range));
  const onCreate = (range: EntryRange) => void send(createEntryRequest(range), 'closing.created');

  const onSplitAt = (entry: TimeEntry, date: string, offsetMinute: number, fine: boolean) => {
    const at = splitInstantAt({ startMs: entryStartMs(entry), endMs: entryEndMs(entry, nowMs) }, date, offsetMinute, timeZone, fine);
    if (at == null) {
      notify('closing.error.splitOutside', 'warning');
      return;
    }
    void send(splitEntryRequest(entry.id, at), 'closing.splitDone');
  };

  const toggleEntry = (entry: TimeEntry) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(entry.id)) next.delete(entry.id);
    else next.add(entry.id);
    return next;
  });

  const [assignOpen, setAssignOpen] = useState(false);
  const candidates = useMemo(
    () => (assignOpen ? assignCandidates(selectedEntries, board?.occurrences ?? [], tasks ?? [], nowMs) : []),
    [assignOpen, selectedEntries, board, tasks, nowMs],
  );
  const assign = (taskId: number | null) => {
    setAssignOpen(false);
    const ids = selectedEntries.map((e) => e.id);
    void send(assignTaskRequest(ids, taskId), 'closing.assigned').then(clearSelectionIf);
  };

  const merge = () => {
    const ids = selectedEntries.map((e) => e.id);
    void send(mergeEntriesRequest(ids), 'closing.merged').then(clearSelectionIf);
  };

  const [editEntry, setEditEntry] = useState<TimeEntry | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number[] | null>(null);
  const deleteEntries = (ids: number[]) => {
    setConfirmDelete(null);
    setEditEntry(null);
    void run(() => sendClosingRequests(deleteEntriesRequests(ids)), 'closing.deleted').then(clearSelectionIf);
  };

  // ── 予定の回 → 打刻（「予定どおり」） ─────────────────────────────────────
  const [occurrenceMenu, setOccurrenceMenu] = useState<{ occurrence: CalendarOccurrence; anchor: HTMLElement } | null>(null);
  const menuOverlaps = occurrenceMenu ? entriesOverlappingOccurrence(occurrenceMenu.occurrence, board?.entries ?? [], nowMs) : [];
  const asScheduled = (occurrence: CalendarOccurrence) => {
    setOccurrenceMenu(null);
    void send(fromOccurrenceRequest(occurrence), 'closing.fromOccurrenceDone');
  };

  // ── 確定・開け直し ─────────────────────────────────────────────────────
  const [confirmReopen, setConfirmReopen] = useState(false);
  const closePeriod = () => {
    if (!firstDay) return;
    void run(async () => { await sendClosingRequest(closePeriodRequest(firstDay)); }, 'closing.closedDone', true);
  };
  const reopenPeriod = () => {
    setConfirmReopen(false);
    if (!firstDay) return;
    void run(async () => { await sendClosingRequest(reopenPeriodRequest(firstDay)); }, 'closing.reopenedDone', true);
  };

  const jump = (item: FindingItem) => {
    if (item.entryIds.length > 0) {
      setSelected(new Set(item.entryIds));
      focus(item.entryIds, null);
      return;
    }
    if (item.occurrence) {
      const occurrence = item.occurrence;
      focus([], occurrence.id);
      // 飛んだ先で「予定どおり」をすぐ押せるように、回のメニューを開く
      window.setTimeout(() => {
        const el = document.getElementById(occurrenceElementId(occurrence.id));
        if (el) setOccurrenceMenu({ occurrence, anchor: el });
      }, 350);
    }
  };

  const goTo = (first: string) => setSearchParams((prev) => {
    const next = new URLSearchParams(prev);
    next.set(PERIOD_PARAM, first);
    return next;
  });

  // 前後の期間と、未確定の期間の一覧（今の期間も入れる）
  const periodOptions = useMemo(() => {
    const list = [...(pendingQuery.data?.pending ?? [])];
    const current = pendingQuery.data?.current;
    if (current && !list.some((p) => p.first_day === current.first_day)) list.push(current);
    if (firstDay && !list.some((p) => p.first_day === firstDay)) list.push(periodOf(firstDay));
    return list.sort((a, b) => a.first_day.localeCompare(b.first_day));
  }, [pendingQuery.data, firstDay]);
  const pendingSet = new Set((pendingQuery.data?.pending ?? []).map((p) => p.first_day));
  const labelOf = (first: string) => {
    const p = periodLabelParts(periodOf(first));
    return t('closing.periodLabel', { year: p.year, from: p.from, to: p.to });
  };

  const unassignedIds = board?.findings.unassigned_entry_ids ?? [];
  const canMerge = selectedEntries.length >= 2 && selectedEntries.every((e) => !e.is_running);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* 期間・状態・確定 */}
      <Box sx={{
        display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px',
        bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '8px', px: '12px', py: '8px',
      }}>
        <Tooltip title={t('closing.prevPeriod')}>
          <span>
            <IconButton size="small" disabled={!firstDay} onClick={() => firstDay && goTo(previousPeriod(firstDay).first_day)} aria-label={t('closing.prevPeriod')}>
              <ChevronLeftIcon size={18} />
            </IconButton>
          </span>
        </Tooltip>
        <Select
          size="small"
          value={firstDay ?? ''}
          onChange={(e) => goTo(String(e.target.value))}
          sx={{ minWidth: 220, fontWeight: 700 }}
          data-testid="closing-period-select"
        >
          {periodOptions.map((p) => (
            <MenuItem key={p.first_day} value={p.first_day}>
              {labelOf(p.first_day)}{pendingSet.has(p.first_day) ? ` — ${t('closing.statusOpen')}` : ''}
            </MenuItem>
          ))}
        </Select>
        <Tooltip title={t('closing.nextPeriod')}>
          <span>
            <IconButton
              size="small" aria-label={t('closing.nextPeriod')}
              disabled={!firstDay || firstDay >= currentFirstDay}
              onClick={() => firstDay && goTo(nextPeriod(firstDay).first_day)}
            >
              <ChevronRightIcon size={18} />
            </IconButton>
          </span>
        </Tooltip>
        {board && (
          <Chip
            size="small"
            color={readOnly ? 'success' : 'warning'}
            label={readOnly ? t('closing.statusClosed') : t('closing.statusOpen')}
            data-testid="closing-status"
          />
        )}
        <Box sx={{ flex: 1 }} />
        {board && (readOnly ? (
          <Button variant="outlined" disabled={busy} onClick={() => setConfirmReopen(true)} data-testid="closing-reopen">
            {t('closing.reopen')}
          </Button>
        ) : (
          <Tooltip title={unassignedIds.length > 0 ? t('closing.closeBlocked', { count: unassignedIds.length }) : ''}>
            <span>
              <Button variant="contained" disabled={busy} onClick={closePeriod} data-testid="closing-close">
                {t('closing.close')}
              </Button>
            </span>
          </Tooltip>
        ))}
      </Box>

      {(boardQuery.isError || pendingQuery.isError) && <Alert severity="error">{t('common.loadError')}</Alert>}
      {readOnly && board?.period.closed_at && (
        <Alert
          severity="success"
          action={(
            // 確定で実績が入ったら、残を手で見直す（残は自動で減らさない。task #162 / ADR-0017）
            <Button component={RouterLink} to="/actuals/review" color="inherit" size="small" data-testid="closing-review-remaining">
              {t('closing.reviewRemaining')}
            </Button>
          )}
        >
          {t('closing.closedReadOnly')}
        </Alert>
      )}

      {/* 打刻の操作 */}
      {board && !readOnly && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
          <ToggleButton
            size="small" value="split" selected={splitMode} onChange={() => setSplitMode((v) => !v)}
            sx={{ px: '12px' }} data-testid="closing-split-mode"
          >
            {t('closing.splitMode')}
          </ToggleButton>
          {unassignedIds.length > 0 && (
            <Button size="small" variant="outlined" color="error" onClick={() => setSelected(new Set(unassignedIds))}>
              {t('closing.selectUnassigned', { count: unassignedIds.length })}
            </Button>
          )}
          {selectedEntries.length > 0 && (
            <>
              <Box sx={{ fontSize: 13, color: ds.textSub, ml: '4px' }}>{t('closing.selectedCount', { count: selectedEntries.length })}</Box>
              <Button size="small" variant="contained" disabled={busy} onClick={() => setAssignOpen(true)} data-testid="closing-assign">
                {t('closing.assign')}
              </Button>
              <Button size="small" variant="outlined" disabled={busy || !canMerge} onClick={merge} data-testid="closing-merge">
                {t('closing.merge')}
              </Button>
              {selectedEntries.length === 1 && (
                <Button size="small" variant="outlined" disabled={busy} onClick={() => setEditEntry(selectedEntries[0])}>
                  {t('closing.edit')}
                </Button>
              )}
              <Button size="small" variant="outlined" color="error" disabled={busy} onClick={() => setConfirmDelete(selectedEntries.map((e) => e.id))}>
                {t('closing.delete')}
              </Button>
              <Button size="small" color="inherit" onClick={() => setSelected(new Set())}>{t('closing.clearSelection')}</Button>
            </>
          )}
          <Box sx={{ fontSize: 12, color: ds.textMuted, ml: 'auto' }}>
            {splitMode ? t('closing.splitHint') : t('closing.dragHint')}
          </Box>
        </Box>
      )}

      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', lg: 'row' }, gap: '12px', alignItems: 'stretch' }}>
        <Box sx={{
          flex: 1, minWidth: 0, border: `1px solid ${ds.border}`, borderRadius: '8px', overflow: 'hidden',
          height: { xs: 'calc(100vh - 220px)', md: 'calc(100vh - 260px)' }, minHeight: 520,
        }}>
          {board ? (
            <ClosingGrid
              dates={dates}
              timeZone={timeZone}
              nowMs={nowMs}
              occurrenceSegmentsByDate={occurrenceSegments}
              entrySegmentsByDate={entrySegments}
              linkedTasks={linkedTasks}
              marks={marks}
              missedOccurrenceIds={missed}
              selectedEntryIds={selected}
              focusedEntryIds={focused.entryIds}
              focusedOccurrenceId={focused.occurrenceId}
              readOnly={readOnly}
              splitMode={splitMode}
              onToggleEntry={toggleEntry}
              onOpenEntry={setEditEntry}
              onClearSelection={() => setSelected(new Set())}
              onOccurrenceClick={(occurrence, anchor) => setOccurrenceMenu({ occurrence, anchor })}
              onReschedule={onReschedule}
              onCreate={onCreate}
              onSplitAt={onSplitAt}
            />
          ) : (
            <Box sx={{ p: '16px', color: ds.textMuted, fontSize: 13 }}>{t('closing.loading')}</Box>
          )}
        </Box>
        <Box sx={{ width: { xs: '100%', lg: 320 }, flexShrink: 0 }}>
          <FindingsPanel items={findings} timeZone={timeZone} onJump={jump} />
        </Box>
      </Box>

      {board && <TotalsTable table={totals} />}

      {/* 予定の回のメニュー */}
      <Popover
        open={occurrenceMenu != null}
        anchorEl={occurrenceMenu?.anchor}
        onClose={() => setOccurrenceMenu(null)}
        anchorOrigin={{ vertical: 'center', horizontal: 'right' }}
        transformOrigin={{ vertical: 'center', horizontal: 'left' }}
      >
        {occurrenceMenu && (
          <Box sx={{ p: '12px 14px', maxWidth: 300, display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <Box sx={{ fontSize: 14, fontWeight: 700 }}>{occurrenceMenu.occurrence.title}</Box>
            <Box sx={{ fontSize: 12, color: ds.textSub }}>
              {occurrenceMenu.occurrence.date} {formatOccurrenceTimeRange(occurrenceMenu.occurrence, timeZone)}
              {occurrenceMenu.occurrence.task_id != null && linkedTasks.get(occurrenceMenu.occurrence.task_id)
                ? ` ・ ${linkedTasks.get(occurrenceMenu.occurrence.task_id)?.title}` : ''}
            </Box>
            {readOnly ? null : !canTurnIntoEntry(occurrenceMenu.occurrence, nowMs) ? (
              <Alert severity="info" sx={{ py: 0 }}>{t('closing.occurrenceNotEnded')}</Alert>
            ) : (
              <>
                {menuOverlaps.length > 0 && (
                  <Alert severity="warning" sx={{ py: 0 }} data-testid="occurrence-overlap-warning">
                    {t('closing.occurrenceOverlapWarning', { count: menuOverlaps.length })}
                  </Alert>
                )}
                <Button
                  variant="contained"
                  color={menuOverlaps.length > 0 ? 'warning' : 'primary'}
                  disabled={busy}
                  onClick={() => asScheduled(occurrenceMenu.occurrence)}
                  data-testid="occurrence-as-scheduled"
                >
                  {t('closing.asScheduled')}
                </Button>
              </>
            )}
          </Box>
        )}
      </Popover>

      {assignOpen && (
        <AssignTaskDialog
          open
          entryCount={selectedEntries.length}
          candidates={candidates}
          onCancel={() => setAssignOpen(false)}
          onChoose={assign}
        />
      )}

      {editEntry && (
        <EntryEditDialog
          entry={editEntry}
          timeZone={timeZone}
          nowMs={nowMs}
          onCancel={() => setEditEntry(null)}
          onSave={(range, memo) => { const id = editEntry.id; setEditEntry(null); void send(editEntryRequest(id, range, memo), 'closing.saved'); }}
          onDelete={() => setConfirmDelete([editEntry.id])}
        />
      )}

      <Dialog open={confirmDelete != null} onClose={() => setConfirmDelete(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('closing.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>{t('closing.deleteConfirm', { count: confirmDelete?.length ?? 0 })}</DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(null)}>{t('calendar.cancel')}</Button>
          <Button color="error" variant="contained" onClick={() => confirmDelete && deleteEntries(confirmDelete)}>{t('closing.delete')}</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={confirmReopen} onClose={() => setConfirmReopen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('closing.reopenConfirmTitle')}</DialogTitle>
        <DialogContent>{t('closing.reopenConfirm', { period: firstDay ? labelOf(firstDay) : '' })}</DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmReopen(false)}>{t('calendar.cancel')}</Button>
          <Button variant="contained" color="warning" onClick={reopenPeriod} data-testid="closing-reopen-confirm">{t('closing.reopen')}</Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={notice != null}
        autoHideDuration={notice?.severity === 'error' ? 8000 : 4000}
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

export default ClosingPage;
