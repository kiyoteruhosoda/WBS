import { describe, expect, it } from 'vitest';
import type { Calendar, CalendarViewPreset } from '../types';
import {
  allVisible, calendarForNewEvent, filterVisibleOccurrences, presetIsActive, toggledVisibleIds, visibleCalendarIds, withVisibleIds,
} from './calendarSelection';
import { occurrence, hm } from './testOccurrences';

const calendar = (id: number, patch: Partial<Calendar> = {}): Calendar => ({
  id, kind: 'EVENTS', name: `c${id}`, color_key: 'DEFAULT', sort_order: id, is_default: id === 1, is_visible: true,
  workdays: null, day_off_reason: null, counts_as_day_off: false,
  created_at: null, updated_at: null, ...patch,
});

const preset = (ids: number[]): CalendarViewPreset => ({
  id: 9, name: 'p', calendar_ids: ids, sort_order: 0, created_at: null, updated_at: null,
});

describe('表示の選択（ADR-0027）', () => {
  const work = { ...occurrence('work', '2026-10-05', hm(9), 60), calendar_id: 2 };
  const plain = { ...occurrence('plain', '2026-10-05', hm(10), 60), calendar_id: 1 };

  it('隠したカレンダーの回は出さない', () => {
    const calendars = [calendar(1), calendar(2, { is_visible: false })];
    expect(filterVisibleOccurrences([work, plain], calendars).map((o) => o.id)).toEqual(['plain']);
  });

  it('一覧がまだ無い・知らないカレンダーの回は出す', () => {
    expect(filterVisibleOccurrences([work, plain], undefined)).toHaveLength(2);
    expect(filterVisibleOccurrences([work], [calendar(1, { is_visible: false })]).map((o) => o.id)).toEqual(['work']);
  });

  it('1 つ切り替える・まとめて当てる', () => {
    const calendars = [calendar(1), calendar(2)];
    expect(toggledVisibleIds(calendars, 2)).toEqual([1]);
    const after = withVisibleIds(calendars, [2]);
    expect(visibleCalendarIds(after)).toEqual([2]);
    expect(allVisible(after)).toBe(false);
    expect(allVisible(calendars)).toBe(true);
  });

  it('新しい予定は既定のカレンダー。隠していれば表示の先頭', () => {
    expect(calendarForNewEvent([calendar(1), calendar(2)])).toBe(1);
    expect(calendarForNewEvent([calendar(1, { is_visible: false }), calendar(2)])).toBe(2);
    expect(calendarForNewEvent([calendar(1, { is_visible: false }), calendar(2, { is_visible: false })])).toBe(1);
    expect(calendarForNewEvent(undefined)).toBeNull();
    // 休みの層には入れない（ADR-0029）
    expect(calendarForNewEvent([
      calendar(1, { is_visible: false }), calendar(5, { kind: 'DAYS_OFF', day_off_reason: 'PERSONAL', is_default: false }),
    ])).toBe(1);
  });

  it('組み合わせが今の表示と同じなら当たっている', () => {
    const calendars = [calendar(1, { is_visible: false }), calendar(2)];
    expect(presetIsActive(preset([2]), calendars)).toBe(true);
    expect(presetIsActive(preset([2, 99]), calendars)).toBe(true);
    expect(presetIsActive(preset([1, 2]), calendars)).toBe(false);
  });
});
