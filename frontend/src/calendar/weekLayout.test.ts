import { describe, expect, it } from 'vitest';
import { splitIntoDaySegments } from './daySegments';
import {
  COLUMN_GAP_RATIO, defaultScrollTop, layoutAllDayLane, layoutTimedSegments, minuteAtOffset, pastShadeHeight,
} from './weekLayout';
import { TOKYO, hm, occurrence } from './testOccurrences';

// 移植元 NolumiaSchedulerTest/WeekViewPresentationTests.cs を写したもの（日付は 2026-05-04）。
const DAY = '2026-05-04';

const timed = (id: string, sh: number, sm: number, eh: number, em: number) => {
  const start = hm(sh, sm);
  const end = hm(eh, em);
  return occurrence(id, DAY, start, end > start ? end - start : end - start + 1440);
};

const layout = (...items: ReturnType<typeof timed>[]) => {
  const segments = items.flatMap((o) => splitIntoDaySegments(o, TOKYO)).filter((s) => s.date === DAY);
  return Object.fromEntries(layoutTimedSegments(segments).map((b) => [b.segment.occurrence.id, b]));
};

const expectedWidth = (columns: number) => (1 - COLUMN_GAP_RATIO * (columns - 1)) / columns;

describe('layoutTimedSegments（DefaultWeekEventLayoutStrategy）', () => {
  it('時間帯イベントが開始時刻の分位置に配置される', () => {
    const blocks = layout(timed('e1', 9, 30, 10, 30));
    expect(blocks.e1.top).toBe(570);
    expect(blocks.e1.height).toBe(60);
  });

  it('終日イベントは時間グリッドに表示しない', () => {
    const segments = splitIntoDaySegments(occurrence('all', DAY, 0, 1440), TOKYO);
    expect(layoutTimedSegments(segments)).toHaveLength(0);
  });

  it('重ならない予定は幅 100% になる', () => {
    const blocks = layout(timed('a', 9, 0, 10, 0), timed('b', 10, 0, 11, 0));
    expect(blocks.a.widthRatio).toBeCloseTo(1, 4);
    expect(blocks.b.widthRatio).toBeCloseTo(1, 4);
  });

  it('完全重複 2 件は幅 50% ずつになる', () => {
    const blocks = layout(timed('a', 9, 0, 10, 0), timed('b', 9, 0, 10, 0));
    expect(blocks.a.widthRatio).toBeCloseTo(expectedWidth(2), 4);
    expect(blocks.b.widthRatio).toBeCloseTo(expectedWidth(2), 4);
    expect(blocks.b.leftRatio).toBeCloseTo(expectedWidth(2) + COLUMN_GAP_RATIO, 4);
  });

  it('三重複は幅 3 分の 1 ずつになる', () => {
    const blocks = layout(timed('a', 9, 0, 11, 0), timed('b', 9, 30, 10, 30), timed('c', 9, 45, 10, 15));
    for (const id of ['a', 'b', 'c']) expect(blocks[id].widthRatio).toBeCloseTo(expectedWidth(3), 4);
    expect([blocks.a.column, blocks.b.column, blocks.c.column]).toEqual([0, 1, 2]);
  });

  it('連続予定は重複扱いしない', () => {
    const blocks = layout(timed('a', 9, 0, 10, 0), timed('b', 10, 0, 11, 0));
    expect(blocks.a.leftRatio).toBeCloseTo(0, 4);
    expect(blocks.b.leftRatio).toBeCloseTo(0, 4);
  });

  it('連鎖重複は実際の同時件数に応じて幅を使い切る', () => {
    const blocks = layout(timed('a', 10, 0, 11, 0), timed('b', 10, 30, 11, 30), timed('c', 11, 0, 12, 0));
    for (const id of ['a', 'b', 'c']) expect(Math.abs(blocks[id].widthRatio - expectedWidth(2))).toBeLessThan(0.02);
    expect(blocks.c.column).toBe(0);
  });

  it('長い予定と短い予定の組み合わせでも右側の空白列を作らない', () => {
    const blocks = layout(timed('long', 9, 0, 12, 0), timed('short1', 9, 30, 10, 0), timed('short2', 10, 30, 11, 0));
    for (const id of ['long', 'short1', 'short2']) expect(Math.abs(blocks[id].widthRatio - expectedWidth(2))).toBeLessThan(0.02);
  });

  it('両隣が重ならない長い予定は両隣と水平に重ならない', () => {
    const blocks = layout(timed('A', 15, 0, 15, 30), timed('B', 10, 0, 19, 30), timed('C', 18, 0, 19, 0));
    for (const id of ['A', 'B', 'C']) expect(Math.abs(blocks[id].widthRatio - expectedWidth(2))).toBeLessThan(0.02);
    expect(blocks.B.leftRatio).toBeCloseTo(0, 4);
    const bRight = blocks.B.leftRatio + blocks.B.widthRatio;
    expect(bRight).toBeLessThanOrEqual(blocks.A.leftRatio + 0.0001);
    expect(bRight).toBeLessThanOrEqual(blocks.C.leftRatio + 0.0001);
  });

  it('右の列が空いていれば重ならない限り広げる', () => {
    // z・y・x が 9:00 に始まって 3 列。w は x とだけ重なるので、空いた列 0 に入り、y の列まで広がる。
    const blocks = layout(timed('x', 9, 0, 12, 0), timed('y', 9, 0, 10, 0), timed('z', 9, 0, 9, 30), timed('w', 10, 30, 11, 0), timed('d', 13, 0, 14, 0));
    expect([blocks.z.column, blocks.y.column, blocks.x.column, blocks.w.column]).toEqual([0, 1, 2, 0]);
    expect(blocks.w.groupColumns).toBe(3);
    expect(blocks.w.columnSpan).toBe(2);
    expect(blocks.w.widthRatio).toBeCloseTo(expectedWidth(3) * 2 + COLUMN_GAP_RATIO, 4);
    expect(blocks.z.columnSpan).toBe(1);
    // 離れた予定は別の塊で 100%
    expect(blocks.d.groupColumns).toBe(1);
    expect(blocks.d.widthRatio).toBeCloseTo(1, 4);
  });

  it('15 分の予定は 15px、長さ 0 の予定は 60 分の枠で描く', () => {
    const blocks = layout(timed('short', 13, 0, 13, 15), { ...timed('zero', 15, 0, 16, 0), duration_minutes: 0 });
    expect(blocks.short.height).toBe(15);
    expect(blocks.zero.top).toBe(900);
    expect(blocks.zero.height).toBe(60);
  });

  it('日をまたぐ予定は、その日の区間だけを並べる', () => {
    const overnight = timed('overnight', 22, 0, 2, 0);
    const first = layoutTimedSegments(splitIntoDaySegments(overnight, TOKYO).filter((s) => s.date === DAY));
    const second = layoutTimedSegments(splitIntoDaySegments(overnight, TOKYO).filter((s) => s.date === '2026-05-05'));
    expect([first[0].top, first[0].height]).toEqual([1320, 120]);
    expect([second[0].top, second[0].height]).toEqual([0, 120]);
  });
});

