import { IndexedDbPressStore, indexedDbAvailable } from './indexedDbPressStore';
import { MemoryPressStore } from './memoryPressStore';
import { PendingPressQueue } from './pendingPresses';
import type { NewPress, PendingPress, PressStore } from './pendingPresses';

// タブに 1 つの「溜まった押下」の控え（task #192・ADR-0028）。上部の打刻ボタンと「今日」の画面が同じものを見る。

/**
 * IndexedDB を使い、開けなければ（プライベートの窓の一部・容量の制限など）タブの中だけの置き場に切り替える。
 * ⚠ 押下を失わないことを優先する —— 残せないと押しても何も起きなくなる。
 */
class DevicePressStore implements PressStore {
  private primary: PressStore | null = indexedDbAvailable() ? new IndexedDbPressStore() : null;
  private readonly fallback = new MemoryPressStore();

  private async attempt<T>(primary: (store: PressStore) => Promise<T>, fallback: () => Promise<T>): Promise<T> {
    if (this.primary) {
      try {
        return await primary(this.primary);
      } catch (error) {
        console.warn('[timer] IndexedDB is unavailable; presses are kept in this tab only', error);
        this.primary = null;
      }
    }
    return fallback();
  }

  add(press: NewPress): Promise<PendingPress> {
    return this.attempt((store) => store.add(press), () => this.fallback.add(press));
  }

  listOldestFirst(): Promise<PendingPress[]> {
    return this.attempt((store) => store.listOldestFirst(), () => this.fallback.listOldestFirst());
  }

  remove(id: number): Promise<void> {
    return this.attempt((store) => store.remove(id), () => this.fallback.remove(id));
  }
}

/** タブどうしで送信を重ねない（Web Locks。無いブラウザではそのまま走らせる。サーバは同じ Start の送り直しを無害に扱う） */
const acrossTabs = <T,>(run: () => Promise<T>): Promise<T> => {
  const locks = (navigator as Navigator & { locks?: LockManager }).locks;
  return locks ? locks.request('wbs-timer-presses', run) : run();
};

let queue: PendingPressQueue | null = null;

export const timerPressQueue = (): PendingPressQueue => {
  if (!queue) {
    queue = new PendingPressQueue(new DevicePressStore(), acrossTabs);
    void queue.reload().catch(() => {});
  }
  return queue;
};
