import type { NewPress, PendingPress, PressStore } from './pendingPresses';

/**
 * 押下の置き場（タブの中だけ）。IndexedDB が使えないブラウザ（プライベートの窓の一部など）での代わりと、試験に使う。
 * ⚠ タブを閉じると消える。
 */
export class MemoryPressStore implements PressStore {
  private presses: PendingPress[] = [];
  private nextId = 1;

  async add(press: NewPress): Promise<PendingPress> {
    const kept = { ...press, id: this.nextId };
    this.nextId += 1;
    this.presses.push(kept);
    return kept;
  }

  async listOldestFirst(): Promise<PendingPress[]> {
    return [...this.presses].sort((a, b) => a.id - b.id);
  }

  async remove(id: number): Promise<void> {
    this.presses = this.presses.filter((press) => press.id !== id);
  }
}
