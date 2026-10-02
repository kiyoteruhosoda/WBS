import { describe, expect, it } from 'vitest';
import type { DayTapTarget } from './dayPanel';
import { DISMISS_SWIPE_MIN_PX, isDismissSwipe, nextSelectedDate, opensDayPanel } from './dayPanel';

describe('日の一覧を開く条件（ADR-0034）', () => {
  it('日付の見出しと月のマスだけが開く', () => {
    expect(opensDayPanel('day-header')).toBe(true);
    expect(opensDayPanel('month-cell')).toBe(true);
  });

  it.each<DayTapTarget>(['occurrence', 'deadline', 'empty-slot', 'all-day-blank'])(
    '%s に触っても開かない',
    (target) => {
      expect(opensDayPanel(target)).toBe(false);
      expect(nextSelectedDate(null, target, '2026-10-02')).toBeNull();
    },
  );

  it('開いていない日を押すと開き、別の日を押すと移る', () => {
    expect(nextSelectedDate(null, 'day-header', '2026-10-02')).toBe('2026-10-02');
    expect(nextSelectedDate('2026-10-02', 'day-header', '2026-10-03')).toBe('2026-10-03');
  });

  it('同じ日をもう一度押すと閉じる', () => {
    expect(nextSelectedDate('2026-10-02', 'day-header', '2026-10-02')).toBeNull();
    expect(nextSelectedDate('2026-10-02', 'month-cell', '2026-10-02')).toBeNull();
  });

  it('タスクや予定に触っても、開いている一覧はそのまま（勝手に別の日へ移らない）', () => {
    expect(nextSelectedDate('2026-10-02', 'deadline', '2026-10-05')).toBe('2026-10-02');
    expect(nextSelectedDate('2026-10-02', 'occurrence', '2026-10-05')).toBe('2026-10-02');
  });
});

describe('下へ払って閉じる', () => {
  it('下へ一定以上なら閉じる', () => {
    expect(isDismissSwipe(0, DISMISS_SWIPE_MIN_PX)).toBe(true);
    expect(isDismissSwipe(10, 120)).toBe(true);
  });

  it('短い・上向き・横向きの動きでは閉じない', () => {
    expect(isDismissSwipe(0, DISMISS_SWIPE_MIN_PX - 1)).toBe(false);
    expect(isDismissSwipe(0, -120)).toBe(false);
    expect(isDismissSwipe(100, 60)).toBe(false);
  });
});
