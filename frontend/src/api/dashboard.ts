import client from './client';
import type { DashboardKpi, GanttTask } from '../types';

export const getDashboardKpi = async (): Promise<DashboardKpi> => {
  const { data } = await client.get('/dashboard/kpi');
  return data;
};

export const getGantt = async (): Promise<GanttTask[]> => {
  const { data } = await client.get('/gantt');
  return data;
};
