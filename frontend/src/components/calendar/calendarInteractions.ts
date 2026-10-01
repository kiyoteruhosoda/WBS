import type React from 'react';
import type { CalendarOccurrence } from '../../types';
import type { DaySegment } from '../../calendar/daySegments';

/** グリッドの上の位置（日 ＋ その日の 0:00 からの分）。 */
export interface GridPoint {
  date: string;
  minute: number;
}

/**
 * カレンダーの操作の口。どれも省ける（省いたボタンは出さない）。
 * API と繋ぐ段で作る・編集・削除、ドラッグ（#158）で pointer の 2 つを使う。
 */
export interface CalendarInteractions {
  onCreateEvent?: (date: string, startMinute?: number) => void;
  onEditOccurrence?: (occurrence: CalendarOccurrence) => void;
  onDeleteOccurrence?: (occurrence: CalendarOccurrence) => void;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
  /**
   * 週のグリッドで予定を押した。ドラッグで動かす・端で長さを変える（#158）の入口。
   * `edge` は押した位置が上端・下端の 10px 以内か（移植元の ResizeHandlePx）。
   */
  onEventPointerDown?: (
    event: React.PointerEvent<HTMLElement>,
    segment: DaySegment,
    edge: 'top' | 'bottom' | null,
  ) => void;
  /** 週のグリッドの空いたところを押した（ドラッグで範囲を作る #158 の入口）。分は 15 分に丸める。 */
  onGridPointerDown?: (event: React.PointerEvent<HTMLElement>, at: GridPoint) => void;
}
