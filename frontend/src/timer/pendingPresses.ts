// 打刻の Start / Stop を端末に溜めて、つながったら古い順に送る（task #192・ADR-0028）。
//
// 考え方は打刻アプリ wbstimer の ADR-0011 と揃える:
// 1. 押したら**まず端末に残し**、それから送る（送る途中でタブが閉じても押下は残る）
// 2. 送るのは**古い順に 1 件ずつ**。送れない 1 件で止め、後ろは残す（Start → Stop → Start の順が崩れると記録が壊れる）
// 3. 捨てるのは、サーバが「この押下は二度と受け取らない」と答えたもの（409 / 422）と、
//    サーバの決まり（ADR-0018 の `at`: 7 日より前は 422）に照らして**送っても断られる**とわかっているものだけ。
//    401（ログインが切れた）・403・5xx・応答なし（つながらない）は**残して止める**
// 4. 時刻はサーバの時計に寄せる（`server_now` と端末の時計の差を足す。サーバは 60 秒より先を断る）
// 5. 画面は押した瞬間に変える（溜まった押下を「いまの打刻」の控えに重ねて描く）
// 6. 同時に 2 つの送信を走らせない（同じタブでは送信中の呼び出しがその結果を待つ。タブどうしは Web Locks）
//
// DOM も IndexedDB も使わない（置き場は PressStore で受け取る）。試験は pendingPresses.test.ts。

import type { TimeEntry } from '../types';
import type { CurrentSnapshot } from './timerState';

export type PressAction = 'start' | 'stop';

/** 端末に溜まっている押下 1 件 */
export interface PendingPress {
  /** 置き場が振る番号。増える順＝押した順 */
  id: number;
  /** 押した人（同じブラウザで別の人がログインしても、その人の押下として送らない） */
  userId: number;
  action: PressAction;
  /** 押した時刻（サーバの時計に寄せた UTC の ISO 文字列）。API の `at` にそのまま渡す */
  pressedAt: string;
  /** Start のタスク。undefined はサーバに任せる（いまの予定 → 直前の打刻 → なし）、null はタスクなし */
  taskId?: number | null;
  /** 画面に出すタスクの名前（送るまでの間だけ使う） */
  taskTitle?: string | null;
}

export type NewPress = Omit<PendingPress, 'id'>;

/** 押下の置き場（本物は IndexedDB。試験は配列） */
export interface PressStore {
  add(press: NewPress): Promise<PendingPress>;
  /** 古い順（押した順） */
  listOldestFirst(): Promise<PendingPress[]>;
  remove(id: number): Promise<void>;
}

/** サーバが受け取る押下の古さの上限（ADR-0018 の `at`。それより前は締めの画面で手で足す） */
export const MAX_PRESS_AGE_MS = 7 * 24 * 60 * 60 * 1000;

/** サーバが「二度と受け取らない」と答える状態コード（重なり・確定済みの締めの期間・古すぎる・未来） */
export const REFUSED_FOR_GOOD = [409, 422] as const;

const statusOf = (error: unknown): number | undefined =>
  (error as { response?: { status?: number } } | null)?.response?.status;

/** 送れなかった押下を捨てるか残すか */
export const verdictOnSendFailure = (error: unknown): 'drop' | 'keep' => {
  const status = statusOf(error);
  return status !== undefined && (REFUSED_FOR_GOOD as readonly number[]).includes(status) ? 'drop' : 'keep';
};

/** 送っても 7 日の上限で断られる押下か（*serverNowMs* はサーバの時計に寄せた「今」） */
export const isTooOldToSend = (press: Pick<PendingPress, 'pressedAt'>, serverNowMs: number): boolean =>
  Date.parse(press.pressedAt) < serverNowMs - MAX_PRESS_AGE_MS;

/** サーバの時計と端末の時計の差（ミリ秒）。控えが無ければ 0（端末の時計をそのまま使う） */
export const serverClockOffsetMs = (snapshot: CurrentSnapshot | undefined): number =>
  snapshot ? Date.parse(snapshot.current.server_now) - snapshot.receivedAt : 0;

/** 押した時刻（サーバの時計に寄せる） */
export const pressTimeOf = (deviceNowMs: number, offsetMs: number): string =>
  new Date(deviceNowMs + offsetMs).toISOString();

/** 捨てた押下と、その理由 */
export interface DroppedPress {
  press: PendingPress;
  /** tooOld: 7 日より前（送らずに捨てた）／refused: サーバが 409・422 で断った */
  reason: 'tooOld' | 'refused';
  error: unknown;
}

export interface SendOutcome {
  sent: number;
  dropped: DroppedPress[];
  /** まだ端末に残っている（この人の）押下の数 */
  remaining: number;
  /** 途中で止まった理由（つながらない・ログイン切れ等）。全部送れた・捨てたなら null */
  stoppedBy: unknown;
}

/** 送っている間に押された分も続けて送る（ただし押され続けても終わるように、読み直しは数回まで） */
const MAX_SEND_ROUNDS = 5;

