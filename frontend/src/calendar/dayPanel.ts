// 「選んだ日の予定一覧」（SelectedDayPanel）をいつ開き、どう閉じるか（ADR-0034）。
// 開くのは「この日の一覧を見たい」と押したときだけ（週の見出しの日付・月のマス）。予定やタスクのブロック・
// 期限のチップ・空き枠に触ったときは開かない（それぞれ編集・タスクを開く・作成がその場で起きる）。

/** カレンダーの上で押されたもの。 */
export type DayTapTarget =
  /** 週・平日・日の表示の見出し（曜日と日付） */
  | 'day-header'
  /** 月の表示のマス */
  | 'month-cell'
  /** 時間グリッドの空き枠（予定を作る） */
  | 'empty-slot'
  /** 終日の帯の空いたところ */
  | 'all-day-blank'
  /** 予定・タスクのブロック（編集を開く） */
  | 'occurrence'
  /** タスク・マイルストーンの期限のチップ（タスクを開く） */
  | 'deadline';

/** 押したもので日の一覧を開くか。 */
export const opensDayPanel = (target: DayTapTarget): boolean => target === 'day-header' || target === 'month-cell';

/**
 * 日を押したあとに選んでいる日。開いている日と同じ日をもう一度押したら閉じる（null）。
 * 日の一覧を開かない押し方なら、今の選択を変えない。
 */
export const nextSelectedDate = (current: string | null, target: DayTapTarget, date: string): string | null => {
  if (!opensDayPanel(target)) return current;
  return current === date ? null : date;
};

/** 下へ払って閉じる距離（px）。これより短い動き・横の動きは閉じない（中の一覧の操作と取り違えない）。 */
export const DISMISS_SWIPE_MIN_PX = 48;

/** 指を離したときの動き（下が正）で、日の一覧を閉じるか。 */
export const isDismissSwipe = (dx: number, dy: number): boolean =>
  dy >= DISMISS_SWIPE_MIN_PX && Math.abs(dy) > Math.abs(dx) * 1.5;
