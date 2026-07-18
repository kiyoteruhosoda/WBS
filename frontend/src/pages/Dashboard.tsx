import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, Button, CircularProgress, Alert, TextField } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { getDashboardToday, getDashboardKpi } from '../api/dashboard';
import { getTasks, patchTask } from '../api/tasks';
import { createWorklog } from '../api/worklogs';
import { getCategories } from '../api/categories';
import type { Task } from '../types';
import { formatDate, formatShortDate, formatMonthDay, isDueToday, isOverdue, overdueDays, displayStatus } from '../utils/format';
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

const todayLabel = (): string => {
  const d = new Date();
  const youbi = ['日', '月', '火', '水', '木', '金', '土'][d.getDay()];
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日（${youbi}）`;
};

const dueLabel = (t: Task): { text: string; urgent: boolean } => {
  if (!t.due_date) return { text: '期限なし', urgent: false };
  if (isOverdue(t)) return { text: `${formatDate(t.due_date)}（${overdueDays(t)}日超過）`, urgent: true };
  if (isDueToday(t)) return { text: '今日', urgent: true };
  return { text: formatDate(t.due_date), urgent: false };
};

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [loggingWork, setLoggingWork] = useState(false);
  const [workHours, setWorkHours] = useState('');

  const { data: today, isLoading, error } = useQuery({ queryKey: ['dashboard-today'], queryFn: getDashboardToday });
  const { data: kpi } = useQuery({ queryKey: ['kpi'], queryFn: getDashboardKpi });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  const { data: allTasks } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['dashboard-today'] });
    qc.invalidateQueries({ queryKey: ['kpi'] });
    qc.invalidateQueries({ queryKey: ['tasks'] });
  };

  const patch = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<Task> }) => patchTask(id, payload),
    onSuccess: invalidate,
  });

  // 進捗は作業ログ（実績時間）から自動算出されるため、記録で更新する
  const logWork = useMutation({
    mutationFn: ({ taskId, hours }: { taskId: number; hours: number }) => {
      const d = new Date();
      const workDate = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      return createWorklog({ task_id: taskId, work_date: workDate, hours, memo: null });
    },
    onSuccess: invalidate,
  });

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">データの読み込みに失敗しました</Alert>;

  const buckets = today?.buckets;
  const doing = buckets?.DOING ?? [];
  const todayTasks = buckets?.TODAY ?? [];
  const overdue = buckets?.OVERDUE ?? [];

  const hero: Task | undefined = doing[0] ?? todayTasks[0];
  const heroDue = hero ? dueLabel(hero) : null;
  const catName = (t: Task) => categories?.find((c) => c.id === t.category_id)?.name ?? '未分類';

  // 今日の予定: 今日締切＋進行中＋遅延をまとめて表示
  const scheduleMap = new Map<number, Task>();
  [...overdue, ...todayTasks, ...doing].forEach((t) => scheduleMap.set(t.id, t));
  const schedule = [...scheduleMap.values()];
  const scheduleDone = schedule.filter((t) => t.status === 'DONE').length;
  const nextTaskId = schedule.find((t) => t.status === 'TODO' && !isOverdue(t))?.id;

  // 近日締切: 期限が今日以降の未完了タスクを期限昇順で上位表示
  const upcomingTasks = (allTasks ?? [])
    .filter((t) => t.due_date && t.status !== 'DONE' && t.status !== 'CANCELLED' && !isOverdue(t))
    .sort((a, b) => (a.due_date ?? '').localeCompare(b.due_date ?? ''))
    .slice(0, 3);

  const total = kpi?.total_tasks ?? 0;
  const done = total - (kpi?.incomplete_tasks ?? 0);
  const donePct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 2, mb: '16px', flexWrap: 'wrap' }}>
        <Box sx={{ fontSize: 18, fontWeight: 700, color: ds.text }}>こんにちは</Box>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{todayLabel()}</Box>
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
              いま取り組んでいるタスク
            </Box>
            {hero ? (
              <Box sx={{ p: '18px' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 13, color: ds.textSub }}>
                  <CategoryDot categoryId={hero.category_id} categories={categories} />
                  {catName(hero)}
                </Box>
                <Box
                  onClick={() => navigate(`/tasks/${hero.id}`)}
                  sx={{ fontSize: 22, fontWeight: 700, color: ds.text, mt: '4px', mb: '14px', cursor: 'pointer', '&:hover': { color: ds.primary } }}
                >
                  {hero.title}
                </Box>
                <Box sx={{ display: 'flex', gap: '40px', mb: '14px', flexWrap: 'wrap' }}>
                  <Box>
                    <Box sx={{ fontSize: 12, color: ds.textMuted, mb: '2px' }}>締切</Box>
                    <Box sx={{ fontSize: 15, fontWeight: 700, color: heroDue?.urgent ? ds.dangerText : ds.text }}>
                      {heroDue?.text}
                    </Box>
                  </Box>
                  <Box>
                    <Box sx={{ fontSize: 12, color: ds.textMuted, mb: '2px' }}>ステータス</Box>
                    <StatusChip task={hero} />
                  </Box>
                </Box>
                <ProgressBar value={hero.progress_percent} showLabel />
                <Box sx={{ display: 'flex', gap: '12px', mt: '16px', flexWrap: 'wrap' }}>
                  <Button
                    variant="contained"
                    sx={{ flex: '1 1 180px' }}
                    disabled={patch.isPending}
                    onClick={() => patch.mutate({ id: hero.id, payload: { status: 'DONE' } })}
                  >
                    完了にする
                  </Button>
                  <Button
                    variant="outlined"
                    sx={{ flex: '1 1 180px' }}
                    onClick={() => { setLoggingWork(!loggingWork); setWorkHours(''); }}
                  >
                    作業を記録
                  </Button>
                </Box>
                {loggingWork && (
                  <Box sx={{ display: 'flex', gap: '10px', mt: '12px', alignItems: 'center' }}>
                    <TextField
                      size="small" type="number" label="今日の作業時間（h）"
                      value={workHours}
                      onChange={(e) => setWorkHours(e.target.value)}
                      slotProps={{ htmlInput: { min: 0, step: 0.5 } }}
                      sx={{ width: 180 }}
                    />
                    <Button
                      variant="contained" size="small"
                      disabled={logWork.isPending || !workHours || Number(workHours) <= 0}
                      onClick={() => {
                        logWork.mutate({ taskId: hero.id, hours: Number(workHours) });
                        setLoggingWork(false);
                      }}
                    >
                      記録する
                    </Button>
                  </Box>
                )}
              </Box>
            ) : (
              <Box sx={{ p: '18px', fontSize: 13, color: ds.textMuted }}>
                進行中のタスクはありません。タスクを開始するとここに表示されます。
              </Box>
            )}
          </Box>

          {/* 今日の予定 */}
          <Box sx={card}>
            <Box sx={{
              display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
              px: '18px', py: '14px', borderBottom: `1px solid ${ds.borderPale}`,
            }}>
              <Box sx={sectionTitle}>今日の予定</Box>
              <Box sx={{ fontSize: 12, color: ds.textSub }}>
                {schedule.length}件 ・ 完了{scheduleDone} / 残り{schedule.length - scheduleDone}
              </Box>
            </Box>
            {schedule.length === 0 && (
              <Box sx={{ px: '18px', py: '20px', fontSize: 13, color: ds.textMuted }}>今日の予定はありません</Box>
            )}
            {schedule.map((t) => {
              const st = displayStatus(t);
              const isDoing = st === 'DOING';
              const isDone = st === 'DONE';
              const stDot = st === 'DONE' ? ds.success : st === 'DOING' ? ds.primary : st === 'LATE' ? ds.danger : ds.todoGray;
              return (
                <Box
                  key={t.id}
                  onClick={() => navigate(`/tasks/${t.id}`)}
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
                    {formatShortDate(t.due_date)}
                  </Box>
                  <Box sx={{
                    width: 10, height: 10, borderRadius: '50%', bgcolor: stDot, flexShrink: 0,
                    boxShadow: isDoing ? `0 0 0 3px ${ds.primaryPale}` : 'none',
                  }} />
                  <CategoryDot categoryId={t.category_id} categories={categories} size={7} />
                  <Box sx={{
                    flex: 1, minWidth: 0, fontSize: 14, color: isDone ? ds.textMuted : ds.text,
                    fontWeight: isDoing ? 700 : 500,
                    textDecoration: isDone ? 'line-through' : 'none',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {t.title}
                  </Box>
                  {t.id === nextTaskId && (
                    <Box sx={{
                      px: '10px', py: '2px', borderRadius: '10px', fontSize: 11, fontWeight: 700,
                      bgcolor: ds.primaryPale, color: ds.primary, whiteSpace: 'nowrap',
                    }}>
                      次はこれ
                    </Box>
                  )}
                  <StatusChip task={t} />
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
                遅延しています（{overdue.length}件）
              </Box>
              {overdue.slice(0, 3).map((t) => (
                <Box
                  key={t.id}
                  onClick={() => navigate(`/tasks/${t.id}`)}
                  sx={{
                    display: 'flex', alignItems: 'center', gap: '8px', bgcolor: ds.paper,
                    borderRadius: '10px', px: '12px', py: '8px', mb: '6px', cursor: 'pointer',
                    '&:last-child': { mb: 0 }, '&:hover': { bgcolor: '#FFF7F7' },
                  }}
                >
                  <CategoryDot categoryId={t.category_id} categories={categories} size={7} />
                  <Box sx={{ flex: 1, minWidth: 0, fontSize: 13, color: ds.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.title}
                  </Box>
                  <Box sx={{ fontSize: 12, fontWeight: 700, color: ds.dangerText, whiteSpace: 'nowrap' }}>
                    {overdueDays(t)}日超過
                  </Box>
                </Box>
              ))}
            </Box>
          )}

          {/* 近日締切 */}
          <Box sx={card}>
            <Box sx={{ px: '18px', py: '14px', borderBottom: `1px solid ${ds.borderPale}`, ...sectionTitle }}>近日締切</Box>
            {upcomingTasks.length === 0 && (
              <Box sx={{ px: '18px', py: '16px', fontSize: 13, color: ds.textMuted }}>近日締切のタスクはありません</Box>
            )}
            {upcomingTasks.map((t) => {
              const md = formatMonthDay(t.due_date);
              return (
                <Box
                  key={t.id}
                  onClick={() => navigate(`/tasks/${t.id}`)}
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
                    {t.title}
                  </Box>
                  <PriorityChip priority={t.priority} />
                </Box>
              );
            })}
          </Box>

          {/* 今週の進捗 */}
          <Box sx={{ ...card, p: '18px' }}>
            <Box sx={{ ...sectionTitle, mb: '14px' }}>全体の進捗</Box>
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
                <Box>完了 <Box component="span" sx={{ fontWeight: 700, color: ds.text }}>{done}</Box> / 全 {total} タスク</Box>
                <Box>今週完了 <Box component="span" sx={{ fontWeight: 700, color: ds.primary }}>{kpi?.this_week_completed ?? 0}</Box></Box>
                <Box>期限超過 <Box component="span" sx={{ fontWeight: 700, color: (kpi?.overdue_tasks ?? 0) > 0 ? ds.dangerText : ds.text }}>{kpi?.overdue_tasks ?? 0}</Box></Box>
              </Box>
            </Box>
          </Box>
        </Box>
      </Box>
    </Box>
  );
};

export default Dashboard;
