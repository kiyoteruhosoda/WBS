import { useCallback, useMemo, useState, useSyncExternalStore } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getCurrentTimeEntry, startTimeEntry, stopTimeEntry, updateTimeEntry } from '../api/timeEntries';
import type { TimeEntry } from '../types';
import { useAuth } from '../auth/AuthProvider';
import { isNetworkFailure } from '../pwa/connectivity';
import { pressTimeOf, pressesOf, projectSnapshot, serverClockOffsetMs } from './pendingPresses';
import type { PendingPress, PressAction, SendOutcome } from './pendingPresses';
import { timerPressQueue } from './timerPressQueue';
import { CURRENT_TIME_ENTRY_KEY } from './timerState';
import type { CurrentSnapshot, TimerFailure } from './timerState';
import { timerFailureOf } from './timerState';
import { TODAY_SUMMARY_KEY } from '../api/today';
import { CLOSING_BOARD_KEY } from '../api/closing';

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

/** 押した人。SSO を使わない配備（利用者が 1 人）では 0 */
const useTimerUserId = (): number => useAuth().user?.user_id ?? 0;

/** 溜まった押下（この人の分）。上部の打刻ボタンと「今日」の画面が同じ控えを見る */
export const usePendingPresses = (): PendingPress[] => {
  const queue = timerPressQueue();
  const presses = useSyncExternalStore(queue.subscribe, queue.getSnapshot);
  const userId = useTimerUserId();
  return useMemo(() => pressesOf(presses, userId), [presses, userId]);
};

/**
 * 「いまの打刻」の控えに、溜まった押下を重ねたもの（押した瞬間に画面を変える）。
 * 走っている打刻が溜まった Start なら isPendingEntry(entry) が真（タスクの付け替えはできない）。
 */
export const useProjectedTimeEntry = () => {
  const query = useCurrentTimeEntry();
  const presses = usePendingPresses();
  const snapshot = useMemo(() => projectSnapshot(query.data, presses, Date.now()), [query.data, presses]);
  return {
    snapshot,
    pendingCount: presses.length,
    /** 走っている打刻が溜まった Start なら、その押下（タスクをサーバに任せたかどうかを見る） */
    pendingStart: presses.length > 0 && presses[presses.length - 1].action === 'start' ? presses[presses.length - 1] : null,
    /** 控えを読めなかった（オフラインで開いた等）。走っているかどうかは分からないが、押せるようにする */
    stateUnknown: query.data === undefined && query.isError,
  };
};

/** 溜まった押下で、知らせるもの（押した人に見えるのは上部の打刻ボタンの 1 か所だけ） */
export type PressNotice =
  | { kind: 'failure'; failure: TimerFailure }
  /** 送れずに残した（つながっているのに 5xx・403 等）。もう一度押さなくてよい */
  | { kind: 'kept' }
  /** 捨てた（サーバが二度と受け取らない・7 日より前） */
  | { kind: 'dropped'; count: number; detail: string | null };

let notice: PressNotice | null = null;
const noticeListeners = new Set<() => void>();
const setNotice = (next: PressNotice | null) => {
  notice = next;
  noticeListeners.forEach((listener) => listener());
};
const subscribeNotice = (listener: () => void) => {
  noticeListeners.add(listener);
  return () => noticeListeners.delete(listener);
};

/** 打刻の知らせ（上部の打刻ボタンが出す） */
export const usePressNotice = () => ({
  notice: useSyncExternalStore(subscribeNotice, () => notice),
  clear: () => setNotice(null),
});

/**
 * 打刻の書き込み（Start・Stop・タスクの付け替え）。上部の打刻ボタンと「今日」の画面で共有する。
 *
 * Start / Stop は**まず端末に溜め、それから古い順に送る**（ADR-0028。押した時刻を `at` で送る）。
 * 送れたら「いまの打刻」の控えを置き換え、打刻を見ている問い合わせ（打刻の一覧・今日の要約・締めの画面）を読み直させる。
 */
