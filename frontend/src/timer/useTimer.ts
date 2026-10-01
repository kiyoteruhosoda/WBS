import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getCurrentTimeEntry, startTimeEntry, stopTimeEntry, updateTimeEntry } from '../api/timeEntries';
import type { TimeEntry } from '../types';
import { CURRENT_TIME_ENTRY_KEY } from './timerState';
import type { CurrentSnapshot, TimerFailure } from './timerState';
import { timerFailureOf } from './timerState';
import { TODAY_SUMMARY_KEY } from '../api/today';

const fetchCurrent = async (): Promise<CurrentSnapshot> => ({
  current: await getCurrentTimeEntry(),
  receivedAt: Date.now(),
});

/** いま走っている打刻の控え。別の端末で押した分も拾うよう 1 分ごとに読み直す。 */
export const useCurrentTimeEntry = () => useQuery({
  queryKey: CURRENT_TIME_ENTRY_KEY,
  queryFn: fetchCurrent,
  refetchInterval: 60_000,
  staleTime: 0,
});

/**
 * 打刻の書き込み（Start・Stop・タスクの付け替え）。上部の打刻ボタンと「今日」の画面で共有する。
 * 書いたら「いま走っている打刻」の控えを置き換え、打刻を見ている問い合わせ（締めの一覧・今日の要約）を読み直させる。
 */
export const useTimerWrites = () => {
  const qc = useQueryClient();
  const [failure, setFailure] = useState<TimerFailure | null>(null);

  const remember = (next: TimeEntry | null, serverNow: string) => {
    qc.setQueryData<CurrentSnapshot>(CURRENT_TIME_ENTRY_KEY, {
      current: { entry: next, server_now: serverNow },
      receivedAt: Date.now(),
    });
    void qc.invalidateQueries({ queryKey: ['time-entries', 'list'] });
    void qc.invalidateQueries({ queryKey: TODAY_SUMMARY_KEY });
  };
  const onError = (error: unknown) => {
    setFailure(timerFailureOf(error));
    // 書けなかった理由が状態の食い違いなら、手元の控えが古い。読み直す
    void qc.invalidateQueries({ queryKey: CURRENT_TIME_ENTRY_KEY });
  };

  const start = useMutation({
    mutationFn: (taskId?: number | null) => startTimeEntry(taskId),
    onSuccess: (res) => remember(res.started, res.server_now),
    onError,
  });
  const stop = useMutation({
    mutationFn: stopTimeEntry,
    onSuccess: (res) => remember(null, res.server_now),
    onError,
  });
  const changeTask = useMutation({
    mutationFn: ({ id, taskId }: { id: number; taskId: number | null }) => updateTimeEntry(id, { task_id: taskId }),
    onSuccess: (updated) => {
      // 経過の起点（server_now と受け取った時刻）はそのまま。打刻だけを差し替える
      qc.setQueryData<CurrentSnapshot>(CURRENT_TIME_ENTRY_KEY, (prev) => (
        prev ? { ...prev, current: { ...prev.current, entry: updated } } : prev
      ));
      void qc.invalidateQueries({ queryKey: ['time-entries', 'list'] });
      void qc.invalidateQueries({ queryKey: TODAY_SUMMARY_KEY });
    },
    onError,
  });

  return {
    start,
    stop,
    changeTask,
    busy: start.isPending || stop.isPending || changeTask.isPending,
    failure,
    clearFailure: () => setFailure(null),
  };
};
