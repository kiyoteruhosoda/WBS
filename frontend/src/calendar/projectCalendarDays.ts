// Look up whether a day is a working day and holiday names from the project calendar (ADR-0059, ADR-0060) (task #559; Gantt columns and working-day counts).
// Holds only UI-independent logic.
import type { TeamCalendar, WeekdayCode } from '../types';

/** Weekday codes in `Date.getDay()` order (Sunday = 0). */
export const WEEKDAYS_SUNDAY_FIRST: readonly WeekdayCode[] = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
const MON_TO_FRI: readonly WeekdayCode[] = ['MO', 'TU', 'WE', 'TH', 'FR'];

export interface ProjectDays {
  workdays: ReadonlySet<WeekdayCode>;
  /** Holidays (date → name; null when unnamed) */
  daysOff: ReadonlyMap<string, string | null>;
  /** Working days (work on non-working weekdays) */
  extraWorkdays: ReadonlyMap<string, string | null>;
}

/** When showing all or unassigned, or for tasks without a calendar: Mon–Fri, no holidays */
export const DEFAULT_PROJECT_DAYS: ProjectDays = {
  workdays: new Set(MON_TO_FRI), daysOff: new Map(), extraWorkdays: new Map(),
};

export const projectDaysOf = (calendar: TeamCalendar | undefined | null): ProjectDays => (calendar ? {
  workdays: new Set(calendar.workdays),
  daysOff: new Map(calendar.days_off.map((d) => [d.day, d.name])),
  extraWorkdays: new Map(calendar.extra_workdays.map((d) => [d.day, d.name])),
} : DEFAULT_PROJECT_DAYS);

const weekdayOf = (day: string): WeekdayCode => {
  const [y, m, d] = day.split('-').map(Number);
  return WEEKDAYS_SUNDAY_FIRST[new Date(y, m - 1, d).getDay()];
};

/** Whether the day is worked (working day > holiday > weekday; the server keeps holidays and working days from overlapping) */
export const worksOn = (days: ProjectDays, day: string): boolean => {
  if (days.extraWorkdays.has(day)) return true;
  if (days.daysOff.has(day)) return false;
  return days.workdays.has(weekdayOf(day));
};

const addDays = (day: string, n: number): string => {
  const [y, m, d] = day.split('-').map(Number);
  const next = new Date(y, m - 1, d + n);
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-${String(next.getDate()).padStart(2, '0')}`;
};

/** Number of working days from–to (inclusive) */
export const workingDaysBetween = (days: ProjectDays, from: string, to: string): number => {
  let count = 0;
  for (let d = from; d <= to; d = addDays(d, 1)) if (worksOn(days, d)) count += 1;
  return count;
};
