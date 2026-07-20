import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, Button, CircularProgress, Alert, TextField } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { getDashboardToday, getDashboardKpi } from '../api/dashboard';
import { getTasks, completeTask } from '../api/tasks';
import { createWorklog } from '../api/worklogs';
import { getCategories } from '../api/categories';
import type { Task, Category } from '../types';
import { formatDate, formatShortDate, formatMonthDay, isDueToday, isOverdue, overdueDays, displayStatus, todayDate } from '../utils/format';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import StatusChip from '../components/StatusChip';
import PriorityChip from '../components/PriorityChip';
import ProgressBar from '../components/ProgressBar';
import CategoryDot from '../components/CategoryDot';
import { WarningTriangleIcon } from '../components/icons';

const card = {
  bgcolor: ds.paper,
  border: `1px solid ${ds.border}`,
  borderRadius: '10px',
} as const;

const sectionTitle = { fontSize: 15, fontWeight: 700, color: ds.text } as const;

// ユーザー設定のタイムゾーンでの「今日」を YYYY-MM-DD にする（作業ログの記録日に使う）
const todayYmd = (): string => {
  const d = todayDate();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

// いま取り組んでいるタスク1件分の詳細ブロック
const FocusTask: React.FC<{
  task: Task;
  categories?: Category[];
  onComplete: (task: Task) => void;
  onLogWork: (taskId: number, hours: number) => void;
  completePending: boolean;
  logPending: boolean;
}> = ({ task, categories, onComplete, onLogWork, completePending, logPending }) => {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [loggingWork, setLoggingWork] = useState(false);
  const [workHours, setWorkHours] = useState('');

  const due = ((): { text: string; urgent: boolean } => {
    if (!task.due_date) return { text: t('common.dueNone'), urgent: false };
    if (isOverdue(task)) return { text: `${formatDate(task.due_date)}（${t('common.overdueDays', { days: overdueDays(task) })}）`, urgent: true };
    if (isDueToday(task)) return { text: t('common.today'), urgent: true };
    return { text: formatDate(task.due_date), urgent: false };
  })();

  const catName = categories?.find((c) => c.id === task.category_id)?.name ?? t('common.uncategorized');

  return (
    <Box sx={{ p: '18px' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 13, color: ds.textSub }}>
        <CategoryDot categoryId={task.category_id} categories={categories} />
        {catName}
      </Box>
      <Box
        onClick={() => navigate(`/tasks/${task.id}`)}
        sx={{ fontSize: 22, fontWeight: 700, color: ds.text, mt: '4px', mb: '14px', cursor: 'pointer', '&:hover': { color: ds.primary } }}
      >
        {task.title}
      </Box>
      <Box sx={{ display: 'flex', gap: '40px', mb: '14px', flexWrap: 'wrap' }}>
        <Box>
          <Box sx={{ fontSize: 12, color: ds.textMuted, mb: '2px' }}>{t('dashboard.due')}</Box>
          <Box sx={{ fontSize: 15, fontWeight: 700, color: due.urgent ? ds.dangerText : ds.text }}>
            {due.text}
          </Box>
        </Box>
        <Box>
          <Box sx={{ fontSize: 12, color: ds.textMuted, mb: '2px' }}>{t('dashboard.status')}</Box>
          <StatusChip task={task} />
        </Box>
      </Box>
      <ProgressBar value={task.progress_percent} showLabel />
      <Box sx={{ display: 'flex', gap: '12px', mt: '16px', flexWrap: 'wrap' }}>
        <Button
          variant="contained"
          sx={{ flex: '1 1 180px' }}
          disabled={completePending}
          onClick={() => onComplete(task)}
        >
          {t('dashboard.complete')}
        </Button>
        <Button
          variant="outlined"
          sx={{ flex: '1 1 180px' }}
          onClick={() => { setLoggingWork(!loggingWork); setWorkHours(''); }}
        >
          {t('dashboard.logWork')}
        </Button>
      </Box>
      {loggingWork && (
        <Box sx={{ display: 'flex', gap: '10px', mt: '12px', alignItems: 'center' }}>
          <TextField
            size="small" type="number" label={t('dashboard.hoursToday')}
            value={workHours}
            onChange={(e) => setWorkHours(e.target.value)}
            slotProps={{ htmlInput: { min: 0, step: 0.5 } }}
            sx={{ width: 180 }}
          />
          <Button
            variant="contained" size="small"
            disabled={logPending || !workHours || Number(workHours) <= 0}
            onClick={() => {
              onLogWork(task.id, Number(workHours));
              setLoggingWork(false);
            }}
          >
            {t('dashboard.record')}
          </Button>
        </Box>
      )}
    </Box>
  );
};

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { t, lang, timezone } = useI18n();

  const { data: today, isLoading, error } = useQuery({ queryKey: ['dashboard-today'], queryFn: getDashboardToday });
  const { data: kpi } = useQuery({ queryKey: ['kpi'], queryFn: getDashboardKpi });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  const { data: allTasks } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['dashboard-today'] });
    qc.invalidateQueries({ queryKey: ['kpi'] });
    qc.invalidateQueries({ queryKey: ['tasks'] });
  };

  const complete = useMutation({
    mutationFn: (task: Task) => completeTask(task),
    onSuccess: invalidate,
  });

  // 進捗は作業ログ（実績時間）から自動算出されるため、記録で更新する
  const logWork = useMutation({
    mutationFn: ({ taskId, hours }: { taskId: number; hours: number }) =>
      createWorklog({ task_id: taskId, work_date: todayYmd(), hours, memo: null }),
    onSuccess: invalidate,
  });

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">{t('common.loadError')}</Alert>;

  const todayLabel = new Intl.DateTimeFormat(lang === 'ja' ? 'ja-JP' : 'en-US', {
    dateStyle: 'full',
    ...(timezone ? { timeZone: timezone } : {}),
  }).format(new Date());

  const buckets = today?.buckets;
  const doing = buckets?.DOING ?? [];
  const todayTasks = buckets?.TODAY ?? [];
  const overdue = buckets?.OVERDUE ?? [];

  // 進行中のタスクはすべて表示する（なければ今日のタスクの先頭1件）
  const focusTasks: Task[] = doing.length > 0 ? doing : todayTasks.slice(0, 1);

  // 今日の予定: 今日締切＋進行中＋遅延をまとめて表示
  const scheduleMap = new Map<number, Task>();
  [...overdue, ...todayTasks, ...doing].forEach((tk) => scheduleMap.set(tk.id, tk));
  const schedule = [...scheduleMap.values()];
  const scheduleDone = schedule.filter((tk) => tk.status === 'DONE').length;
  const nextTaskId = schedule.find((tk) => tk.status === 'TODO' && !isOverdue(tk))?.id;

  // 近日締切: 期限が今日以降の未完了タスクを期限昇順で上位表示
  const upcomingTasks = (allTasks ?? [])
    .filter((tk) => tk.due_date && tk.status !== 'DONE' && tk.status !== 'CANCELLED' && !isOverdue(tk))
    .sort((a, b) => (a.due_date ?? '').localeCompare(b.due_date ?? ''))
    .slice(0, 3);

  const total = kpi?.total_tasks ?? 0;
  const done = total - (kpi?.incomplete_tasks ?? 0);
  const donePct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 2, mb: '16px', flexWrap: 'wrap' }}>
        <Box sx={{ fontSize: 18, fontWeight: 700, color: ds.text }}>{t('dashboard.greeting')}</Box>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{todayLabel}</Box>
      </Box>

      <Box sx={{ display: 'flex', gap: '20px', alignItems: 'flex-start', flexWrap: { xs: 'wrap', lg: 'nowrap' } }}>
        {/* 左カラム */}
        <Box sx={{ flex: '1 1 600px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* いま取り組んでいるタスク */}
          <Box sx={{ ...card, border: `1px solid ${ds.primaryPaleBorder}`, overflow: 'hidden' }}>
            <Box sx={{
              bgcolor: ds.primary, color: '#fff', px: '18px', py: '10px',
              display: 'flex', alignItems: 'center', gap: '10px', fontSize: 14, fontWeight: 700,
            }}>
              <Box sx={{
                width: 14, height: 14, borderRadius: '50%', border: '3px solid rgba(255,255,255,.45)',
                bgcolor: '#fff', backgroundClip: 'content-box', p: '2px', boxSizing: 'border-box',
              }} />
              {t('dashboard.focusTitle')}
              {focusTasks.length > 1 && (
                <Box sx={{
                  ml: 'auto', px: '9px', py: '1px', borderRadius: '10px', fontSize: 12, fontWeight: 700,
                  bgcolor: 'rgba(255,255,255,.22)',
                }}>
                  {focusTasks.length}
                </Box>
              )}
            </Box>
            {focusTasks.length > 0 ? (
              focusTasks.map((task, i) => (
                <Box key={task.id} sx={{ borderTop: i === 0 ? 'none' : `1px solid ${ds.borderPale}` }}>
                  <FocusTask
                    task={task}
                    categories={categories}
                    onComplete={(tk) => complete.mutate(tk)}
                    onLogWork={(taskId, hours) => logWork.mutate({ taskId, hours })}
                    completePending={complete.isPending}
                    logPending={logWork.isPending}
                  />
                </Box>
              ))
            ) : (
              <Box sx={{ p: '18px', fontSize: 13, color: ds.textMuted }}>
                {t('dashboard.noFocus')}
              </Box>
            )}
          </Box>

          {/* 今日の予定 */}
          <Box sx={card}>
            <Box sx={{
              display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
              px: '18px', py: '14px', borderBottom: `1px solid ${ds.borderPale}`,
            }}>
              <Box sx={sectionTitle}>{t('dashboard.schedule')}</Box>
              <Box sx={{ fontSize: 12, color: ds.textSub }}>
                {t('dashboard.scheduleStats', { count: schedule.length, done: scheduleDone, left: schedule.length - scheduleDone })}
              </Box>
            </Box>
            {schedule.length === 0 && (
              <Box sx={{ px: '18px', py: '20px', fontSize: 13, color: ds.textMuted }}>{t('dashboard.noSchedule')}</Box>
            )}
            {schedule.map((tk) => {
              const st = displayStatus(tk);
              const isDoing = st === 'DOING';
              const isDone = st === 'DONE';
              const stDot = st === 'DONE' ? ds.success : st === 'DOING' ? ds.primary : st === 'LATE' ? ds.danger : ds.todoGray;
              return (
                <Box
                  key={tk.id}
                  onClick={() => navigate(`/tasks/${tk.id}`)}
                  sx={{
                    display: 'flex', alignItems: 'center', gap: '12px', px: '18px', py: '12px',
                    cursor: 'pointer',
                    borderBottom: `1px solid ${ds.hairline}`,
                    '&:last-child': { borderBottom: 'none' },
                    bgcolor: isDoing ? ds.rowHighlight : 'transparent',
                    boxShadow: isDoing ? `inset 3px 0 ${ds.primary}` : 'none',
                    '&:hover': { bgcolor: isDoing ? ds.rowHighlight : '#FAFAFA' },
                  }}
                >
                  <Box sx={{ width: 40, fontSize: 12, color: ds.textMuted, flexShrink: 0, whiteSpace: 'nowrap' }}>
                    {formatShortDate(tk.due_date)}
                  </Box>
                  <Box sx={{
                    width: 10, height: 10, borderRadius: '50%', bgcolor: stDot, flexShrink: 0,
                    boxShadow: isDoing ? `0 0 0 3px ${ds.primaryPale}` : 'none',
                  }} />
                  <CategoryDot categoryId={tk.category_id} categories={categories} size={7} />
                  <Box sx={{
                    flex: 1, minWidth: 0, fontSize: 14, color: isDone ? ds.textMuted : ds.text,
                    fontWeight: isDoing ? 700 : 500,
                    textDecoration: isDone ? 'line-through' : 'none',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {tk.title}
                  </Box>
                  {tk.id === nextTaskId && (
                    <Box sx={{
                      px: '10px', py: '2px', borderRadius: '10px', fontSize: 11, fontWeight: 700,
                      bgcolor: ds.primaryPale, color: ds.primary, whiteSpace: 'nowrap',
                    }}>
                      {t('dashboard.nextUp')}
                    </Box>
                  )}
                  <StatusChip task={tk} />
                </Box>
              );
            })}
          </Box>
        </Box>

        {/* 右カラム */}
        <Box sx={{ flex: '1 1 320px', minWidth: 280, display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* 遅延アラート */}
          {overdue.length > 0 && (
            <Box sx={{ bgcolor: ds.dangerPale, border: `1px solid ${ds.dangerPaleBorder}`, borderRadius: '10px', p: '16px' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px', color: ds.dangerText, fontSize: 14, fontWeight: 700, mb: '10px' }}>
                <WarningTriangleIcon size={20} stroke={ds.danger} />
                {t('dashboard.overdueAlert', { count: overdue.length })}
              </Box>
              {overdue.slice(0, 3).map((tk) => (
                <Box
                  key={tk.id}
                  onClick={() => navigate(`/tasks/${tk.id}`)}
                  sx={{
                    display: 'flex', alignItems: 'center', gap: '8px', bgcolor: ds.paper,
                    borderRadius: '10px', px: '12px', py: '8px', mb: '6px', cursor: 'pointer',
                    '&:last-child': { mb: 0 }, '&:hover': { bgcolor: '#FFF7F7' },
                  }}
                >
                  <CategoryDot categoryId={tk.category_id} categories={categories} size={7} />
                  <Box sx={{ flex: 1, minWidth: 0, fontSize: 13, color: ds.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {tk.title}
                  </Box>
                  <Box sx={{ fontSize: 12, fontWeight: 700, color: ds.dangerText, whiteSpace: 'nowrap' }}>
                    {t('common.overdueDays', { days: overdueDays(tk) })}
                  </Box>
                </Box>
              ))}
            </Box>
          )}

          {/* 近日締切 */}
          <Box sx={card}>
            <Box sx={{ px: '18px', py: '14px', borderBottom: `1px solid ${ds.borderPale}`, ...sectionTitle }}>{t('dashboard.upcoming')}</Box>
            {upcomingTasks.length === 0 && (
              <Box sx={{ px: '18px', py: '16px', fontSize: 13, color: ds.textMuted }}>{t('dashboard.noUpcoming')}</Box>
            )}
            {upcomingTasks.map((tk) => {
              const md = formatMonthDay(tk.due_date, lang);
              return (
                <Box
                  key={tk.id}
                  onClick={() => navigate(`/tasks/${tk.id}`)}
                  sx={{
                    display: 'flex', alignItems: 'center', gap: '12px', px: '18px', py: '12px', cursor: 'pointer',
                    borderBottom: `1px solid ${ds.hairline}`, '&:last-child': { borderBottom: 'none' },
                    '&:hover': { bgcolor: '#FAFAFA' },
                  }}
                >
                  <Box sx={{ width: 34, flexShrink: 0, textAlign: 'center' }}>
                    <Box sx={{ fontSize: 10, color: ds.textMuted, lineHeight: 1.2 }}>{md.month}</Box>
                    <Box sx={{ fontSize: 18, fontWeight: 700, color: ds.text, lineHeight: 1.2 }}>{md.day}</Box>
                  </Box>
                  <Box sx={{ flex: 1, minWidth: 0, fontSize: 13, color: ds.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {tk.title}
                  </Box>
                  <PriorityChip priority={tk.priority} />
                </Box>
              );
            })}
          </Box>

          {/* 全体の進捗 */}
          <Box sx={{ ...card, p: '18px' }}>
            <Box sx={{ ...sectionTitle, mb: '14px' }}>{t('dashboard.overall')}</Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
              <Box sx={{
                width: 96, height: 96, borderRadius: '50%', flexShrink: 0,
                background: `conic-gradient(${ds.success} ${donePct}%, ${ds.track} 0)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Box sx={{
                  width: 68, height: 68, borderRadius: '50%', bgcolor: ds.paper,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 20, fontWeight: 700, color: ds.text,
                }}>
                  {donePct}%
                </Box>
              </Box>
              <Box sx={{ fontSize: 13, color: ds.textSub, lineHeight: 2 }}>
                <Box>{t('dashboard.completedOfTotal', { done, total })}</Box>
                <Box>
                  {t('dashboard.thisWeekDone')}{' '}
                  <Box component="span" sx={{ fontWeight: 700, color: ds.primary }}>{kpi?.this_week_completed ?? 0}</Box>
                </Box>
                <Box>
                  {t('dashboard.overdueCount')}{' '}
                  <Box component="span" sx={{ fontWeight: 700, color: (kpi?.overdue_tasks ?? 0) > 0 ? ds.dangerText : ds.text }}>{kpi?.overdue_tasks ?? 0}</Box>
                </Box>
              </Box>
            </Box>
          </Box>
        </Box>
      </Box>
    </Box>
  );
};

export default Dashboard;
