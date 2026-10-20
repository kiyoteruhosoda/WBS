// プロジェクトのカレンダー（ADR-0059・ADR-0060）で、その日に働くか・休日の名前を引く（task #559。ガントの列と営業日の数）。
// 画面に依らない計算だけを置く。
import type { TeamCalendar, WeekdayCode } from '../types';

const WEEKDAYS_SUNDAY_FIRST: readonly WeekdayCode[] = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
const MON_TO_FRI: readonly WeekdayCode[] = ['MO', 'TU', 'WE', 'TH', 'FR'];

export interface ProjectDays {
  workdays: ReadonlySet<WeekdayCode>;
  /** 休日（日付 → 名前。名前の無いものは null） */
  daysOff: ReadonlyMap<string, string | null>;
  /** 稼働日（稼働しない曜日に働く日） */
  extraWorkdays: ReadonlyMap<string, string | null>;
}

/** 全部・未分類を表示しているとき・カレンダーの無いタスク: 月〜金、休日なし */
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

/** その日に働くか（稼働日 > 休日 > 曜日。休日と稼働日はサーバーで重ならないように組んである） */
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

/** from〜to（両端を含む）の働く日の数 */
export const workingDaysBetween = (days: ProjectDays, from: string, to: string): number => {
  let count = 0;
  for (let d = from; d <= to; d = addDays(d, 1)) if (worksOn(days, d)) count += 1;
  return count;
};
