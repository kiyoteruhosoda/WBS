import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, Typography, CircularProgress, Alert, Card, CardContent, Grid } from '@mui/material';
import { getDashboardToday } from '../api/dashboard';
import { patchTask } from '../api/tasks';
import type { Task, TaskStatus } from '../types';
import { formatDate, priorityLabel } from '../utils/format';
import StatusChip from '../components/StatusChip';
import { useNavigate } from 'react-router-dom';

const bucketLabels: Record<string, string> = {
  OVERDUE: '期限超過',
  TODAY: '今日',
  TOMORROW: '明日',
  DOING: '進行中',
  STARTED: '開始済み',
};

const toggleStatus = (s: TaskStatus): TaskStatus => s === 'DOING' ? 'DONE' : 'DOING';

const Today: React.FC = () => {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data: today, isLoading, error } = useQuery({ queryKey: ['dashboard-today'], queryFn: getDashboardToday });
  const patch = useMutation({
    mutationFn: ({ id, status }: { id: number; status: TaskStatus }) => patchTask(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard-today'] }),
  });

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">データの読み込みに失敗しました</Alert>;

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>今日のタスク</Typography>
      {today && Object.entries(today.buckets).map(([bucket, tasks]) => (
        <Box key={bucket} sx={{ mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>{bucketLabels[bucket] ?? bucket} ({(tasks as Task[]).length})</Typography>
          <Grid container spacing={1}>
            {(tasks as Task[]).map(t => (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={t.id}>
                <Card variant="outlined">
                  <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
                    <Typography variant="body2" sx={{ fontWeight: 'bold', cursor: 'pointer' }} onClick={() => navigate(`/tasks/${t.id}`)}>{t.title}</Typography>
                    <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
                      <Box sx={{ cursor: 'pointer' }} onClick={() => patch.mutate({ id: t.id, status: toggleStatus(t.status) })}>
                        <StatusChip status={t.status} />
                      </Box>
                      <Typography variant="caption">{formatDate(t.due_date)}</Typography>
                      <Typography variant="caption" color="warning.main">{priorityLabel(t.priority)}</Typography>
                      <Typography variant="caption">緊急度: {t.urgency}</Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
            {(tasks as Task[]).length === 0 && <Grid size={12}><Typography variant="body2" color="text.secondary">なし</Typography></Grid>}
          </Grid>
        </Box>
      ))}
    </Box>
  );
};

export default Today;
