import React, { useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, CircularProgress, Alert } from '@mui/material';
import { getTasks, completeTask, reopenTask, updateTask } from '../api/tasks';
import { getScopedMilestones } from '../api/milestones';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { showsOnGantt } from '../forecast/forecastView';
import { getCategories } from '../api/categories';
import type { Task } from '../types';
import { ds } from '../theme';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import GanttChart from '../components/GanttChart';
import { ACTUAL_DAY_COLOR } from '../actuals/actualsView';
import { ACTUALS_KEY, getGanttActuals } from '../api/actuals';
import { scopeParams } from '../projects/projectScope';
import { useProjectScope } from '../projects/useProjectScope';

const legend: { labelKey: TranslationKey; color: string }[] = [
  { labelKey: 'status.TODO', color: ds.todoGray },
  { labelKey: 'status.DOING', color: ds.primary },
  { labelKey: 'status.DONE', color: ds.success },
  { labelKey: 'status.LATE', color: ds.danger },
];

const GanttPage: React.FC = () => {
  const qc = useQueryClient();
  const { t } = useI18n();
  // サイドバーで選んだプロジェクト（と子孫）だけ（task #187、ADR-0024）
  const { scope } = useProjectScope();
  const { data, isLoading, error } = useQuery({
    queryKey: ['tasks', 'scope', scope],
    queryFn: () => getTasks(scopeParams(scope)),
  });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  // マイルストーンの期限と見込みの日（ADR-0058）。取れなくてもタスクは出す
  const { data: milestones } = useQuery({
    queryKey: ['milestones', 'scope', scope],
    queryFn: () => getScopedMilestones(scopeParams(scope)),
  });
  // 実績の帯（確定した実績。task #162）。取れなくても計画の帯は出す
  const { data: actualSpans } = useQuery({ queryKey: [...ACTUALS_KEY, 'gantt'], queryFn: () => getGanttActuals() });
  const actuals = useMemo(() => new Map((actualSpans ?? []).map((s) => [s.task_id, s])), [actualSpans]);

  const toggleDone = useMutation({
    mutationFn: (task: Task) => (task.status === 'DONE' ? reopenTask(task) : completeTask(task)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['today'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      qc.invalidateQueries({ queryKey: ['milestones'] });
    },
  });

  // 残をその場で直す。見込みは読み直したときに計算し直される（ADR-0058 決定 4）
  const editRemaining = useMutation({
    mutationFn: ({ task, hours }: { task: Task; hours: number | null }) => updateTask(task.id, { remaining_hours: hours }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['milestones'] });
      qc.invalidateQueries({ queryKey: ['today'] });
    },
  });

  const tasks = useMemo(
    () => (data ?? [])
      // 計画の日付が無くても、終わる見込みがあれば出す
      .filter(showsOnGantt)
      .sort((a, b) => (a.start_date ?? a.due_date ?? '').localeCompare(b.start_date ?? b.due_date ?? '')),
    [data],
  );

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">{t('common.loadError')}</Alert>;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: '12px', mb: '14px', flexWrap: 'wrap' }}>
        <Box sx={{ fontSize: 16, fontWeight: 700, color: ds.text }}>{t('gantt.schedule')}</Box>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('gantt.totalTasks', { count: tasks.length })}</Box>
        <Box sx={{ flex: 1 }} />
        <Box sx={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
          {legend.map((l) => (
            <Box key={l.labelKey} sx={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 12, color: ds.textSub }}>
              <Box sx={{ width: 12, height: 12, borderRadius: '3px', bgcolor: l.color }} />
              {t(l.labelKey)}
            </Box>
          ))}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 12, color: ds.textSub }}>
            <Box sx={{ width: 12, height: 6, borderRadius: '3px', bgcolor: ACTUAL_DAY_COLOR }} />
            {t('gantt.legendActual')}
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 12, color: ds.textSub }}>
            <Box sx={{ width: 16, height: 8, borderRadius: '3px', border: `1.5px dashed ${ds.primary}`, bgcolor: ds.primaryPale }} />
            {t('gantt.legendForecast')}
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: 12, color: ds.dangerText }}>
            <WarningAmberIcon sx={{ fontSize: 16 }} aria-hidden />
            {t('gantt.legendOverdue')}
          </Box>
        </Box>
      </Box>

      {tasks.length === 0 ? (
        <Box sx={{
          bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px',
          p: '40px', textAlign: 'center', fontSize: 13, color: ds.textMuted,
        }}>
          {t('gantt.empty')}
        </Box>
      ) : (
        <>
          {editRemaining.isError && <Alert severity="error" sx={{ mb: '10px' }}>{t('gantt.remainingError')}</Alert>}
          <GanttChart
            tasks={tasks} categories={categories} actuals={actuals} milestones={milestones}
            onToggleDone={(t) => toggleDone.mutate(t)}
            onEditRemaining={(task, hours) => editRemaining.mutate({ task, hours })}
          />
        </>
      )}
    </Box>
  );
};

export default GanttPage;
