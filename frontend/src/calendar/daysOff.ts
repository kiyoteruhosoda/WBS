// 休みの 4 層を画面に重ねる（task #191、ADR-0029）。
// - 塗る・帯に名前を出すのは「表示」にしている層だけ（表示の選択）
// - 営業日かどうかは表示に関係なく「休みとして数える」で決まる（サーバーと同じ判定）
// 層の日の理由は `GET /api/calendars/days-off` の `DayOffMark`。

import type { Calendar, CalendarHoliday, DayOffMark, DayOffReason } from '../types';
import { eventColor } from './calendarColors';
import { addDays } from './zonedTime';

/** 同じ日に理由が重なったときに、塗りと帯の色をどれにするか（前ほど強い）。 */
const REASON_PRIORITY: readonly DayOffReason[] = ['NATIONAL_HOLIDAY', 'COMPANY', 'PERSONAL'];

export interface DayOffView {
  /** 終日の帯に出す休み（日に 1 つ。名前は理由を「・」でつなぐ）。表示中の層だけ */
  holidays: CalendarHoliday[];
  /** 曜日の休み（営業日の層が表示のときだけ。表示でなければ null で、画面は土日の色のまま） */
  nonWorkdays: ReadonlySet<string> | null;
  /** 営業日でない日（表示に関係なく、数える理由が 1 つでもある日） */
  nonBusinessDays: ReadonlySet<string>;
}

const layerName = (calendars: ReadonlyMap<number, Calendar>, mark: DayOffMark): string | null =>
  (mark.calendar_id != null ? calendars.get(mark.calendar_id)?.name : null) ?? null;

/** 帯の名前: 祝日は祝日名、公休・私の休みは「層の名前: 日の名前」（日の名前が無ければ層の名前）。 */
export const dayOffLabel = (mark: DayOffMark, layer: string | null): string => {
  if (mark.reason === 'NATIONAL_HOLIDAY') return mark.name ?? layer ?? '';
  if (mark.name) return layer ? `${layer}: ${mark.name}` : mark.name;
  return layer ?? '';
};

export const buildDayOffView = (marks: readonly DayOffMark[], calendars: readonly Calendar[] | undefined): DayOffView => {
  const byId = new Map((calendars ?? []).map((c) => [c.id, c]));
  // 一覧がまだ無いときは全部を表示とみなす（何も塗られない画面にしない）
  const visible = (mark: DayOffMark) => {
    if (!calendars || calendars.length === 0 || mark.calendar_id == null) return true;
    return byId.get(mark.calendar_id)?.is_visible ?? true;
  };
  const nonBusinessDays = new Set(marks.filter((m) => m.counts_as_day_off).map((m) => m.date));
  const workweek = (calendars ?? []).find((c) => c.kind === 'WORKWEEK');
  const nonWorkdays = workweek && !workweek.is_visible
    ? null
    : new Set(marks.filter((m) => m.reason === 'WEEKLY').map((m) => m.date));

  const byDate = new Map<string, DayOffMark[]>();
  for (const mark of marks) {
    if (mark.reason === 'WEEKLY' || !visible(mark)) continue;
    const list = byDate.get(mark.date) ?? [];
    list.push(mark);
    byDate.set(mark.date, list);
  }
  const holidays: CalendarHoliday[] = [];
  for (const [date, list] of byDate) {
    const sorted = [...list].sort(
      (a, b) => REASON_PRIORITY.indexOf(a.reason as DayOffReason) - REASON_PRIORITY.indexOf(b.reason as DayOffReason),
    );
    const top = sorted[0];
    const layer = top.calendar_id != null ? byId.get(top.calendar_id) : undefined;
    holidays.push({
      date,
      name: sorted.map((m) => dayOffLabel(m, layerName(byId, m))).filter(Boolean).join('・') || null,
      reason: top.reason as DayOffReason,
      color: layer ? eventColor(layer.color_key) : undefined,
    });
  }
  holidays.sort((a, b) => a.date.localeCompare(b.date));
  return { holidays, nonWorkdays, nonBusinessDays };
};

/** `from`〜`to`（両端を含む）の営業日の数。`to` が前なら 0。 */
export const businessDaysBetween = (from: string, to: string, nonBusinessDays: ReadonlySet<string>): number => {
  let count = 0;
  for (let d = from; d <= to; d = addDays(d, 1)) if (!nonBusinessDays.has(d)) count += 1;
  return count;
};

/**
 * 休みの日に置いた予定の知らせの文の材料: その日の数える理由の名前（無ければ null = 営業日）。
 * 曜日の休みは「曜日の休み」と書く（呼び手が訳した文を渡す）。
 */
export const dayOffReasonsOn = (
  date: string,
  marks: readonly DayOffMark[],
  calendars: readonly Calendar[] | undefined,
  weeklyLabel: string,
): string | null => {
  const byId = new Map((calendars ?? []).map((c) => [c.id, c]));
  const names = marks
    .filter((m) => m.date === date && m.counts_as_day_off)
    .map((m) => (m.reason === 'WEEKLY' ? weeklyLabel : dayOffLabel(m, layerName(byId, m))))
    .filter(Boolean);
  return names.length > 0 ? [...new Set(names)].join('・') : null;
};
