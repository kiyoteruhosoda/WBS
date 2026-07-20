import React, { useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, CircularProgress, Alert } from '@mui/material';
import { getTasks, completeTask, reopenTask } from '../api/tasks';
import { getCategories } from '../api/categories';
import type { Task } from '../types';
import { ds } from '../theme';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import GanttChart from '../components/GanttChart';

const legend: { labelKey: TranslationKey; color: string }[] = [
  { labelKey: 'status.TODO', color: ds.todoGray },
  { labelKey: 'status.DOING', color: ds.primary },
  { labelKey: 'status.DONE', color: ds.success },
  { labelKey: 'status.LATE', color: ds.danger },
];

const GanttPage: React.FC = () => {
  const qc = useQueryClient();
  const { t } = useI18n();
  const { data, isLoading, error } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });

  const toggleDone = useMutation({
    mutationFn: (task: Task) => (task.status === 'DONE' ? reopenTask(task) : completeTask(task)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['dashboard-today'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
    },
  });

  const tasks = useMemo(
    () => (data ?? [])
      .filter((t) => t.start_date || t.due_date)
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
        <GanttChart tasks={tasks} categories={categories} onToggleDone={(t) => toggleDone.mutate(t)} />
      )}
    </Box>
  );
};

export default GanttPage;
