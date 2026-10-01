import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, ButtonBase, CircularProgress, Divider, Menu, MenuItem, Tooltip } from '@mui/material';
import { ds } from '../theme';
import { useI18n } from '../i18n';
import { getTasks } from '../api/tasks';
import { ChevronDownIcon, PlayIcon, StopIcon, WarningTriangleIcon } from './icons';
import { LONG_RUNNING_MS, elapsedOf } from '../timer/timerState';
import { formatExactDuration } from '../utils/format';
import { useCurrentTimeEntry, useTimerWrites } from '../timer/useTimer';
import TimerFailureNotice from './TimerFailureNotice';

// 打刻ボタン（task #154）。全画面の上部に常に出す。
// 普段は ▶ 開始 / ■ 停止 を押すだけ。タスクはその場で変えられるが、変えなくてよい
// （省くとサーバが「いまの予定のタスク → 直前の打刻のタスク → タスクなし」の順で決める）。

const BUTTON_HEIGHT = 44;

const TimerButton: React.FC = () => {
  const { t } = useI18n();
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const { data: snapshot } = useCurrentTimeEntry();
  const entry = snapshot?.current.entry ?? null;

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
  const openTasks = (tasks ?? []).filter((task) => task.status !== 'DONE' && task.status !== 'CANCELLED');

  const { start, stop, changeTask, busy, failure, clearFailure } = useTimerWrites();

  const chooseTask = (taskId: number | null) => {
    setMenuAnchor(null);
    if (entry) {
      changeTask.mutate({ id: entry.id, taskId });
    } else {
      start.mutate(taskId);
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
            onClick={(e) => setMenuAnchor(e.currentTarget)}
            disabled={busy}
            aria-label={t('timer.changeTask')}
            aria-haspopup="menu"
            sx={{
              ...segment, px: '10px', minWidth: 0, color: ds.text, fontWeight: 500,
              maxWidth: { xs: 72, sm: 220 },
            }}
          >
            <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {entry.task_title ?? t('timer.unassigned')}
            </Box>
            <ChevronDownIcon size={14} />
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
            onClick={() => stop.mutate()}
            disabled={busy}
            aria-label={t('timer.stop')}
            sx={{
              ...segment, px: { xs: '10px', sm: '14px' }, color: '#fff', bgcolor: ds.dangerText,
              '&:hover': { bgcolor: '#A32116' },
            }}
          >
            {stop.isPending ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : <StopIcon size={16} />}
            <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>{t('timer.stop')}</Box>
          </ButtonBase>
        </Box>
      ) : (
        <Box sx={{ display: 'flex', alignItems: 'stretch', borderRadius: '8px', overflow: 'hidden', flexShrink: 0 }}>
          <ButtonBase
            onClick={() => start.mutate(undefined)}
            disabled={busy || !snapshot}
            aria-label={t('timer.start')}
            sx={{
              ...segment, pl: '14px', pr: '14px', color: '#fff', bgcolor: ds.success,
              '&:hover': { bgcolor: ds.successDark },
            }}
          >
            {start.isPending ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : <PlayIcon size={16} />}
            {t('timer.start')}
          </ButtonBase>
          <ButtonBase
            onClick={(e) => setMenuAnchor(e.currentTarget)}
            disabled={busy || !snapshot}
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

      <Menu
        anchorEl={menuAnchor}
        open={menuOpen}
        onClose={() => setMenuAnchor(null)}
        slotProps={{ paper: { sx: { maxHeight: 360, minWidth: 220, maxWidth: 'calc(100vw - 32px)' } } }}
      >
        <MenuItem disabled sx={{ fontSize: 12, opacity: '1 !important', color: ds.textMuted }}>
          {entry ? t('timer.changeTask') : t('timer.startWithTask')}
        </MenuItem>
        <MenuItem
          selected={entry !== null && entry.task_id === null}
          onClick={() => chooseTask(null)}
          sx={{ fontSize: 14, minHeight: 44 }}
        >
          {t('timer.unassigned')}
        </MenuItem>
        <Divider />
        {tasksLoading && (
          <MenuItem disabled sx={{ justifyContent: 'center' }}><CircularProgress size={18} /></MenuItem>
        )}
        {!tasksLoading && openTasks.length === 0 && (
          <MenuItem disabled sx={{ fontSize: 14 }}>{t('timer.noTasks')}</MenuItem>
        )}
        {openTasks.map((task) => (
          <MenuItem
            key={task.id}
            selected={entry?.task_id === task.id}
            onClick={() => chooseTask(task.id)}
            sx={{ fontSize: 14, minHeight: 44, whiteSpace: 'normal' }}
          >
            {task.title}
          </MenuItem>
        ))}
      </Menu>

      <TimerFailureNotice failure={failure} onClose={clearFailure} />
    </>
  );
};

export default TimerButton;
