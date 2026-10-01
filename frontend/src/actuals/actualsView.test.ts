import { describe, expect, it } from 'vitest';
import {
  formatRatio, ganttActualLayout, groupFill,
  previousClosingPeriod, stackSegments, totalOf, UNASSIGNED_FILL, UNGROUPED_COLOR,
} from './actualsView';

describe('割合の表示', () => {
  it('百分率に。分母 0 は「—」', () => {
    expect(formatRatio(0.3333)).toBe('33%');
    expect(formatRatio(null)).toBe('—');
  });
});

describe('ガントの実績の帯', () => {
  const start = new Date(2026, 8, 1); // 9/1 から 10 日
  const span = {
    task_id: 1,
    first_date: '2026-08-28',
    last_date: '2026-09-05',
    days: [
      { date: '2026-08-28', seconds: 3600 },
      { date: '2026-09-03', seconds: 1800 },
      { date: '2026-09-05', seconds: 7200 },
    ],
  };

  it('範囲の外にはみ出す帯は端で切り、日の塗りは範囲の中だけ', () => {
    const layout = ganttActualLayout(span, start, 10);
    expect(layout.strip).toEqual({ startIdx: 0, endIdx: 4, clippedStart: true, clippedEnd: false });
    expect(layout.cells).toEqual([{ idx: 2, seconds: 1800 }, { idx: 4, seconds: 7200 }]);
  });

  it('範囲に掛からなければ帯は出さない', () => {
    expect(ganttActualLayout({ ...span, last_date: '2026-08-30', days: [] }, start, 10).strip).toBeNull();
    expect(ganttActualLayout(undefined, start, 10)).toEqual({ strip: null, cells: [] });
  });
});

describe('書き出しの既定の期間', () => {
  it('前半なら先月の後半、後半なら今月の前半', () => {
    expect(previousClosingPeriod(new Date(2026, 9, 1))).toEqual({ from: '2026-09-16', to: '2026-09-30' });
    expect(previousClosingPeriod(new Date(2026, 0, 3))).toEqual({ from: '2025-12-16', to: '2025-12-31' });
    expect(previousClosingPeriod(new Date(2026, 1, 20))).toEqual({ from: '2026-02-01', to: '2026-02-15' });
  });
});

describe('積み上げ', () => {
  const groups = [
    { key: 'category:2', name: '仕事', color: '#123456' },
    { key: 'none', name: null, color: null },
    { key: 'unassigned', name: null, color: null },
  ];

  it('凡例の順に並べ、最も長い期間を 1 とした長さにする', () => {
    const seconds = { unassigned: 900, 'category:2': 2700 };
    expect(totalOf(seconds)).toBe(3600);
    expect(stackSegments(groups, seconds, 7200)).toEqual([
      { key: 'category:2', seconds: 2700, share: 0.375 },
      { key: 'unassigned', seconds: 900, share: 0.125 },
    ]);
  });

  it('色はカテゴリの色・未分類は灰色・タスク外は斜線・マイルストーンは固定の順', () => {
    const categoryFill = (id: number, color: string | null) => color ?? `cat-${id}`;
    expect(groupFill(groups[0], 0, categoryFill)).toBe('#123456');
    expect(groupFill({ key: 'category:5', name: '私用', color: null }, 0, categoryFill)).toBe('cat-5');
    expect(groupFill(groups[1], 0, categoryFill)).toBe(UNGROUPED_COLOR);
    expect(groupFill(groups[2], 0, categoryFill)).toBe(UNASSIGNED_FILL);
    const milestone = { key: 'milestone:9', name: 'β', color: null };
    expect(groupFill(milestone, 0, categoryFill)).toBe('#2a78d6');
    expect(groupFill(milestone, 8, categoryFill)).toBe('#8E8E93');
    // プロジェクト（task #187）: 自分の色、無ければ並び順の固定色
    expect(groupFill({ key: 'project:3', name: '仕事', color: '#0017C1' }, 0, categoryFill)).toBe('#0017C1');
    expect(groupFill({ key: 'project:4', name: '私用', color: null }, 1, categoryFill)).toBe('#eb6834');
  });
});
