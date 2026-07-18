import React, { useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, CircularProgress, Alert } from '@mui/material';
import { getTasks, completeTask, reopenTask } from '../api/tasks';
import { getCategories } from '../api/categories';
import type { Task } from '../types';
import { ds } from '../theme';
import GanttChart from '../components/GanttChart';

const legend = [
  { label: '未着手', color: ds.todoGray },
  { label: '進行中', color: ds.primary },
  { label: '完了', color: ds.success },
  { label: '遅延', color: ds.danger },
];

const GanttPage: React.FC = () => {
  const qc = useQueryClient();
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
  if (error) return <Alert severity="error">データの読み込みに失敗しました</Alert>;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: '12px', mb: '14px', flexWrap: 'wrap' }}>
        <Box sx={{ fontSize: 16, fontWeight: 700, color: ds.text }}>スケジュール</Box>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>全{tasks.length}タスク</Box>
        <Box sx={{ flex: 1 }} />
        <Box sx={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
          {legend.map((l) => (
            <Box key={l.label} sx={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 12, color: ds.textSub }}>
              <Box sx={{ width: 12, height: 12, borderRadius: '3px', bgcolor: l.color }} />
              {l.label}
            </Box>
          ))}
        </Box>
      </Box>

      {tasks.length === 0 ? (
        <Box sx={{
          bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px',
          p: '40px', textAlign: 'center', fontSize: 13, color: ds.textMuted,
        }}>
          表示できるタスクがありません（開始日または期日が設定されたタスクが必要です）
        </Box>
      ) : (
        <GanttChart tasks={tasks} categories={categories} onToggleDone={(t) => toggleDone.mutate(t)} />
      )}
    </Box>
  );
};

export default GanttPage;
