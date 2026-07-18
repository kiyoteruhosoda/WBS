import type { Task, TaskStatus } from '../types';

export const formatDate = (dateStr: string | null | undefined): string => {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '—';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}/${m}/${day}`;
};

export const formatShortDate = (dateStr: string | null | undefined): string => {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '—';
  return `${d.getMonth() + 1}/${d.getDate()}`;
};

export const formatMonthDay = (dateStr: string | null | undefined): { month: string; day: string } => {
  if (!dateStr) return { month: '', day: '—' };
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return { month: '', day: '—' };
  return { month: `${d.getMonth() + 1}月`, day: String(d.getDate()) };
};

export const statusLabel: Record<string, string> = {
  TODO: '未着手',
  DOING: '進行中',
  WAITING: '待機中',
  DONE: '完了',
  CANCELLED: '中止',
};

export type PriorityBand = 'high' | 'mid' | 'low';

// priority 1〜5 を 高/中/低 の3段階に丸める
export const priorityBand = (p: number): PriorityBand => (p >= 4 ? 'high' : p === 3 ? 'mid' : 'low');

export const priorityBandLabel: Record<PriorityBand, string> = { high: '高', mid: '中', low: '低' };

// 高/中/低 選択時に保存する priority 値
export const priorityBandValue: Record<PriorityBand, number> = { high: 5, mid: 3, low: 1 };

const dateOnly = (d: Date): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export const isOverdue = (task: Pick<Task, 'due_date' | 'status'>): boolean => {
  if (!task.due_date || task.status === 'DONE' || task.status === 'CANCELLED') return false;
  const due = new Date(task.due_date);
  if (isNaN(due.getTime())) return false;
  return dateOnly(due) < dateOnly(new Date());
};

export const isDueToday = (task: Pick<Task, 'due_date'>): boolean => {
  if (!task.due_date) return false;
  const due = new Date(task.due_date);
  if (isNaN(due.getTime())) return false;
  return dateOnly(due).getTime() === dateOnly(new Date()).getTime();
};

// 表示用ステータス（遅延を含む）
export type DisplayStatus = TaskStatus | 'LATE';

export const displayStatus = (task: Pick<Task, 'due_date' | 'status'>): DisplayStatus =>
  isOverdue(task) ? 'LATE' : task.status;

export const overdueDays = (task: Pick<Task, 'due_date'>): number => {
  if (!task.due_date) return 0;
  const due = dateOnly(new Date(task.due_date));
  const today = dateOnly(new Date());
  return Math.max(0, Math.round((today.getTime() - due.getTime()) / 86400000));
};

export const getCurrentWeek = (): string => {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const dayOfYear = Math.floor((now.getTime() - new Date(now.getFullYear(), 0, 0).getTime()) / 86400000);
  const weekNum = Math.ceil((dayOfYear + jan4.getDay()) / 7);
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
};
