// タスクとマイルストーンの期限をカレンダーに出す（task #157。前の `/calendar` の役目を引き継ぐ）。
//
// 期限は予定ではない（時刻を持たない・動かせない）ので、終日の帯に予定とは違う見た目で置く。

import type { Category, Milestone, Task } from '../types';

export interface CalendarDeadline {
  /** React の key（`task-1` / `milestone-2`） */
  key: string;
  kind: 'task' | 'milestone';
  /** タスクかマイルストーンの id */
  id: number;
  title: string;
  /** 期限の日（YYYY-MM-DD） */
  date: string;
  /** 印の色（タスクはカテゴリの色、マイルストーンは決まった色） */
  color: string;
  /** 済み（完了・取り消し）。打ち消し線で出す */
  done: boolean;
}

export const MILESTONE_COLOR = '#6B46C1';
const UNCATEGORIZED_COLOR = '#70757a';

const dateOnly = (value: string | null): string | null => (value ? value.slice(0, 10) : null);

/**
 * 表示している期間（両端を含む）にかかる期限。消したタスクは出さない。
 * 並びは日、同じ日の中はマイルストーンが先、あとは題名の順。
 */
export const buildDeadlines = (
  tasks: readonly Task[],
  milestones: readonly Milestone[],
  categories: readonly Category[],
  range: { from: string; to: string },
): CalendarDeadline[] => {
  const inRange = (date: string | null): date is string => date != null && range.from <= date && date <= range.to;
  const colors = new Map(categories.map((c) => [c.id, c.color]));
  const list: CalendarDeadline[] = [];
  for (const task of tasks) {
    const date = dateOnly(task.due_date);
    if (task.deleted_at || !inRange(date)) continue;
    list.push({
      key: `task-${task.id}`,
      kind: 'task',
      id: task.id,
      title: task.title,
      date,
      color: (task.category_id != null ? colors.get(task.category_id) : null) ?? UNCATEGORIZED_COLOR,
      done: task.status === 'DONE' || task.status === 'CANCELLED',
    });
  }
  for (const milestone of milestones) {
    const date = dateOnly(milestone.due_date);
    if (!inRange(date)) continue;
    list.push({
      key: `milestone-${milestone.id}`, kind: 'milestone', id: milestone.id, title: milestone.name, date,
      color: MILESTONE_COLOR, done: false,
    });
  }
  const kindOrder = (d: CalendarDeadline) => (d.kind === 'milestone' ? 0 : 1);
  return list.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : kindOrder(a) - kindOrder(b) || a.title.localeCompare(b.title)));
};

/** 日 → その日の期限。 */
export const groupDeadlinesByDate = (deadlines: readonly CalendarDeadline[]): Map<string, CalendarDeadline[]> => {
  const map = new Map<string, CalendarDeadline[]>();
  for (const d of deadlines) {
    const list = map.get(d.date);
    if (list) list.push(d);
    else map.set(d.date, [d]);
  }
  return map;
};