export const useTimerWrites = () => {
  const qc = useQueryClient();
  const userId = useTimerUserId();
  const [changeFailure, setChangeFailure] = useState<TimerFailure | null>(null);

  const refreshViews = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ['time-entries', 'list'] });
    void qc.invalidateQueries({ queryKey: TODAY_SUMMARY_KEY });
    void qc.invalidateQueries({ queryKey: [CLOSING_BOARD_KEY] });
  }, [qc]);

  const remember = useCallback((next: TimeEntry | null, serverNow: string) => {
    qc.setQueryData<CurrentSnapshot>(CURRENT_TIME_ENTRY_KEY, {
      current: { entry: next, server_now: serverNow },
      receivedAt: Date.now(),
    });
    refreshViews();
  }, [qc, refreshViews]);

  const sendThroughQueue = useCallback((offsetMs: number) => timerPressQueue().send({
    userId,
    serverNowMs: () => Date.now() + offsetMs,
    send: async (press) => {
      if (press.action === 'start') {
        const res = await startTimeEntry(press.taskId, press.pressedAt);
        remember(res.started, res.server_now);
      } else {
        const res = await stopTimeEntry(press.pressedAt);
        remember(null, res.server_now);
      }
    },
  }), [userId, remember]);

  const sendPending = useCallback(async () => {
    const offsetMs = serverClockOffsetMs(qc.getQueryData<CurrentSnapshot>(CURRENT_TIME_ENTRY_KEY));
    let outcome: SendOutcome;
    try {
      outcome = await sendThroughQueue(offsetMs);
    } catch (error) {
      // 置き場が読めない等。押下は残っている（次の機会に送る）
      console.warn('[timer] could not send kept presses', error);
      return null;
    }

    if (outcome.dropped.length > 0) {
      // 捨てた分は画面の控えと食い違う。読み直す
      void qc.invalidateQueries({ queryKey: CURRENT_TIME_ENTRY_KEY });
      const last = outcome.dropped[outcome.dropped.length - 1];
      setNotice({ kind: 'dropped', count: outcome.dropped.length, detail: last.error ? timerFailureOf(last.error).detail : null });
    } else if (outcome.stoppedBy != null && !isNetworkFailure(outcome.stoppedBy) && !isUnauthorized(outcome.stoppedBy)) {
      setNotice({ kind: 'kept' });
    }
    return outcome;
  }, [qc, sendThroughQueue]);

  /** 押した。端末に残してから送る */
  const press = useCallback(async (action: PressAction, task?: { id: number | null; title?: string | null }) => {
    const offsetMs = serverClockOffsetMs(qc.getQueryData<CurrentSnapshot>(CURRENT_TIME_ENTRY_KEY));
    try {
      await timerPressQueue().keep({
        userId,
        action,
        pressedAt: pressTimeOf(Date.now(), offsetMs),
        ...(action === 'start' && task !== undefined ? { taskId: task.id, taskTitle: task.title ?? null } : {}),
      });
    } catch {
      setNotice({ kind: 'failure', failure: { conflict: false, detail: null } });
      return;
    }
    await sendPending();
  }, [qc, userId, sendPending]);

  const changeTask = useMutation({
    mutationFn: ({ id, taskId }: { id: number; taskId: number | null }) => updateTimeEntry(id, { task_id: taskId }),
    onSuccess: (updated) => {
      // 経過の起点（server_now と受け取った時刻）はそのまま。打刻だけを差し替える
      qc.setQueryData<CurrentSnapshot>(CURRENT_TIME_ENTRY_KEY, (prev) => (
        prev ? { ...prev, current: { ...prev.current, entry: updated } } : prev
      ));
      refreshViews();
    },
    onError: (error: unknown) => {
      setChangeFailure(timerFailureOf(error));
      // 書けなかった理由が状態の食い違いなら、手元の控えが古い。読み直す
      void qc.invalidateQueries({ queryKey: CURRENT_TIME_ENTRY_KEY });
    },
  });

  return {
    /** Start。taskId を省くとサーバが決める。null はタスクなし。taskTitle は送るまでの間に出す名前 */
    start: (taskId?: number | null, taskTitle?: string | null) =>
      void press('start', taskId === undefined ? undefined : { id: taskId, title: taskTitle }),
    stop: () => void press('stop'),
    /** 溜まった押下を送る（つながったとき・画面に戻ったとき） */
    sendPending,
    changeTask,
    busy: changeTask.isPending,
    /** タスクの付け替えの失敗（Start / Stop の知らせは usePressNotice） */
    failure: changeFailure,
    clearFailure: () => setChangeFailure(null),
  };
};

const isUnauthorized = (error: unknown): boolean =>
  (error as { response?: { status?: number } } | null)?.response?.status === 401;
