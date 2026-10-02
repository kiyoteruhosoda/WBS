import type { NewPress, PendingPress, PressStore } from './pendingPresses';

// 押下の置き場（IndexedDB。task #192・ADR-0028）。タブを閉じても・端末を再起動しても残る。
// 番号は IndexedDB の autoIncrement に振らせる（増える順＝押した順。消しても番号は戻らない）。

const DATABASE_NAME = 'wbs';
const DATABASE_VERSION = 1;
const STORE_NAME = 'timerPresses';

const openDatabase = (): Promise<IDBDatabase> => new Promise((resolve, reject) => {
  const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
  request.onupgradeneeded = () => {
    const db = request.result;
    if (!db.objectStoreNames.contains(STORE_NAME)) {
      db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
    }
  };
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(request.error);
  request.onblocked = () => reject(new Error('IndexedDB is blocked'));
});

export class IndexedDbPressStore implements PressStore {
  private database: Promise<IDBDatabase> | null = null;

  /**
   * 1 つの取引で 1 つの要求を出し、**取引が書き終わってから**結果を返す
   * （要求の成功の時点ではまだ書けていない。直後にタブが閉じても押下が残るように）。
   */
  private async run<T>(mode: IDBTransactionMode, request: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
    this.database ??= openDatabase();
    let transaction: IDBTransaction;
    try {
      transaction = (await this.database).transaction(STORE_NAME, mode);
    } catch (error) {
      this.database = null; // 開き直せるように（閉じられた・作り直された等）
      throw error;
    }
    const pending = request(transaction.objectStore(STORE_NAME));
    return new Promise<T>((resolve, reject) => {
      transaction.oncomplete = () => resolve(pending.result);
      transaction.onerror = () => reject(transaction.error ?? pending.error);
      transaction.onabort = () => reject(transaction.error ?? new Error('IndexedDB transaction aborted'));
    });
  }

  async add(press: NewPress): Promise<PendingPress> {
    const id = await this.run('readwrite', (store) => store.add(press));
    return { ...press, id: Number(id) };
  }

  async listOldestFirst(): Promise<PendingPress[]> {
    // 主キー（番号）の昇順で返る
    return this.run('readonly', (store) => store.getAll() as IDBRequest<PendingPress[]>);
  }

  async remove(id: number): Promise<void> {
    await this.run('readwrite', (store) => store.delete(id));
  }
}

/** IndexedDB が使えるか（使えなければタブの中だけの置き場にする） */
export const indexedDbAvailable = (): boolean => {
  try {
    return typeof indexedDB !== 'undefined' && indexedDB !== null;
  } catch {
    return false;
  }
};
