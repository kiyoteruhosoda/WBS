import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, ButtonBase, Divider, ListItemButton, ListItemText, Popover, Tooltip } from '@mui/material';
import { ds } from '../theme';
import { useI18n } from '../i18n';
import { getTasks } from '../api/tasks';
import { getOccurrences } from '../api/calendar';
import { getTimeEntries } from '../api/timeEntries';
import { OCCURRENCES_QUERY } from '../calendar/calendarQueries';
import { resolveTimeZone, toZonedPoint } from '../calendar/zonedTime';
import { pickerHead, recentTaskIds, scheduledTaskIds } from '../projects/taskPicker';
import { useProjectScope } from '../projects/useProjectScope';
import TaskPicker from './TaskPicker';
import { ChevronDownIcon, PlayIcon, StopIcon, WarningTriangleIcon } from './icons';
import { LONG_RUNNING_MS, elapsedOf } from '../timer/timerState';
import { formatExactDuration } from '../utils/format';
import { useProjectedTimeEntry, usePressNotice, useTimerWrites } from '../timer/useTimer';
import { isPendingEntry } from '../timer/pendingPresses';
import TimerFailureNotice from './TimerFailureNotice';
import PressNoticeView from './PressNotice';

// 打刻ボタン（task #154）。全画面の上部に常に出す。
// 普段は ▶ 開始 / ■ 停止 を押すだけ。タスクはその場で変えられるが、変えなくてよい
// （省くとサーバが「いまの予定のタスク → 直前の打刻のタスク → タスクなし」の順で決める）。
// 選び方は締めの画面と同じ部品（TaskPicker。task #189 / ADR-0026）: 先頭に「いまの予定のタスク・直前に
// 使ったタスク」、あとはプロジェクトの木で束ねる（サイドバーの範囲の中が先）。

/** 「直前に使った」を探す長さ（打刻ボタンを開いたときだけ引く）。 */
const RECENT_DAYS = 7;
// 押下は端末に溜めてから送る（task #192・ADR-0028）。送れていない分は「未送信 n 件」と出し、
// つながったとき・画面に戻ったとき・しばらくおきに送り直す。溜まった押下を送るのはこの部品（常に出ている）。

/** 溜まった押下を送り直す間隔（つながっていて、溜まっているときだけ） */
const RESEND_INTERVAL_MS = 30_000;

const BUTTON_HEIGHT = 44;

