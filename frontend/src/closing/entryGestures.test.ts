import { describe, expect, it } from 'vitest';
import {
  draggedEntryRange, entryCreateRange, entryTiming, fromLocalInputValue, laneIndexAt, splitInstantAt, toLocalInputValue,
  zonedInstant,
} from './entryGestures';
import { TOKYO } from '../calendar/testOccurrences';

const ms = (iso: string) => Date.parse(iso);
// 9:07:30〜10:00:00（東京）
const original = { startMs: ms('2026-09-01T00:07:30Z'), endMs: ms('2026-09-01T01:00:00Z') };
const grabbed = { date: '2026-09-01', startMinute: 547.5, endMinute: 600 };

describe('打刻の時刻と週表示の計算の橋渡し', () => {
  it('秒は小数の分として持つ', () => {
    expect(zonedInstant('2026-09-01', 9 * 60 + 7.5, TOKYO)).toBe(ms('2026-09-01T00:07:30Z'));
    expect(entryTiming(original, TOKYO)).toEqual({ date: '2026-09-01', startMinute: 547.5, durationMinutes: 52.5 });
  });
});

describe('打刻のドラッグ → 新しい範囲', () => {
  it('動かすと上端を 15 分に合わせ、長さ（秒）は元のまま', () => {
    expect(draggedEntryRange('move', null, original, grabbed, '2026-09-01', 30, TOKYO, false))
      .toEqual({ startMs: ms('2026-09-01T00:45:00Z'), endMs: ms('2026-09-01T01:37:30Z') });
  });

  it('Shift を押していれば 1 分刻み', () => {
    expect(draggedEntryRange('move', null, original, grabbed, '2026-09-01', 30, TOKYO, true))
      .toEqual({ startMs: ms('2026-09-01T00:38:00Z'), endMs: ms('2026-09-01T01:30:30Z') });
  });

  it('別の日の列へ動かせる', () => {
    expect(draggedEntryRange('move', null, original, grabbed, '2026-09-02', 0, TOKYO, false).startMs)
      .toBe(ms('2026-09-02T00:15:00Z'));
  });

  it('下端を伸ばすと終わりだけ、上端を伸ばすと始まりだけが変わる', () => {
    expect(draggedEntryRange('resize', 'bottom', original, grabbed, '2026-09-01', 20, TOKYO, false))
      .toEqual({ startMs: original.startMs, endMs: ms('2026-09-01T01:15:00Z') });
    expect(draggedEntryRange('resize', 'top', original, grabbed, '2026-09-01', -10, TOKYO, false))
      .toEqual({ startMs: ms('2026-09-01T00:00:00Z'), endMs: original.endMs });
  });

  it('縮めても刻み 1 つ分は残す', () => {
    expect(draggedEntryRange('resize', 'top', original, grabbed, '2026-09-01', 100, TOKYO, false).startMs)
      .toBe(ms('2026-09-01T00:45:00Z'));
    expect(draggedEntryRange('resize', 'top', original, grabbed, '2026-09-01', 100, TOKYO, true).startMs)
      .toBe(ms('2026-09-01T00:59:00Z'));
  });
});

describe('空き時間から作る範囲・分ける位置', () => {
  it('押した枠から指している枠まで（上へ引いてもよい）', () => {
    expect(entryCreateRange(125, 70, false)).toEqual({ startMinute: 60, endMinute: 135 });
    expect(entryCreateRange(125.4, 125.9, true)).toEqual({ startMinute: 125, endMinute: 126 });
    expect(entryCreateRange(1439, 1439, false)).toEqual({ startMinute: 1425, endMinute: 1440 });
  });

  it('分ける位置は刻みに合わせ、内側でなければ null', () => {
    expect(splitInstantAt(original, '2026-09-01', 572, TOKYO, false)).toBe(ms('2026-09-01T00:30:00Z'));
    expect(splitInstantAt(original, '2026-09-01', 572, TOKYO, true)).toBe(ms('2026-09-01T00:32:00Z'));
    expect(splitInstantAt(original, '2026-09-01', 600, TOKYO, false)).toBeNull();
    expect(splitInstantAt(original, '2026-09-01', 540, TOKYO, false)).toBeNull();
  });

  it('横位置からいちばん近い打刻の列', () => {
    const lanes = [{ left: 0, right: 100 }, { left: 200, right: 300 }];
    expect(laneIndexAt(50, lanes)).toBe(0);
    expect(laneIndexAt(150, lanes)).toBe(1);
    expect(laneIndexAt(-10, lanes)).toBe(0);
    expect(laneIndexAt(999, lanes)).toBe(1);
    expect(laneIndexAt(10, [])).toBe(-1);
  });
});

describe('時刻の入力欄（datetime-local）', () => {
  it('タイムゾーンの壁時計で読み書きする', () => {
    expect(toLocalInputValue(ms('2026-09-01T00:07:30Z'), TOKYO)).toBe('2026-09-01T09:07');
    expect(fromLocalInputValue('2026-09-01T09:07', TOKYO)).toBe(ms('2026-09-01T00:07:00Z'));
    expect(fromLocalInputValue('bad', TOKYO)).toBeNull();
  });
});