/**
 * *userId* の押下を古い順に送る。送れたら消し、409 / 422 なら捨てて次へ、それ以外の失敗で止める。
 * *send* は 1 件を API へ送る（失敗は例外で返す）。*afterEach* は 1 件片付くたび（画面の件数を減らす）。
 */
export const sendPendingPresses = async (args: {
  store: PressStore;
  userId: number;
  send: (press: PendingPress) => Promise<void>;
  serverNowMs: () => number;
  afterEach?: () => void | Promise<void>;
}): Promise<SendOutcome> => {
  const mineOf = async () => (await args.store.listOldestFirst()).filter((press) => press.userId === args.userId);
  let sent = 0;
  const dropped: DroppedPress[] = [];
  for (let round = 0; round < MAX_SEND_ROUNDS; round += 1) {
    const mine = await mineOf();
    if (mine.length === 0) break;
    for (let i = 0; i < mine.length; i += 1) {
      const press = mine[i];
      if (isTooOldToSend(press, args.serverNowMs())) {
        await args.store.remove(press.id);
        dropped.push({ press, reason: 'tooOld', error: null });
        await args.afterEach?.();
        continue;
      }
      try {
        await args.send(press);
        await args.store.remove(press.id);
        sent += 1;
      } catch (error) {
        if (verdictOnSendFailure(error) === 'keep') {
          return { sent, dropped, remaining: (await mineOf()).length, stoppedBy: error };
        }
        await args.store.remove(press.id);
        dropped.push({ press, reason: 'refused', error });
      }
      await args.afterEach?.();
    }
  }
  return { sent, dropped, remaining: (await mineOf()).length, stoppedBy: null };
};

/** この人の溜まった押下 */
export const pressesOf = (presses: readonly PendingPress[], userId: number): PendingPress[] =>
  presses.filter((press) => press.userId === userId);

/** 送るまでの間、走っていることにする打刻（番号は負＝まだサーバに無い） */
export const pendingEntryOf = (press: PendingPress): TimeEntry => ({
  id: -press.id,
  user_id: press.userId,
  task_id: press.taskId ?? null,
  task_title: press.taskTitle ?? null,
  started_at: press.pressedAt,
  ended_at: null,
  memo: null,
  source: 'timer',
  is_running: true,
  duration_seconds: 0,
  is_long_running: false,
  created_at: null,
  updated_at: null,
});

/** まだサーバに無い（溜まった Start から作った）打刻か */
export const isPendingEntry = (entry: TimeEntry): boolean => entry.id < 0;

/**
 * 「いまの打刻」の控えに、溜まった押下を重ねる（押した瞬間に画面を変える）。最後の押下が勝つ:
 * Stop なら止まっている、Start ならその時刻から走っている。溜まっていなければ控えのまま。
 * 控えが無い（オフラインで開いた）ときは、端末の時計を起点にした控えを作る。
 */
export const projectSnapshot = (
  snapshot: CurrentSnapshot | undefined,
  presses: readonly PendingPress[],
  deviceNowMs: number,
): CurrentSnapshot | undefined => {
  const last = presses[presses.length - 1];
  if (!last) return snapshot;
  const base: CurrentSnapshot = snapshot ?? {
    current: { entry: null, server_now: new Date(deviceNowMs).toISOString() },
    receivedAt: deviceNowMs,
  };
  return {
    ...base,
    current: { ...base.current, entry: last.action === 'start' ? pendingEntryOf(last) : null },
  };
};

type Listener = () => void;

/**
 * 溜まった押下の控え（タブに 1 つ）。画面は subscribe / getSnapshot で件数と中身を見る。
 * 置き場の読み書きはここを通す（読み直すたびに控えを差し替え、画面へ知らせる）。
 */
export class PendingPressQueue {
  private presses: readonly PendingPress[] = [];
  private readonly listeners = new Set<Listener>();
  private inFlight: Promise<SendOutcome> | null = null;
  private readonly store: PressStore;
  /** タブどうしで送信を重ねない（本物は Web Locks。無ければそのまま走らせる） */
  private readonly exclusive: <T>(run: () => Promise<T>) => Promise<T>;

  constructor(store: PressStore, exclusive?: <T>(run: () => Promise<T>) => Promise<T>) {
    this.store = store;
    this.exclusive = exclusive ?? ((run) => run());
  }

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): readonly PendingPress[] => this.presses;

  /** 置き場から読み直す */
  async reload(): Promise<void> {
    this.presses = await this.store.listOldestFirst();
    this.listeners.forEach((listener) => listener());
  }

  /** 押下を残す（送るのは send） */
  async keep(press: NewPress): Promise<PendingPress> {
    const kept = await this.store.add(press);
    await this.reload();
    return kept;
  }

  /** 溜まった押下を送る。送信中に呼ばれたら、その送信の結果を待つ */
  send(args: { userId: number; send: (press: PendingPress) => Promise<void>; serverNowMs: () => number }): Promise<SendOutcome> {
    if (this.inFlight) return this.inFlight;
    const run = this.exclusive(() => sendPendingPresses({
      store: this.store,
      ...args,
      afterEach: () => this.reload(),
    }));
    this.inFlight = run.finally(() => {
      this.inFlight = null;
      return this.reload();
    });
    return this.inFlight;
  }
}
