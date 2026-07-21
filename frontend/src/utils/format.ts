import type { Task, TaskStatus } from '../types';

// ユーザー設定のタイムゾーン。「今日」の判定に使う（未設定時はブラウザのローカル）。
// I18nProvider が設定読み込み時に反映する。
let activeTimeZone: string | null = null;

export const setActiveTimeZone = (tz: string | null): void => {
  activeTimeZone = tz;
};

// 設定タイムゾーンでの「今日」を、ローカル日付（時刻0時）として返す
export const todayDate = (): Date => {
  const now = new Date();
  if (activeTimeZone) {
    try {
      // en-CA ロケールは YYYY-MM-DD 形式を返す
      const ymd = new Intl.DateTimeFormat('en-CA', { timeZone: activeTimeZone }).format(now);
      const [y, m, d] = ymd.split('-').map(Number);
      return new Date(y, m - 1, d);
    } catch {
      // 不正なタイムゾーンはローカルにフォールバック
    }
  }
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
};

// APIの日付文字列をローカル日付として解釈する。
// `YYYY-MM-DD` を new Date() に渡すと UTC 深夜扱いになり、UTCより西のタイムゾーンで前日にずれるため、
// 日付のみの文字列は明示的にローカルの年月日で構築する。
export const parseDate = (dateStr: string | null | undefined): Date | null => {
  if (!dateStr) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(dateStr);
  return isNaN(d.getTime()) ? null : d;
};

export const formatDate = (dateStr: string | null | undefined): string => {
  const d = parseDate(dateStr);
  if (!d) return '—';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}/${m}/${day}`;
};

export const formatShortDate = (dateStr: string | null | undefined): string => {
  const d = parseDate(dateStr);
  if (!d) return '—';
  return `${d.getMonth() + 1}/${d.getDate()}`;
};

export const formatMonthDay = (dateStr: string | null | undefined, lang: 'ja' | 'en' = 'ja'): { month: string; day: string } => {
  const d = parseDate(dateStr);
  if (!d) return { month: '', day: '—' };
  const month = lang === 'ja'
    ? `${d.getMonth() + 1}月`
    : d.toLocaleString('en-US', { month: 'short' });
  return { month, day: String(d.getDate()) };
};

export type PriorityBand = 'high' | 'mid' | 'low';

// priority 1〜5 を 高/中/低 の3段階に丸める
export const priorityBand = (p: number): PriorityBand => (p >= 4 ? 'high' : p === 3 ? 'mid' : 'low');

// 高/中/低 選択時に保存する priority 値
export const priorityBandValue: Record<PriorityBand, number> = { high: 5, mid: 3, low: 1 };

const dateOnly = (d: Date): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export const isOverdue = (task: Pick<Task, 'due_date' | 'status'>): boolean => {
  if (task.status === 'DONE' || task.status === 'CANCELLED') return false;
  const due = parseDate(task.due_date);
  if (!due) return false;
  return dateOnly(due) < todayDate();
};

export const isDueToday = (task: Pick<Task, 'due_date'>): boolean => {
  const due = parseDate(task.due_date);
  if (!due) return false;
  return dateOnly(due).getTime() === todayDate().getTime();
};

// 表示用ステータス（遅延を含む）
export type DisplayStatus = TaskStatus | 'LATE';

export const displayStatus = (task: Pick<Task, 'due_date' | 'status'>): DisplayStatus =>
  isOverdue(task) ? 'LATE' : task.status;

export const overdueDays = (task: Pick<Task, 'due_date'>): number => {
  const parsed = parseDate(task.due_date);
  if (!parsed) return 0;
  const due = dateOnly(parsed);
  const today = todayDate();
  return Math.max(0, Math.round((today.getTime() - due.getTime()) / 86400000));
};

export const getCurrentWeek = (): string => {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const dayOfYear = Math.floor((now.getTime() - new Date(now.getFullYear(), 0, 0).getTime()) / 86400000);
  const weekNum = Math.ceil((dayOfYear + jan4.getDay()) / 7);
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
};
