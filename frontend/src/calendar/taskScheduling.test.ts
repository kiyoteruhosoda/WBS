import { describe, expect, it } from 'vitest';
import type { Category, Task } from '../types';
import {
  buildLinkedTasks, draftFromDrop, draftFromSlot, dropStartMinute, formatHours, linkedTaskLabel, occurrenceColor,
  parseScheduleTaskParam, schedulableTasks, scheduleTaskPath, taskBlockMinutes, taskEventRequest,
} from './taskScheduling';
import { eventColor } from './calendarColors';
import { NEW_YORK, TOKYO, hm, occurrence } from './testOccurrences';

// 計画 → 予定（task #159）: タスクを時間グリッドへ落とす・枠を選ぶ → 予定を作る呼び出し。

const task = (id: number, title: string, patch: Partial<Task> = {}): Task => ({
  id, user_id: 1, title, category_id: null, priority: 3, urgency: 3, status: 'TODO', start_date: null, due_date: null,
  estimated_hours: null, remaining_hours: 4, remaining_hours_entered: null, actual_hours: 0, has_subtasks: false,
  rollup_actual_hours: 0, rollup_remaining_hours: 4, progress_percent: 0, scheduled_hours: 0, unscheduled_hours: 4,
  priority_score: 0, memo: null, parent_task_id: null, milestone_id: null, completed_at: null, deleted_at: null,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', ...patch,
});

describe('taskBlockMinutes', () => {
  it('既定は 1 時間', () => {
    expect(taskBlockMinutes({ remaining_hours: 4 })).toBe(60);
    expect(taskBlockMinutes({ remaining_hours: 1 })).toBe(60);
  });

  it('残が 1 時間より短ければ残（15 分へ切り上げ、最短 15 分）', () => {
    expect(taskBlockMinutes({ remaining_hours: 0.5 })).toBe(30);
    expect(taskBlockMinutes({ remaining_hours: 0.3 })).toBe(30); // 18 分 → 30 分
    expect(taskBlockMinutes({ remaining_hours: 0.25 })).toBe(15);
    expect(taskBlockMinutes({ remaining_hours: 0.05 })).toBe(15);
  });

  it('残が決まらない・0 なら 1 時間', () => {
    expect(taskBlockMinutes({ remaining_hours: null })).toBe(60);
    expect(taskBlockMinutes({ remaining_hours: 0 })).toBe(60);
  });
});

describe('dropStartMinute', () => {
  it('15 分へ丸め、0:00〜23:45 に収める', () => {
    expect(dropStartMinute(hm(9, 7))).toBe(hm(9));
    expect(dropStartMinute(hm(9, 8))).toBe(hm(9, 15));
    expect(dropStartMinute(-20)).toBe(0);
    expect(dropStartMinute(hm(23, 59))).toBe(hm(23, 45));
  });
});

describe('draftFromDrop → taskEventRequest', () => {
  it('落とした日と位置から、タスク名・task_id 付きの単発の予定を作る', () => {
    const draft = draftFromDrop(task(12, '設計書'), { date: '2026-10-06', offsetY: hm(13, 20) });
    expect(draft).toEqual({ taskId: 12, title: '設計書', date: '2026-10-06', startMinute: hm(13, 15), durationMinutes: 60 });
    expect(taskEventRequest(draft, TOKYO)).toEqual({
      method: 'POST',
      url: '/calendar/events',
      body: {
        title: '設計書',
        time_zone: TOKYO,
        start: '2026-10-06T04:15:00.000Z',
        duration_minutes: 60,
        location: null,
        description: null,
        color_key: 'DEFAULT',
        task_id: 12,
        recurrence: null,
      },
    });
  });

  it('残が短いタスクは残の長さで作る', () => {
    const draft = draftFromDrop(task(3, '仕上げ', { remaining_hours: 0.75 }), { date: '2026-10-06', offsetY: hm(9) });
    expect(draft.durationMinutes).toBe(45);
  });

  it('開始は閲覧者のタイムゾーンの壁時計から UTC へ直す', () => {
    const draft = draftFromDrop(task(1, 'A'), { date: '2026-10-06', offsetY: hm(9) });
    expect((taskEventRequest(draft, NEW_YORK).body as { start: string }).start).toBe('2026-10-06T13:00:00.000Z');
  });

  it('23:30 に落とすと日をまたいで 1 時間（長さは削らない）', () => {
    const draft = draftFromDrop(task(1, 'A'), { date: '2026-10-06', offsetY: hm(23, 30) });
    expect(draft.startMinute).toBe(hm(23, 30));
    expect(draft.durationMinutes).toBe(60);
  });
});

