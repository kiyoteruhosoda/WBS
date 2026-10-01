// 締めの画面のグリッドの外（気付かせる物の一覧）から、打刻・予定の回へ飛ぶための DOM の id。

export const entryElementId = (entryId: number): string => `closing-entry-${entryId}`;

export const occurrenceElementId = (occurrenceId: string): string =>
  `closing-occurrence-${occurrenceId.replace(/[^\w-]/g, '_')}`;
