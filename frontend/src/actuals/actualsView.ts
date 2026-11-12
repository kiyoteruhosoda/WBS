// Pure functions for the actuals visualization screen (task #162, ADR-0017).
import type { BreakdownGroup, GanttActualSpan, ReportUnit } from '../types/actuals';

/** Ratio 0–1 as a percentage. Zero denominator (null) → "—". */
export const formatRatio = (ratio: number | null): string =>
  ratio === null ? '—' : `${Math.round(ratio * 100)}%`;

/** Gantt actuals bar (first to last day) and fill for days with actuals. */
export const ACTUAL_STRIP_COLOR = '#D9D4F5';
export const ACTUAL_DAY_COLOR = '#4a3aa7';

const MS_PER_DAY = 86_400_000;

/** 'YYYY-MM-DD' to 0:00 of that day (device local). Same parsing as the Gantt dates. */
export const parseIsoDay = (s: string): Date => {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
};

export const toIsoDay = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const dayIndex = (s: string, rangeStart: Date): number =>
  Math.round((parseIsoDay(s).getTime() - rangeStart.getTime()) / MS_PER_DAY);

export interface GanttActualLayout {
  /** Bar from first to last day (day indices clipped to the visible range, inclusive). null if outside the range. */
  strip: { startIdx: number; endIdx: number; clippedStart: boolean; clippedEnd: boolean } | null;
  /** Days with actuals (within the visible range only). */
  cells: { idx: number; seconds: number }[];
}

/** Convert one Gantt row's actuals bar to indices in the visible range (dayCount days from rangeStart). */
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

/** The period just before closing (second half of last month if today is in the first half, else first half of this month). Default for export. */
export const previousClosingPeriod = (today: Date): { from: string; to: string } => {
  const y = today.getFullYear();
  const m = today.getMonth();
  if (today.getDate() <= 15) {
    const lastOfPrev = new Date(y, m, 0);
    return { from: toIsoDay(new Date(lastOfPrev.getFullYear(), lastOfPrev.getMonth(), 16)), to: toIsoDay(lastOfPrev) };
  }
  return { from: toIsoDay(new Date(y, m, 1)), to: toIsoDay(new Date(y, m, 15)) };
};

/** Milestone colors (fixed order; beyond 8 they all become gray —— colors are not cycled). */
const MILESTONE_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'];
const OVERFLOW_COLOR = '#8E8E93';
// To keep this testable as pure functions, copy the values instead of reading the MUI theme (ds.todoGray / ds.paper in theme.ts)
export const UNGROUPED_COLOR = '#B7B7BB';
/** Non-task time is hatched (not distinguished from unassigned gray by color alone). */
export const UNASSIGNED_FILL = `repeating-linear-gradient(135deg, ${UNGROUPED_COLOR} 0 3px, #FFFFFF 3px 6px)`;

/**
 * Group fill. Categories use the category color (pass the same ``categoryColor`` as other screens),
 * milestones a fixed color by order. Projects use their own color (or a fixed color by order if none).
 */
export const groupFill = (
  group: BreakdownGroup,
  milestoneOrder: number,
  categoryFill: (categoryId: number, color: string | null) => string,
): string => {
  if (group.key === 'unassigned') return UNASSIGNED_FILL;
  if (group.key === 'none') return UNGROUPED_COLOR;
  if (group.key.startsWith('category:')) return categoryFill(Number(group.key.slice('category:'.length)), group.color);
  // Projects use their color if set, otherwise the same fixed order colors as milestones
  if (group.key.startsWith('project:') && group.color) return group.color;
  return MILESTONE_COLORS[milestoneOrder] ?? OVERFLOW_COLOR;
};

export interface StackSegment {
  key: string;
  seconds: number;
  /** Length relative to the longest period (= 1). */
  share: number;
}

/** One stacked bar. In group order (same as the legend), excluding zero-second entries. */
export const stackSegments = (
  groups: BreakdownGroup[], secondsByGroup: Record<string, number>, maxTotal: number,
): StackSegment[] =>
  groups
    .map((g) => ({ key: g.key, seconds: secondsByGroup[g.key] ?? 0 }))
    .filter((s) => s.seconds > 0)
    .map((s) => ({ ...s, share: maxTotal > 0 ? s.seconds / maxTotal : 0 }));

export const totalOf = (secondsByGroup: Record<string, number>): number =>
  Object.values(secondsByGroup).reduce((a, b) => a + b, 0);

/** Period unit and range (blank = server default: 6 periods ending with the current one). */
export interface RangeValue {
  unit: ReportUnit;
  from: string;
  to: string;
}

/** Blank values are left out of the query. */
export const rangeParams = (value: RangeValue): { from?: string; to?: string } => ({
  ...(value.from ? { from: value.from } : {}),
  ...(value.to ? { to: value.to } : {}),
});
