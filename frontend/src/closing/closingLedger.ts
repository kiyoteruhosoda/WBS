// 締めの工数表（task #389、ADR-0047）。行はプロジェクト（タスクの合計）、列は日。
// いちばん上に、その日の業務の開始（最初の打刻の始まり）と終了（最後の打刻の終わり）。休憩は差し引かない。
// 時間は 0.5 時間単位で丸めて見せる（中身は秒のまま。合計は丸める前に足す）。自動の打刻を含むセルに印。
import type { DailyTaskTotal, Project, TimeEntry, WorkBreak } from '../types';
import { toZonedPoint } from '../calendar/zonedTime';
import type { ProjectScope } from '../projects/projectScope';
import type { EntrySegment, ProjectRowHead } from './closingBoard';
import { projectRowClassifier, projectRowRank } from './closingBoard';

export interface LedgerRow extends ProjectRowHead {
  /** プロジェクトコード（プロジェクトの行だけ。無ければ null） */
  code: string | null;
  /** 日 → 秒 */
  byDate: Record<string, number>;
  total: number;
  /** WinTrack の自動の打刻を含む日 */
  autoDates: ReadonlySet<string>;
}

/** その日の業務の開始と終了（利用者のローカル日の 0:00 からの分）。 */
export interface WorkBounds {
  startMinute: number;
  endMinute: number;
}

export interface Ledger {
  dates: string[];
  rows: LedgerRow[];
  /** 日 → 秒（全部の行） */
  dayTotals: Record<string, number>;
  grandTotal: number;
  /** 日 → 業務の開始と終了（打刻の無い日は null） */
  bounds: Record<string, WorkBounds | null>;
}

/**
 * 打刻がどの行に入るか。タスクのプロジェクトは日ごとの合計（サーバーが打刻から出したもの）から引く。
 * 合計に無いタスク（ふつうは無い）は未分類として扱う。
 */
export const ledgerRowOfEntry = (
  totals: readonly DailyTaskTotal[],
  projects: readonly Project[],
  scope: ProjectScope,
): ((entry: TimeEntry) => ProjectRowHead) => {
  const classify = projectRowClassifier(projects, scope);
  const projectOfTask = new Map<number, number | null>();
  for (const t of totals) if (t.task_id != null) projectOfTask.set(t.task_id, t.project_id ?? null);
  return (entry) => classify({
    task_id: entry.task_id,
    task_title: entry.task_title,
    project_id: entry.task_id != null ? projectOfTask.get(entry.task_id) ?? null : null,
  });
};

export const buildLedger = (
  totals: readonly DailyTaskTotal[],
  segmentsByDate: ReadonlyMap<string, readonly EntrySegment[]>,
  dates: readonly string[],
  projects: readonly Project[],
  scope: ProjectScope,
): Ledger => {
  const classify = projectRowClassifier(projects, scope);
  const rowOf = ledgerRowOfEntry(totals, projects, scope);
  const rank = projectRowRank(projects);
  const codes = new Map(projects.map((p) => [p.id, p.code ?? null]));
  const rows = new Map<string, LedgerRow & { autoDates: Set<string> }>();
  const rowFor = (head: ProjectRowHead) => {
    let row = rows.get(head.key);
    if (!row) {
      row = {
        ...head,
        code: head.projectId != null ? codes.get(head.projectId) ?? null : null,
        byDate: {}, total: 0, autoDates: new Set<string>(),
      };
      rows.set(head.key, row);
    }
    return row;
  };

  const dayTotals: Record<string, number> = Object.fromEntries(dates.map((d) => [d, 0]));
  let grandTotal = 0;
  for (const t of totals) {
    const row = rowFor(classify(t));
    row.byDate[t.work_date] = (row.byDate[t.work_date] ?? 0) + t.seconds;
    row.total += t.seconds;
    dayTotals[t.work_date] = (dayTotals[t.work_date] ?? 0) + t.seconds;
    grandTotal += t.seconds;
  }

  const bounds: Record<string, WorkBounds | null> = {};
  for (const date of dates) {
    const segments = segmentsByDate.get(date) ?? [];
    bounds[date] = segments.length === 0 ? null : {
      startMinute: Math.min(...segments.map((s) => s.startMinute)),
      endMinute: Math.max(...segments.map((s) => s.endMinute)),
    };
    for (const segment of segments) {
      if (segment.entry.source === 'auto') rowFor(rowOf(segment.entry)).autoDates.add(date);
    }
  }

  return {
    dates: [...dates],
    rows: [...rows.values()].sort((a, b) => rank(a) - rank(b)),
    dayTotals,
    grandTotal,
    bounds,
  };
};

/** その日・その行の打刻の区間（セルを押したときの一覧。始まりの順）。 */
export const ledgerCellSegments = (
  segmentsByDate: ReadonlyMap<string, readonly EntrySegment[]>,
  date: string,
  rowKey: string,
  rowOf: (entry: TimeEntry) => ProjectRowHead,
): EntrySegment[] => (segmentsByDate.get(date) ?? []).filter((s) => rowOf(s.entry).key === rowKey);

/** 0.5 時間単位に丸めた時間（`6.0`・`0.5`）。中身は秒のまま持ち、見せるときだけ丸める。 */
export const formatHalfHours = (seconds: number): string => (Math.round(seconds / 1800) / 2).toFixed(1);

/** その日の休み（task #392 / ADR-0048）。区間は利用者のローカル日の 0:00 からの分。 */
export interface DayBreaks {
  seconds: number;
  spans: { startMinute: number; endMinute: number }[];
}

/**
 * 休みを日ごとに（日の計はサーバーが休みを引いてある。ここは見せるだけ）。休みは送り手がその日の中に
 * 収めて送るので、始まりの日に入れる（翌 0:00 ちょうどの終わりは 24:00）。休みの無い日は入れない。
 */
export const breaksByDate = (
  breaks: readonly WorkBreak[],
  dates: readonly string[],
  timeZone: string,
): Record<string, DayBreaks> => {
  const days = new Set(dates);
  const byDate: Record<string, DayBreaks> = {};
  for (const b of [...breaks].sort((x, y) => Date.parse(x.started_at) - Date.parse(y.started_at))) {
    const startMs = Date.parse(b.started_at);
    const endMs = Date.parse(b.ended_at);
    const start = toZonedPoint(startMs, timeZone);
    if (!days.has(start.date) || endMs <= startMs) continue;
    const end = toZonedPoint(endMs, timeZone);
    const endMinute = end.date === start.date ? end.minute : 24 * 60;
    const day = (byDate[start.date] ??= { seconds: 0, spans: [] });
    day.seconds += Math.round((endMs - startMs) / 1000);
    day.spans.push({ startMinute: start.minute, endMinute });
  }
  return byDate;
};
