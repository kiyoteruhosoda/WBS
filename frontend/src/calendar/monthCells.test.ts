import { describe, expect, it } from 'vitest';
import { availableChipRows, buildMonthCells, visibleChipCount } from './monthCells';
import { groupSegmentsByDate } from './daySegments';
import { TOKYO, hm, occurrence } from './testOccurrences';

describe('buildMonthCells', () => {
  it('6×7 のマスに、当月・今日・過去・曜日・祝日・回を載せる', () => {
    const byDate = groupSegmentsByDate([
      occurrence('a', '2026-10-01', hm(9), 60),
      occurrence('night', '2026-10-01', hm(23), 120),
    ], TOKYO);
    const cells = buildMonthCells('2026-10-01', '2026-10-01', byDate, [{ date: '2026-10-12', name: 'スポーツの日' }]);
    expect(cells).toHaveLength(42);
    const first = cells[0];
    expect(first).toMatchObject({ date: '2026-09-27', isCurrentMonth: false, isPast: true, dayOfWeek: 0 });
    const today = cells.find((c) => c.date === '2026-10-01')!;
    expect(today).toMatchObject({ isToday: true, isPast: false, isCurrentMonth: true, dayOfWeek: 4 });
    expect(today.segments.map((s) => s.occurrence.id)).toEqual(['a', 'night']);
    // 日をまたぐ回は翌日のマスにも出る
    expect(cells.find((c) => c.date === '2026-10-02')!.segments.map((s) => s.occurrence.id)).toEqual(['night']);
    expect(cells.find((c) => c.date === '2026-10-12')!.holiday?.name).toBe('スポーツの日');
    expect(cells[41]).toMatchObject({ date: '2026-11-07', isCurrentMonth: false, isPast: false });
  });
});

describe('チップの数（CalendarDayCell）', () => {
  it('マスの高さから段数を出す（見出し 36px・1 段 16px）。祝日のチップが 1 段使う', () => {
    expect(availableChipRows(88, false)).toBe(3);
    expect(availableChipRows(88, true)).toBe(2);
    expect(availableChipRows(40, true)).toBe(1);
    expect(availableChipRows(150, false)).toBe(7);
  });

  it('全部入るなら全部、入らなければ最後の段を「+N 件」に譲る', () => {
    expect(visibleChipCount(3, 3)).toBe(3);
    expect(visibleChipCount(4, 3)).toBe(2);
    expect(visibleChipCount(10, 1)).toBe(1);
    expect(visibleChipCount(0, 3)).toBe(0);
  });
});