const TimerButton: React.FC = () => {
  const { t, timezone } = useI18n();
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  /** 選び方を開いた時刻（「いまの予定」「直前」の基準。開いている間は動かさない） */
  const [openedAt, setOpenedAt] = useState(() => Date.now());
  const openMenu = (anchor: HTMLElement) => {
    setOpenedAt(Date.now());
    setMenuAnchor(anchor);
  };
  const [nowMs, setNowMs] = useState(() => Date.now());

  const { snapshot, pendingCount, pendingStart, stateUnknown } = useProjectedTimeEntry();
  const entry = snapshot?.current.entry ?? null;
  const pendingEntry = entry !== null && isPendingEntry(entry);

  useEffect(() => {
    if (!entry) return undefined;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [entry]);

  const menuOpen = Boolean(menuAnchor);
  const { data: tasks, isLoading: tasksLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => getTasks(),
    enabled: menuOpen,
  });
  const { scope, projects } = useProjectScope();

  // 先頭の候補: いまの時間の予定のタスク（今日の回は「今日」の画面と同じ鍵で引く）と、直前の打刻のタスク
  const timeZone = resolveTimeZone(timezone);
  const today = toZonedPoint(openedAt, timeZone).date;
  const { data: occurrences } = useQuery({
    queryKey: [OCCURRENCES_QUERY, today, today, timeZone],
    queryFn: () => getOccurrences({ from: today, to: today }, timeZone),
    enabled: menuOpen,
  });
  const { data: recentEntries } = useQuery({
    // 打刻を書いたら読み直させる鍵（timer/useTimer の ['time-entries', 'list']）の下に置く
    queryKey: ['time-entries', 'list', 'recent', today],
    queryFn: () => getTimeEntries(
      new Date(openedAt - RECENT_DAYS * 86_400_000).toISOString(), new Date(openedAt + 60_000).toISOString(),
    ),
    enabled: menuOpen,
  });
  const head = useMemo(() => pickerHead(
    scheduledTaskIds([{ startMs: openedAt, endMs: openedAt + 60_000 }], occurrences ?? []),
    recentTaskIds(recentEntries ?? [], openedAt),
  ), [occurrences, recentEntries, openedAt]);

  const { start, stop, changeTask, sendPending, busy, failure, clearFailure } = useTimerWrites();
  const { notice, clear: clearNotice } = usePressNotice();

  // 溜まった押下を送る: 開いたとき・つながったとき・画面に戻ったとき・溜まっている間はしばらくおきに
  useEffect(() => {
    const resend = () => {
      if (navigator.onLine) void sendPending();
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') resend();
    };
    resend();
    window.addEventListener('online', resend);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('online', resend);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [sendPending]);
  useEffect(() => {
    if (pendingCount === 0) return undefined;
    const timer = window.setInterval(() => {
      if (navigator.onLine) void sendPending();
    }, RESEND_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [pendingCount, sendPending]);

  const chooseTask = (taskId: number | null) => {
    setMenuAnchor(null);
    if (entry) {
      changeTask.mutate({ id: entry.id, taskId });
    } else {
      start(taskId, taskId === null ? null : (tasks ?? []).find((task) => task.id === taskId)?.title);
    }
  };

  const elapsedMs = entry && snapshot ? elapsedOf(snapshot, entry, nowMs) : 0;
  const longRunning = entry !== null && (entry.is_long_running || elapsedMs > LONG_RUNNING_MS);

  const segment = {
    height: BUTTON_HEIGHT, display: 'flex', alignItems: 'center', gap: '6px',
    font: 'inherit', fontSize: 14, fontWeight: 700, whiteSpace: 'nowrap',
  } as const;

  return (
    <>
      {entry ? (
        <Box
          role="group"
          sx={{
            display: 'flex', alignItems: 'stretch', minWidth: 0, borderRadius: '8px', overflow: 'hidden',
            border: `1px solid ${longRunning ? ds.warnText : ds.primaryPaleBorder}`,
            bgcolor: longRunning ? ds.warnPale : ds.primaryPale,
          }}
        >
          <ButtonBase
            onClick={(e) => openMenu(e.currentTarget)}
            // 溜まった Start はまだサーバに無いので、タスクを付け替えられない（送れたら付け替えられる）
            disabled={busy || pendingEntry}
            aria-label={t('timer.changeTask')}
            aria-haspopup="menu"
            sx={{
              ...segment, px: '10px', minWidth: 0, color: ds.text, fontWeight: 500,
              maxWidth: { xs: 72, sm: 220 },
            }}
          >
            <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {entry.task_title ?? t(pendingStart?.taskId === undefined && pendingEntry ? 'timer.taskOnSend' : 'timer.unassigned')}
            </Box>
            {!pendingEntry && <ChevronDownIcon size={14} />}
          </ButtonBase>
          <Tooltip title={longRunning ? t('timer.longRunning') : ''} enterTouchDelay={0}>
            <Box
              sx={{
                ...segment, px: { xs: '6px', sm: '8px' }, color: longRunning ? ds.warnText : ds.primary,
                fontVariantNumeric: 'tabular-nums', letterSpacing: '0.02em',
              }}
              aria-label={`${t('timer.elapsed')} ${formatExactDuration(elapsedMs / 1000)}`}
            >
              {longRunning && <WarningTriangleIcon size={16} />}
              {formatExactDuration(elapsedMs / 1000)}
            </Box>
          </Tooltip>
          <ButtonBase
            onClick={stop}
            disabled={busy}
            aria-label={t('timer.stop')}
            sx={{
              ...segment, px: { xs: '10px', sm: '14px' }, color: '#fff', bgcolor: ds.dangerText,
              '&:hover': { bgcolor: '#A32116' },
            }}
          >
            <StopIcon size={16} />
            <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>{t('timer.stop')}</Box>
          </ButtonBase>
        </Box>
      ) : (
        <Box sx={{ display: 'flex', alignItems: 'stretch', borderRadius: '8px', overflow: 'hidden', flexShrink: 0 }}>
          <ButtonBase
            onClick={() => start()}
            // 控えを読めなかった（オフラインで開いた）ときも押せる。走っていればサーバが止めて切り替える
            disabled={busy || (!snapshot && !stateUnknown)}
            aria-label={t('timer.start')}
            sx={{
              ...segment, pl: '14px', pr: '14px', color: '#fff', bgcolor: ds.success,
              '&:hover': { bgcolor: ds.successDark },
            }}
          >
            <PlayIcon size={16} />
            {t('timer.start')}
          </ButtonBase>
          <ButtonBase
            onClick={(e) => openMenu(e.currentTarget)}
            disabled={busy || (!snapshot && !stateUnknown)}
            aria-label={t('timer.startWithTask')}
            aria-haspopup="menu"
            sx={{
              ...segment, px: '8px', color: '#fff', bgcolor: ds.success,
              borderLeft: '1px solid rgba(255,255,255,0.35)',
              '&:hover': { bgcolor: ds.successDark },
            }}
          >
            <ChevronDownIcon size={16} />
          </ButtonBase>
        </Box>
      )}

      <Popover
        anchorEl={menuAnchor}
        open={menuOpen}
        onClose={() => setMenuAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        slotProps={{ paper: { sx: { width: 340, maxWidth: 'calc(100vw - 32px)', maxHeight: 'min(560px, calc(100vh - 96px))', display: 'flex', flexDirection: 'column' } } }}
      >
        <TaskPicker
          tasks={tasks ?? []}
          projects={projects}
          head={head}
          scope={scope}
          selectedTaskId={entry?.task_id ?? null}
          loading={tasksLoading}
          onChoose={chooseTask}
          autoFocus
          maxHeight="min(440px, calc(100vh - 220px))"
          before={(
            <>
              <Box sx={{ px: '16px', pt: '10px', fontSize: 12, color: ds.textMuted }}>
                {entry ? t('timer.changeTask') : t('timer.startWithTask')}
              </Box>
              <ListItemButton
                selected={entry !== null && entry.task_id === null}
                onClick={() => chooseTask(null)}
                sx={{ minHeight: 44 }}
              >
                <ListItemText primary={t('timer.unassigned')} slotProps={{ primary: { sx: { fontSize: 14 } } }} />
              </ListItemButton>
              <Divider />
            </>
          )}
        />
      </Popover>

      {pendingCount > 0 && (
        <Tooltip title={t('timer.pendingHint')} enterTouchDelay={0}>
          <Box
            role="status"
            sx={{
              display: 'flex', alignItems: 'center', height: 28, px: '8px', borderRadius: '14px', flexShrink: 0,
              fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', color: ds.warnText, bgcolor: ds.warnPale,
            }}
          >
            {t('timer.pending', { count: pendingCount })}
          </Box>
        </Tooltip>
      )}

      <TimerFailureNotice failure={failure} onClose={clearFailure} />
      <PressNoticeView notice={notice} onClose={clearNotice} />
    </>
  );
};

export default TimerButton;
