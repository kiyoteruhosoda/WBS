import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Typography, CircularProgress, Alert } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { Gantt, ViewMode } from 'gantt-task-react';
import type { Task as GanttLibTask } from 'gantt-task-react';
import 'gantt-task-react/dist/index.css';
import { getGantt } from '../api/dashboard';
import type { GanttTask } from '../types';

const toGanttTask = (t: GanttTask): GanttLibTask | null => {
  if (!t.start_date || !t.due_date) return null;
  const start = new Date(t.start_date);
  const end = new Date(t.due_date);
  if (isNaN(start.getTime()) || isNaN(end.getTime())) return null;
  if (end <= start) end.setDate(start.getDate() + 1);
  return {
    id: String(t.id),
    name: t.title,
    start,
    end,
    progress: t.progress_percent,
    type: 'task',
    project: t.parent_task_id ? String(t.parent_task_id) : undefined,
    dependencies: t.dependencies.map(String),
  };
};

const GanttPage: React.FC = () => {
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({ queryKey: ['gantt'], queryFn: getGantt });

  const ganttTasks = useMemo<GanttLibTask[]>(() => {
    if (!data) return [];
    return data.map(toGanttTask).filter((t): t is GanttLibTask => t !== null);
  }, [data]);

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">読み込みエラー</Alert>;

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>ガントチャート</Typography>
      {ganttTasks.length === 0
        ? <Alert severity="info">表示できるタスクがありません（開始日・期日が設定されたタスクが必要です）</Alert>
        : (
          <Box sx={{ overflowX: 'auto' }}>
            <Gantt
              tasks={ganttTasks}
              viewMode={ViewMode.Day}
              onDoubleClick={(t) => navigate(`/tasks/${t.id}`)}
              listCellWidth="155px"
              columnWidth={60}
            />
          </Box>
        )
      }
    </Box>
  );
};

export default GanttPage;