describe('draftFromSlot', () => {
  it('引いた範囲があればその長さ', () => {
    const draft = draftFromSlot(task(5, 'レビュー'), { date: '2026-10-07', startMinute: hm(10), endMinute: hm(12) });
    expect(draft).toEqual({ taskId: 5, title: 'レビュー', date: '2026-10-07', startMinute: hm(10), durationMinutes: 120 });
  });

  it('押しただけなら既定の長さ', () => {
    expect(draftFromSlot(task(5, 'レビュー', { remaining_hours: 0.5 }), { date: '2026-10-07', startMinute: hm(10) }).durationMinutes)
      .toBe(30);
  });
});

describe('schedulableTasks', () => {
  it('未完了で残があるものを、期限が近い順（期限なしは後ろ）・優先度の点の高い順に', () => {
    const list = schedulableTasks([
      task(1, '期限なし'),
      task(2, '完了', { status: 'DONE', due_date: '2026-10-01' }),
      task(3, '中止', { status: 'CANCELLED', due_date: '2026-10-01' }),
      task(4, '残なし', { remaining_hours: 0, due_date: '2026-10-01' }),
      task(5, '残が決まらない', { remaining_hours: null, due_date: '2026-10-01' }),
      task(6, '消した', { deleted_at: '2026-09-01T00:00:00Z', due_date: '2026-10-01' }),
      task(7, '来週', { due_date: '2026-10-12' }),
      task(8, '明日・低', { due_date: '2026-10-06', priority_score: 100 }),
      task(9, '明日・高', { due_date: '2026-10-06', priority_score: 500 }),
    ]);
    expect(list.map((t) => t.title)).toEqual(['明日・高', '明日・低', '来週', '期限なし']);
  });
});

describe('予定に出すタスクの印', () => {
  const categories: Category[] = [{ id: 2, name: '開発', color: '#0b8043', sort_order: 1 }];
  const categoryColor = (id: number | null | undefined, api?: string | null) => api ?? (id == null ? '#999999' : '#123456');
  const linked = buildLinkedTasks(
    [task(12, '設計書', { category_id: 2 }), task(13, '色なし', { category_id: 9 }), task(14, 'カテゴリなし')],
    categories,
    categoryColor,
  );

  it('色が既定の予定は、結んだタスクのカテゴリの色', () => {
    expect(occurrenceColor({ color_key: 'DEFAULT', task_id: 12 }, linked)).toBe('#0b8043');
    expect(occurrenceColor({ color_key: 'DEFAULT', task_id: 13 }, linked)).toBe('#123456');
    expect(occurrenceColor({ color_key: 'DEFAULT', task_id: 14 }, linked)).toBe('#999999');
  });

  it('予定に色があればそれ。タスクが無い・知らないタスクなら既定の色', () => {
    expect(occurrenceColor({ color_key: 'TOMATO', task_id: 12 }, linked)).toBe(eventColor('TOMATO'));
    expect(occurrenceColor({ color_key: 'DEFAULT', task_id: null }, linked)).toBe(eventColor('DEFAULT'));
    expect(occurrenceColor({ color_key: 'DEFAULT', task_id: 99 }, linked)).toBe(eventColor('DEFAULT'));
  });

  it('タスク名は題名と違うときだけ添える', () => {
    const o = { ...occurrence('a', '2026-10-06', hm(9), 60), task_id: 12 };
    expect(linkedTaskLabel({ ...o, title: '設計書' }, linked)).toBeNull();
    expect(linkedTaskLabel({ ...o, title: '午前の作業' }, linked)).toBe('設計書');
    expect(linkedTaskLabel({ ...o, task_id: null }, linked)).toBeNull();
  });
});

describe('クエリと表示', () => {
  it('「時間を取る」の行き先と、クエリの読み取り', () => {
    expect(scheduleTaskPath(12)).toBe('/calendar?schedule_task=12');
    expect(parseScheduleTaskParam('12')).toBe(12);
    expect(parseScheduleTaskParam(null)).toBeNull();
    expect(parseScheduleTaskParam('abc')).toBeNull();
    expect(parseScheduleTaskParam('0')).toBeNull();
    expect(parseScheduleTaskParam('-3')).toBeNull();
  });

  it('時間の表示', () => {
    expect(formatHours(1.5)).toBe('1.5h');
    expect(formatHours(2)).toBe('2h');
    expect(formatHours(0.333333)).toBe('0.33h');
    expect(formatHours(null)).toBe('—');
  });
});
