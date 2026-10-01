import { describe, expect, it } from 'vitest';
import type { Category, Milestone, Task } from '../types';
import { MILESTONE_COLOR, buildDeadlines, groupDeadlinesByDate } from './taskDeadlines';
import { buildMonthCells } from './monthCells';
import { layoutAllDayLane } from './weekLayout';
import { splitIntoDaySegments } from './daySegments';
import { TOKYO, occurrence } from './testOccurrences';

// タスク・マイルストーンの期限をカレンダーに出す（前の /calendar の役目）。

const task = (id: number, title: string, due: string | null, patch: Partial<Task> = {}): Task => ({
  id, user_id: 1, title, category_id: null, priority: 3, urgency: 3, status: 'TODO', start_date: null, due_date: due,
  estimated_hours: null, remaining_hours: null, remaining_hours_entered: null, actual_hours: 0, has_subtasks: false,
  rollup_actual_hours: 0, rollup_remaining_hours: null, progress_percent: 0, scheduled_hours: 0,
  unscheduled_hours: null, priority_score: 0, memo: null,
  parent_task_id: null, milestone_id: null, completed_at: null, deleted_at: null,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', ...patch,
});
const milestone = (id: number, name: string, due: string | null): Milestone => ({ id, name, due_date: due, description: null });
const categories: Category[] = [{ id: 2, name: '開発', color: '#0b8043', sort_order: 1 }];
const RANGE = { from: '2026-05-03', to: '2026-05-09' };

describe('buildDeadlines', () => {
  it('表示している期間にかかる期限だけ。消したタスク・期限なしは出さない', () => {
    const list = buildDeadlines([
      task(1, '設計書', '2026-05-04'),
      task(2, '先月', '2026-04-30'),
      task(3, '期限なし', null),
      task(4, '消した', '2026-05-05', { deleted_at: '2026-05-01T00:00:00Z' }),
      task(5, '最終日', '2026-05-09'),
    ], [], categories, RANGE);
    expect(list.map((d) => d.key)).toEqual(['task-1', 'task-5']);
  });

  it('色はカテゴリの色、済み（完了・取り消し）は印を付ける。マイルストーンは決まった色で同じ日の先頭', () => {
    const list = buildDeadlines(
      [task(1, 'b', '2026-05-04', { category_id: 2, status: 'DONE' }), task(6, 'a', '2026-05-04', { status: 'CANCELLED' })],
      [milestone(9, 'リリース', '2026-05-04')],
      categories,
      RANGE,
    );
    expect(list.map((d) => [d.key, d.color, d.done])).toEqual([
      ['milestone-9', MILESTONE_COLOR, false],
      ['task-6', '#70757a', true],
      ['task-1', '#0b8043', true],
    ]);
  });

  it('日時の形の期限も日付で読む', () => {
    expect(buildDeadlines([task(1, 'x', '2026-05-04T00:00:00')], [], [], RANGE)[0].date).toBe('2026-05-04');
  });
});

describe('期限の置き場所', () => {
  // 同じ日の中は題名の順なので、並びが決まるよう英字で始める。
  const deadlines = buildDeadlines([task(1, 'A 設計書', '2026-05-04'), task(2, 'B 見積', '2026-05-04')], [], [], RANGE);

  it('月表示: その日のマスに期限を載せる', () => {
    const cells = buildMonthCells('2026-05-01', '2026-05-01', new Map(), [], groupDeadlinesByDate(deadlines));
    expect(cells.find((c) => c.date === '2026-05-04')?.deadlines.map((d) => d.id)).toEqual([1, 2]);
    expect(cells.find((c) => c.date === '2026-05-05')?.deadlines).toEqual([]);
  });

  it('週表示: 終日の帯で、その日の終日の予定の下に積む（祝日があれば 0 段目は祝日）', () => {
    const allDay = splitIntoDaySegments(occurrence('all', '2026-05-04', 0, 1440, TOKYO), TOKYO);
    const lane = layoutAllDayLane(allDay, '2026-05-03', 7, [{ date: '2026-05-05', name: 'こどもの日' }], deadlines);
    const rows = lane.blocks
      .filter((b) => b.column === 1)
      .map((b) => [b.segment ? 'event' : `deadline-${b.deadline?.id}`, b.row]);
    expect(rows).toEqual([['event', 1], ['deadline-1', 2], ['deadline-2', 3]]);
    expect(lane.rowCount).toBe(4);
  });

  it('表示していない日の期限は置かない', () => {
    const lane = layoutAllDayLane([], '2026-05-05', 5, [], deadlines);
    expect(lane.blocks).toHaveLength(0);
  });
});
