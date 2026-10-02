import { describe, expect, it } from 'vitest';
import { MemoryPressStore } from './memoryPressStore';
import {
  MAX_PRESS_AGE_MS, PendingPressQueue, isPendingEntry, isTooOldToSend, pressTimeOf, projectSnapshot,
  sendPendingPresses, serverClockOffsetMs, verdictOnSendFailure,
} from './pendingPresses';
import type { NewPress, PendingPress } from './pendingPresses';
import type { CurrentSnapshot } from './timerState';

const NOW = Date.parse('2026-10-02T09:00:00Z');
const at = (minutesAgo: number) => new Date(NOW - minutesAgo * 60_000).toISOString();
const failure = (status?: number) => (status === undefined
  ? Object.assign(new Error('Network Error'), { isAxiosError: true, code: 'ERR_NETWORK' })
  : Object.assign(new Error(`HTTP ${status}`), { isAxiosError: true, response: { status, data: { detail: `refused ${status}` } } }));

const storeWith = async (...presses: NewPress[]) => {
  const store = new MemoryPressStore();
  for (const press of presses) await store.add(press);
  return store;
};

const start = (minutesAgo: number, extra: Partial<NewPress> = {}): NewPress =>
  ({ userId: 1, action: 'start', pressedAt: at(minutesAgo), ...extra });
const stop = (minutesAgo: number, extra: Partial<NewPress> = {}): NewPress =>
  ({ userId: 1, action: 'stop', pressedAt: at(minutesAgo), ...extra });

describe('溜めた押下を送る順と止まり方', () => {
  it('押した順（古い順）に 1 件ずつ送り、送れたら消す', async () => {
    const store = await storeWith(start(30), stop(20), start(10, { taskId: 5 }));
    const sent: string[] = [];
    const outcome = await sendPendingPresses({
      store, userId: 1, serverNowMs: () => NOW,
      send: async (press) => { sent.push(`${press.action}@${press.pressedAt}`); },
    });
    expect(sent).toEqual([`start@${at(30)}`, `stop@${at(20)}`, `start@${at(10)}`]);
    expect(outcome).toMatchObject({ sent: 3, remaining: 0, stoppedBy: null, dropped: [] });
    expect(await store.listOldestFirst()).toEqual([]);
  });

  it('つながらない 1 件で止め、その後ろは送らずに残す（順を崩さない）', async () => {
    const store = await storeWith(start(30), stop(20), start(10));
    const sent: string[] = [];
    const outcome = await sendPendingPresses({
      store, userId: 1, serverNowMs: () => NOW,
      send: async (press) => {
        if (press.action === 'stop') throw failure();
        sent.push(press.action);
      },
    });
    expect(sent).toEqual(['start']);
    expect(outcome.sent).toBe(1);
    expect(outcome.remaining).toBe(2);
    expect(outcome.stoppedBy).toBeInstanceOf(Error);
    expect((await store.listOldestFirst()).map((press) => press.action)).toEqual(['stop', 'start']);
  });

  it.each([401, 403, 500, 502, 503])('%i は残して止める（ログイン切れ・Web で未ログイン・サーバの不調は、あとで送れる）', async (status) => {
    const store = await storeWith(start(10));
    const outcome = await sendPendingPresses({
      store, userId: 1, serverNowMs: () => NOW, send: async () => { throw failure(status); },
    });
    expect(outcome.remaining).toBe(1);
    expect(await store.listOldestFirst()).toHaveLength(1);
  });

  it.each([409, 422])('%i は捨てて次へ進む（サーバが二度と受け取らない。残すと先頭で詰まる）', async (status) => {
    const store = await storeWith(start(30), stop(20));
    const sent: string[] = [];
    const outcome = await sendPendingPresses({
      store, userId: 1, serverNowMs: () => NOW,
      send: async (press) => {
        if (press.action === 'start') throw failure(status);
        sent.push(press.action);
      },
    });
    expect(sent).toEqual(['stop']);
    expect(outcome.sent).toBe(1);
    expect(outcome.dropped).toHaveLength(1);
    expect(outcome.dropped[0]).toMatchObject({ reason: 'refused', press: { action: 'start' } });
    expect(await store.listOldestFirst()).toEqual([]);
  });

  it('7 日より前の押下は送らずに捨てる（サーバの at の上限。締めの画面で手で足す）', async () => {
    const tooOld = MAX_PRESS_AGE_MS / 60_000 + 1;
    const store = await storeWith(start(tooOld), stop(10));
    const sent: string[] = [];
    const outcome = await sendPendingPresses({
      store, userId: 1, serverNowMs: () => NOW, send: async (press) => { sent.push(press.action); },
    });
    expect(sent).toEqual(['stop']);
    expect(outcome.dropped).toMatchObject([{ reason: 'tooOld', press: { action: 'start' } }]);
  });

  it('ほかの人の押下は送らない・消さない（同じブラウザで別の人がログインした）', async () => {
    const store = await storeWith(start(30, { userId: 2 }), start(10));
    const sent: number[] = [];
    await sendPendingPresses({
      store, userId: 1, serverNowMs: () => NOW, send: async (press) => { sent.push(press.userId); },
    });
    expect(sent).toEqual([1]);
    expect((await store.listOldestFirst()).map((press) => press.userId)).toEqual([2]);
  });
});

