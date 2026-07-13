import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Card, CardContent, Grid, Typography, CircularProgress, Alert, Divider } from '@mui/material';
import { getDashboardToday, getDashboardKpi } from '../api/dashboard';
import TaskCard from '../components/TaskCard';
import type { Task } from '../types';

const bucketLabels: Record<string, string> = {
  OVERDUE: '期限超過',
  TODAY: '今日',
  TOMORROW: '明日',
  DOING: '進行中',
  STARTED: '開始済み',
};

const KpiCard: React.FC<{ label: string; value: number | string }> = ({ label, value }) => (
  <Card>
    <CardContent>
      <Typography variant="h4" sx={{ fontWeight: 'bold' }}>{value}</Typography>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
    </CardContent>
  </Card>
);

const Dashboard: React.FC = () => {
  const { data: kpi, isLoading: kpiLoading, error: kpiError } = useQuery({ queryKey: ['kpi'], queryFn: getDashboardKpi });
  const { data: today, isLoading: todayLoading, error: todayError } = useQuery({ queryKey: ['dashboard-today'], queryFn: getDashboardToday });

  if (kpiLoading || todayLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress /></Box>;
  if (kpiError || todayError) return <Alert severity="error">データの読み込みに失敗しました</Alert>;

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>ダッシュボード</Typography>
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}><KpiCard label="総タスク数" value={kpi?.total_tasks ?? 0} /></Grid>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}><KpiCard label="未完了" value={kpi?.incomplete_tasks ?? 0} /></Grid>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}><KpiCard label="期限超過" value={kpi?.overdue_tasks ?? 0} /></Grid>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}><KpiCard label="今週完了" value={kpi?.this_week_completed ?? 0} /></Grid>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}><KpiCard label="今週時間" value={`${kpi?.this_week_hours ?? 0}h`} /></Grid>
      </Grid>
      <Divider sx={{ mb: 2 }} />
      <Grid container spacing={2}>
        {today && Object.entries(today.buckets).map(([bucket, tasks]) => (
          <Grid size={{ xs: 12, md: 6 }} key={bucket}>
            <Typography variant="h6" sx={{ mb: 1 }}>{bucketLabels[bucket] ?? bucket} ({(tasks as Task[]).length})</Typography>
            {(tasks as Task[]).map(t => <TaskCard key={t.id} task={t} />)}
            {(tasks as Task[]).length === 0 && <Typography variant="body2" color="text.secondary">なし</Typography>}
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

export default Dashboard;
