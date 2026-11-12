import type { Task, TaskStatus } from '../types';

// User-configured time zone. Used to decide "today" (browser local when unset).
// I18nProvider applies it when settings are loaded.
let activeTimeZone: string | null = null;

export const setActiveTimeZone = (tz: string | null): void => {
  activeTimeZone = tz;
};

// Returns "today" in the configured time zone as a local date (at midnight)
export const todayDate = (): Date => {
  const now = new Date();
  if (activeTimeZone) {
    try {
      // The en-CA locale returns YYYY-MM-DD
      const ymd = new Intl.DateTimeFormat('en-CA', { timeZone: activeTimeZone }).format(now);
      const [y, m, d] = ymd.split('-').map(Number);
      return new Date(y, m - 1, d);
    } catch {
      // Fall back to local for an invalid time zone
    }
  }
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
};

// Parse an API date string as a local date.
// Passing `YYYY-MM-DD` to new Date() treats it as UTC midnight, which shifts to the previous day in time zones west of UTC,
// so date-only strings are built explicitly from local year/month/day.
export const parseDate = (dateStr: string | null | undefined): Date | null => {
  if (!dateStr) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(dateStr);
  return isNaN(d.getTime()) ? null : d;
};

// ── Date format (ADR-0020) ─────────────────────────────────────────
// Dates in text and tables are `M/D` (no zero padding). If not this year (the year of "today" in the user's time zone),
// `YYYY/M/D`. Ranges are `M/D〜M/D`; the year goes on the start only when it is not this year, and on the end only when it differs from the start's year.
// Exceptions (not routed through here): calendar headings (ported format), closing screen headings (always show the year), and the Gantt day axis.

type DateInput = string | Date | null | undefined;

const toDate = (value: DateInput): Date | null => (value instanceof Date ? value : parseDate(value));

const monthDay = (d: Date): string => `${d.getMonth() + 1}/${d.getDate()}`;

/** A single date. `9/30` this year, `2025/9/30` otherwise. "—" when missing. */
export const formatDate = (value: DateInput): string => {
  const d = toDate(value);
  if (!d) return '—';
  return d.getFullYear() === todayDate().getFullYear() ? monthDay(d) : `${d.getFullYear()}/${monthDay(d)}`;
};

/**
 * Both ends of a range. The arrangement (`{from}〜{to}`) is up to the translations (`common.dateRange` etc.).
 * The start is as `formatDate`. The end omits the year when it equals the start's (`2025/12/16〜12/31`, `2025/12/16〜2026/1/15`).
 */
export const dateRangeParts = (from: DateInput, to: DateInput): { from: string; to: string } => {
  const a = toDate(from);
  const b = toDate(to);
  if (!b) return { from: formatDate(a), to: '—' };
  const sameYear = a ? a.getFullYear() === b.getFullYear() : b.getFullYear() === todayDate().getFullYear();
  return { from: formatDate(a), to: sameYear ? monthDay(b) : `${b.getFullYear()}/${monthDay(b)}` };
};

// ── Duration format (ADR-0020) ─────────────────────────────────────────
// Effort (estimate, planned, remaining, actual totals, confirmed actuals, differences) is decimal hours `1.5h` (up to 2 decimals, trailing zeros dropped).
// Amounts on screens where time entries are reviewed (today, closing, timer) are read next to clock times, so `H:MM` (`H:MM:SS` for running elapsed time and exact lengths).
// The 15-minute rounding in the closing table (`formatQuarterHours`) also uses `H:MM`.

/** Effort hours (`1.5h`). null → "—". */
export const formatHours = (hours: number | null | undefined): string =>
  hours == null ? '—' : `${Number(hours.toFixed(2))}h`;

/** Effort given in seconds as `1.5h`. */
export const formatSecondsAsHours = (seconds: number): string => formatHours(seconds / 3600);

/** Difference (tracked − planned). Prefixed with "+" when positive. */
export const formatSignedSecondsAsHours = (seconds: number): string => {
  if (seconds === 0) return '±0h';
  return `${seconds > 0 ? '+' : '−'}${formatSecondsAsHours(Math.abs(seconds))}`;
};

/** Time entry length as `H:MM` (seconds truncated). */
export const formatClockDuration = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds / 60));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};

/** Exact time entry length or running elapsed time as `H:MM:SS` (fractional seconds truncated, negative → 0). */
export const formatExactDuration = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

export type PriorityBand = 'high' | 'mid' | 'low';

// Map priority 1–5 to three bands: high/mid/low
export const priorityBand = (p: number): PriorityBand => (p >= 4 ? 'high' : p === 3 ? 'mid' : 'low');

// priority value saved when high/mid/low is chosen
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

// Display status (including late)
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
