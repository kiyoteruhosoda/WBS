// 予定（回）を書いたあとに読み直させる問い合わせ（task #185）。カレンダーと「今日」の画面で同じものを使う。

import { TODAY_SUMMARY_KEY } from '../api/today';

/** 表示している期間の回。キーは `[OCCURRENCES_QUERY, from, to, timeZone]` */
export const OCCURRENCES_QUERY = 'calendar-occurrences';
/** 表示している期間の祝日。キーは `[HOLIDAYS_QUERY, from, to]` */
export const HOLIDAYS_QUERY = 'calendar-holidays';

/**
 * 予定を作る・動かす・直す・消したあとに読み直させるもの（前方一致）。回と祝日のほか、
 * タスクの「予定済みの時間」（タスクに結んだ予定で変わる）と、「今日」の画面の要約
 * （「まだ時間を取っていないタスク」）。
 */
export const queriesAfterEventWrite = (): readonly (readonly unknown[])[] => [
  [OCCURRENCES_QUERY],
  [HOLIDAYS_QUERY],
  ['tasks'],
  ['task'],
  TODAY_SUMMARY_KEY,
];