describe('layoutAllDayLane（DefaultWeekAllDayLayoutStrategy）', () => {
  const weekStart = '2026-05-03';

  it('終日イベントは終日レーンのその日の列に置く', () => {
    const lane = layoutAllDayLane(splitIntoDaySegments(occurrence('all', DAY, 0, 1440), TOKYO), weekStart, 7, []);
    expect(lane.blocks).toHaveLength(1);
    expect(lane.blocks[0]).toMatchObject({ column: 1, widthColumns: 1, row: 0 });
    expect(lane.height).toBe(28);
  });

  it('終日イベントが重なる場合はスタック表示になる', () => {
    const segments = ['a', 'b'].flatMap((id) => splitIntoDaySegments(occurrence(id, DAY, 0, 1440), TOKYO));
    const lane = layoutAllDayLane(segments, weekStart, 7, []);
    expect(lane.blocks.map((b) => b.row)).toEqual([0, 1]);
    expect(lane.height).toBe(48);
  });

  it('祝日があれば祝日を 0 段目に置き、予定を 1 段下げる', () => {
    const segments = splitIntoDaySegments(occurrence('a', DAY, 0, 1440), TOKYO);
    const lane = layoutAllDayLane(segments, weekStart, 7, [{ date: '2026-05-05', name: 'こどもの日' }]);
    const holiday = lane.blocks.find((b) => b.holiday != null);
    const event = lane.blocks.find((b) => b.segment != null);
    expect(holiday).toMatchObject({ column: 2, row: 0 });
    expect(event).toMatchObject({ column: 1, row: 1 });
    expect(lane.rowCount).toBe(2);
  });

  it('表示していない日の終日と祝日は置かない（平日表示の土日）', () => {
    const segments = splitIntoDaySegments(occurrence('sat', '2026-05-09', 0, 1440), TOKYO);
    const lane = layoutAllDayLane(segments, '2026-05-04', 5, [{ date: '2026-05-10', name: null }]);
    expect(lane.blocks).toHaveLength(0);
    expect(lane.height).toBe(28);
  });
});

describe('週の表示の細かいところ', () => {
  it('開いたら今週は今の 4 時間前、それ以外は 9:00 へ送る', () => {
    expect(defaultScrollTop(false, hm(15))).toBe(540);
    expect(defaultScrollTop(true, hm(15))).toBe(hm(11));
    expect(defaultScrollTop(true, hm(2))).toBe(0);
  });

  it('過ぎた日は下まで、今日は今まで影を落とす', () => {
    expect(pastShadeHeight('2026-05-03', '2026-05-04', hm(10), 1440)).toBe(1440);
    expect(pastShadeHeight('2026-05-04', '2026-05-04', hm(10), 1440)).toBe(600);
    expect(pastShadeHeight('2026-05-05', '2026-05-04', hm(10), 1440)).toBe(0);
  });

  it('縦の位置を 15 分刻みの分へ丸める', () => {
    expect(minuteAtOffset(0)).toBe(0);
    expect(minuteAtOffset(554)).toBe(540);
    expect(minuteAtOffset(5000)).toBe(1425);
    expect(minuteAtOffset(-3)).toBe(0);
  });
});
