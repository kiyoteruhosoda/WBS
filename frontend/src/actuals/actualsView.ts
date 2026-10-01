// 実績の見える化の画面で使う純関数（task #162、ADR-0017）。
import type { BreakdownGroup, GanttActualSpan, ReportUnit } from '../types/actuals';

/** 0〜1 の割合を百分率に。分母 0（null）は「—」。 */
export const formatRatio = (ratio: number | null): string =>
  ratio === null ? '—' : `${Math.round(ratio * 100)}%`;

/** ガントの実績の帯（最初〜最後の日）と、実績のある日の塗り。 */
export const ACTUAL_STRIP_COLOR = '#D9D4F5';
export const ACTUAL_DAY_COLOR = '#4a3aa7';

const MS_PER_DAY = 86_400_000;

/** 'YYYY-MM-DD' をその日の 0:00（端末のローカル）に。ガントの日付と同じ読み方。 */
export const parseIsoDay = (s: string): Date => {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
};

export const toIsoDay = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const dayIndex = (s: string, rangeStart: Date): number =>
  Math.round((parseIsoDay(s).getTime() - rangeStart.getTime()) / MS_PER_DAY);

export interface GanttActualLayout {
  /** 最初〜最後の日の帯（表示範囲で切った日の添字、両端を含む）。範囲の外なら null。 */
  strip: { startIdx: number; endIdx: number; clippedStart: boolean; clippedEnd: boolean } | null;
  /** 実績のある日（表示範囲の中だけ）。 */
  cells: { idx: number; seconds: number }[];
}

/** ガントの 1 行の実績の帯を、表示範囲（rangeStart から dayCount 日）の添字へ直す。 */
export const ganttActualLayout = (
  span: GanttActualSpan | undefined, rangeStart: Date, dayCount: number,
): GanttActualLayout => {
  if (!span) return { strip: null, cells: [] };
  const first = dayIndex(span.first_date, rangeStart);
  const last = dayIndex(span.last_date, rangeStart);
  const strip = last < 0 || first > dayCount - 1
    ? null
    : {
      startIdx: Math.max(0, first),
      endIdx: Math.min(dayCount - 1, last),
      clippedStart: first < 0,
      clippedEnd: last > dayCount - 1,
    };
  const cells = span.days
    .map((d) => ({ idx: dayIndex(d.date, rangeStart), seconds: d.seconds }))
    .filter((c) => c.idx >= 0 && c.idx < dayCount && c.seconds > 0);
  return { strip, cells };
};

/** 締めの直前の期間（今日が前半なら先月の後半、後半なら今月の前半）。書き出しの既定。 */
export const previousClosingPeriod = (today: Date): { from: string; to: string } => {
  const y = today.getFullYear();
  const m = today.getMonth();
  if (today.getDate() <= 15) {
    const lastOfPrev = new Date(y, m, 0);
    return { from: toIsoDay(new Date(lastOfPrev.getFullYear(), lastOfPrev.getMonth(), 16)), to: toIsoDay(lastOfPrev) };
  }
  return { from: toIsoDay(new Date(y, m, 1)), to: toIsoDay(new Date(y, m, 15)) };
};

/** マイルストーンの色（固定の順。8 つを超えたぶんは灰色にまとめる——色を巡回させない）。 */
const MILESTONE_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'];
const OVERFLOW_COLOR = '#8E8E93';
// 純関数のまま試験できるよう、テーマ（MUI）は引かずに値を写す（theme.ts の ds.todoGray / ds.paper）
export const UNGROUPED_COLOR = '#B7B7BB';
/** タスク外は斜線で塗る（未分類の灰色と色だけで分けない）。 */
export const UNASSIGNED_FILL = `repeating-linear-gradient(135deg, ${UNGROUPED_COLOR} 0 3px, #FFFFFF 3px 6px)`;

/**
 * グループの塗り。カテゴリはカテゴリの色（ほかの画面と同じ ``categoryColor`` を渡す）、
 * マイルストーンは並び順の固定色。
 */
export const groupFill = (
  group: BreakdownGroup,
  milestoneOrder: number,
  categoryFill: (categoryId: number, color: string | null) => string,
): string => {
  if (group.key === 'unassigned') return UNASSIGNED_FILL;
  if (group.key === 'none') return UNGROUPED_COLOR;
  if (group.key.startsWith('category:')) return categoryFill(Number(group.key.slice('category:'.length)), group.color);
  return MILESTONE_COLORS[milestoneOrder] ?? OVERFLOW_COLOR;
};

export interface StackSegment {
  key: string;
  seconds: number;
  /** 最も長い期間を 1 とした長さ。 */
  share: number;
}

/** 積み上げの 1 本。グループの並び（凡例と同じ順）で、0 秒のものは除く。 */
export const stackSegments = (
  groups: BreakdownGroup[], secondsByGroup: Record<string, number>, maxTotal: number,
): StackSegment[] =>
  groups
    .map((g) => ({ key: g.key, seconds: secondsByGroup[g.key] ?? 0 }))
    .filter((s) => s.seconds > 0)
    .map((s) => ({ ...s, share: maxTotal > 0 ? s.seconds / maxTotal : 0 }));

export const totalOf = (secondsByGroup: Record<string, number>): number =>
  Object.values(secondsByGroup).reduce((a, b) => a + b, 0);

/** 期間の単位と範囲（空欄はサーバの既定: 今の期間で終わる 6 期間）。 */
export interface RangeValue {
  unit: ReportUnit;
  from: string;
  to: string;
}

/** 空欄はクエリに載せない。 */
export const rangeParams = (value: RangeValue): { from?: string; to?: string } => ({
  ...(value.from ? { from: value.from } : {}),
  ...(value.to ? { to: value.to } : {}),
});
