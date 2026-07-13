import client from './client';
import type { DashboardToday, DashboardKpi, GanttTask, WeeklyReview } from '../types';

export const getDashboardToday = async (): Promise<DashboardToday> => {
  const { data } = await client.get('/dashboard/today');
  return data;
};

export const getDashboardKpi = async (): Promise<DashboardKpi> => {
  const { data } = await client.get('/dashboard/kpi');
  return data;
};

export const getGantt = async (): Promise<GanttTask[]> => {
  const { data } = await client.get('/gantt');
  return data;
};

export const getWeeklyReview = async (week: string): Promise<WeeklyReview> => {
  const { data } = await client.get('/reviews/weekly', { params: { week } });
  return data;
};
