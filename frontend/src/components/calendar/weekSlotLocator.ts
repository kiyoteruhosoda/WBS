// 画面の位置 → 週表示の時間グリッドの日と位置（task #159: タスクの一覧から時間グリッドへ落とす）。
//
// 週表示（WeekView）の外から引くので、WeekView が付けている印（`data-testid="week-scroll"` と
// 日の列の `data-day-column`）を DOM から探す。月表示のときは時間グリッドが無いので null。

import type { PointerPoint } from '../../calendar/weekGestures';

const WEEK_SCROLL_SELECTOR = '[data-testid="week-scroll"]';
const DAY_COLUMN_ATTRIBUTE = 'data-day-column';

/** 時間グリッドの中の位置: 日と、その日の 0:00 からの px（= 分。丸める前）。 */
export interface WeekSlot {
  date: string;
  offsetY: number;
}

/** 週表示の時間グリッド（縦に送れる枠）。無ければ null。 */
export const weekScrollElement = (): HTMLElement | null => document.querySelector<HTMLElement>(WEEK_SCROLL_SELECTOR);

const inside = (rect: DOMRect, client: PointerPoint): boolean =>
  client.x >= rect.left && client.x < rect.right && client.y >= rect.top && client.y < rect.bottom;

/** ポインタの下の日と位置。時間グリッドの見えている枠の外なら null。 */
export const locateWeekSlot = (client: PointerPoint): WeekSlot | null => {
  const scroll = weekScrollElement();
  if (!scroll || !inside(scroll.getBoundingClientRect(), client)) return null;
  for (const column of Array.from(scroll.querySelectorAll<HTMLElement>(`[${DAY_COLUMN_ATTRIBUTE}]`))) {
    const rect = column.getBoundingClientRect();
    if (client.x < rect.left || client.x >= rect.right) continue;
    const date = column.getAttribute(DAY_COLUMN_ATTRIBUTE);
    return date ? { date, offsetY: client.y - rect.top } : null;
  }
  return null;
};