describe('捨てる条件', () => {
  it('捨てるのは 409 / 422 だけ', () => {
    expect(verdictOnSendFailure(failure(409))).toBe('drop');
    expect(verdictOnSendFailure(failure(422))).toBe('drop');
    expect(verdictOnSendFailure(failure(400))).toBe('keep');
    expect(verdictOnSendFailure(failure(401))).toBe('keep');
    expect(verdictOnSendFailure(failure(403))).toBe('keep');
    expect(verdictOnSendFailure(failure(500))).toBe('keep');
    expect(verdictOnSendFailure(failure())).toBe('keep');
    expect(verdictOnSendFailure(null)).toBe('keep');
  });

  it('古すぎるのは 7 日を過ぎたものから', () => {
    expect(isTooOldToSend({ pressedAt: new Date(NOW - MAX_PRESS_AGE_MS).toISOString() }, NOW)).toBe(false);
    expect(isTooOldToSend({ pressedAt: new Date(NOW - MAX_PRESS_AGE_MS - 1000).toISOString() }, NOW)).toBe(true);
  });
});

describe('押した時刻', () => {
  it('サーバの時計に寄せる（端末の時計が 90 秒遅れていても、サーバの「今」で付く）', () => {
    const snapshot: CurrentSnapshot = {
      current: { entry: null, server_now: new Date(NOW + 90_000).toISOString() }, receivedAt: NOW,
    };
    const offset = serverClockOffsetMs(snapshot);
    expect(offset).toBe(90_000);
    expect(pressTimeOf(NOW + 5000, offset)).toBe(new Date(NOW + 95_000).toISOString());
  });

  it('控えが無ければ端末の時計のまま', () => {
    expect(serverClockOffsetMs(undefined)).toBe(0);
  });
});

describe('溜めた押下を画面に重ねる', () => {
  const running = {
    id: 9, user_id: 1, task_id: 3, task_title: '設計', started_at: at(60), ended_at: null, memo: null,
    source: 'timer' as const, is_running: true, duration_seconds: 0, is_long_running: false, created_at: null, updated_at: null,
  };
  const snapshot: CurrentSnapshot = { current: { entry: running, server_now: new Date(NOW).toISOString() }, receivedAt: NOW };
  const kept = (press: NewPress, id: number): PendingPress => ({ ...press, id });

  it('溜まっていなければサーバの控えのまま', () => {
    expect(projectSnapshot(snapshot, [], NOW)).toBe(snapshot);
  });

  it('最後が Stop なら止まっている', () => {
    expect(projectSnapshot(snapshot, [kept(stop(5), 1)], NOW)?.current.entry).toBeNull();
  });

  it('最後が Start なら、押した時刻から走っている（まだサーバに無い打刻）', () => {
    const projected = projectSnapshot(snapshot, [kept(stop(5), 1), kept(start(2, { taskId: 4, taskTitle: '実装' }), 2)], NOW);
    const entry = projected?.current.entry;
    expect(entry).toMatchObject({ task_id: 4, task_title: '実装', started_at: at(2), is_running: true });
    expect(entry && isPendingEntry(entry)).toBe(true);
    expect(isPendingEntry(running)).toBe(false);
    // 経過の起点はサーバの控えのまま
    expect(projected?.current.server_now).toBe(snapshot.current.server_now);
  });

  it('控えが無い（オフラインで開いた）ときは端末の時計を起点にする', () => {
    const projected = projectSnapshot(undefined, [kept(start(1), 1)], NOW);
    expect(projected).toMatchObject({ receivedAt: NOW, current: { server_now: new Date(NOW).toISOString() } });
  });
});

describe('タブの中の控え', () => {
  it('送信中にもう一度送ろうとしても、同じ送信の結果を待つ（同じ押下を 2 度送らない）', async () => {
    const store = await storeWith(start(10));
    const queue = new PendingPressQueue(store);
    let calls = 0;
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const send = async () => { calls += 1; await gate; };
    const first = queue.send({ userId: 1, send, serverNowMs: () => NOW });
    const second = queue.send({ userId: 1, send, serverNowMs: () => NOW });
    release();
    expect(await second).toBe(await first);
    expect(calls).toBe(1);
  });

  it('残した押下は控えに出て、送れたら消える（件数が画面に出る）', async () => {
    const queue = new PendingPressQueue(new MemoryPressStore());
    await queue.keep(start(1));
    await queue.keep(stop(0));
    expect(queue.getSnapshot().map((press) => press.action)).toEqual(['start', 'stop']);
    await queue.send({ userId: 1, send: async () => {}, serverNowMs: () => NOW });
    expect(queue.getSnapshot()).toEqual([]);
  });
});
