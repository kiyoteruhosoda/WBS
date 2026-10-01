import { describe, expect, it } from 'vitest';
import {
  canRedo, canUndo, emptyHistory, recordOperation, redoOperation, undoOperation,
} from './operationHistory';

// 移植元 CalendarViewModel の Undo / Redo / PushUndo の振る舞い。
describe('操作の履歴', () => {
  it('空のときは戻せない・やり直せない', () => {
    const h = emptyHistory<string>();
    expect(canUndo(h)).toBe(false);
    expect(canRedo(h)).toBe(false);
    expect(undoOperation(h)).toBeNull();
    expect(redoOperation(h)).toBeNull();
  });

  it('新しい順に戻し、戻した順の逆にやり直す', () => {
    let h = recordOperation(recordOperation(emptyHistory<string>(), 'a'), 'b');
    const first = undoOperation(h);
    expect(first?.entry).toBe('b');
    h = first!.history;
    const second = undoOperation(h);
    expect(second?.entry).toBe('a');
    h = second!.history;
    expect(canUndo(h)).toBe(false);
    expect(canRedo(h)).toBe(true);
    const again = redoOperation(h);
    expect(again?.entry).toBe('a');
    expect(again?.history).toEqual({ past: ['a'], future: ['b'] });
  });

  it('新しい操作を積むと、やり直しの側は捨てる', () => {
    const h = recordOperation(emptyHistory<string>(), 'a');
    const undone = undoOperation(h)!.history;
    const next = recordOperation(undone, 'c');
    expect(next).toEqual({ past: ['c'], future: [] });
    expect(canRedo(next)).toBe(false);
  });

  it('上限を超えたら古いものから捨てる', () => {
    let h = emptyHistory<number>();
    for (let i = 0; i < 5; i++) h = recordOperation(h, i, 3);
    expect(h.past).toEqual([2, 3, 4]);
  });

  it('元の履歴は変えない', () => {
    const h = recordOperation(emptyHistory<string>(), 'a');
    undoOperation(h);
    expect(h).toEqual({ past: ['a'], future: [] });
  });
});
