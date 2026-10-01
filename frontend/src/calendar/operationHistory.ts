// 操作の履歴（元に戻す・やり直し）。移植元 `CalendarViewModel` の `_undoStack` / `_redoStack`。
//
// 中身は呼び手が決める（見本ページは「前と後の回」、API と繋いだ後は「前と後の時刻」）。
// 新しい操作を積むと、やり直しの側は捨てる。

export interface OperationHistory<T> {
  /** 古い順。最後が次に戻すもの */
  readonly past: readonly T[];
  /** 最後が次にやり直すもの */
  readonly future: readonly T[];
}

/** 覚えておく操作の数の上限（古いものから捨てる）。 */
export const HISTORY_LIMIT = 100;

export const emptyHistory = <T>(): OperationHistory<T> => ({ past: [], future: [] });

export const canUndo = <T>(history: OperationHistory<T>): boolean => history.past.length > 0;

export const canRedo = <T>(history: OperationHistory<T>): boolean => history.future.length > 0;

export const recordOperation = <T>(history: OperationHistory<T>, entry: T, limit = HISTORY_LIMIT): OperationHistory<T> => ({
  past: [...history.past, entry].slice(-limit),
  future: [],
});

/** 戻す操作と、戻した後の履歴。戻すものが無ければ null。 */
export const undoOperation = <T>(history: OperationHistory<T>): { entry: T; history: OperationHistory<T> } | null => {
  if (history.past.length === 0) return null;
  const entry = history.past[history.past.length - 1];
  return { entry, history: { past: history.past.slice(0, -1), future: [...history.future, entry] } };
};

/** やり直す操作と、やり直した後の履歴。やり直すものが無ければ null。 */
export const redoOperation = <T>(history: OperationHistory<T>): { entry: T; history: OperationHistory<T> } | null => {
  if (history.future.length === 0) return null;
  const entry = history.future[history.future.length - 1];
  return { entry, history: { past: [...history.past, entry], future: history.future.slice(0, -1) } };
};
