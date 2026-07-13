export const formatDate = (dateStr: string | null | undefined): string => {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '—';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}/${m}/${day}`;
};

export const statusLabel: Record<string, string> = {
  TODO: '未着手',
  DOING: '進行中',
  WAITING: '待機中',
  DONE: '完了',
  CANCELLED: 'キャンセル',
};

export const statusColor: Record<string, 'default' | 'primary' | 'warning' | 'success' | 'error'> = {
  TODO: 'default',
  DOING: 'primary',
  WAITING: 'warning',
  DONE: 'success',
  CANCELLED: 'error',
};

export const priorityLabel = (p: number): string => '★'.repeat(p) + '☆'.repeat(5 - p);

export const getCurrentWeek = (): string => {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const dayOfYear = Math.floor((now.getTime() - new Date(now.getFullYear(), 0, 0).getTime()) / 86400000);
  const weekNum = Math.ceil((dayOfYear + jan4.getDay()) / 7);
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
};
