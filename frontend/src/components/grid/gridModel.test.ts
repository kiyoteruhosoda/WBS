import { describe, expect, it } from 'vitest';
import { moveCell, parseChoice, parseClipboard, parseDay, parseNumber, planPaste, tabCell } from './gridModel';

describe('gridModel', () => {
  it('moves with arrows and stops at the edges', () => {
    expect(moveCell({ row: 0, col: 0 }, 'up', 3, 4)).toEqual({ row: 0, col: 0 });
    expect(moveCell({ row: 0, col: 0 }, 'down', 3, 4)).toEqual({ row: 1, col: 0 });
    expect(moveCell({ row: 2, col: 3 }, 'right', 3, 4)).toEqual({ row: 2, col: 3 });
    expect(moveCell({ row: 2, col: 3 }, 'left', 3, 4)).toEqual({ row: 2, col: 2 });
  });

  it('tabs to the next cell and wraps to the next row', () => {
    expect(tabCell({ row: 0, col: 3 }, false, 3, 4)).toEqual({ row: 1, col: 0 });
    expect(tabCell({ row: 1, col: 0 }, true, 3, 4)).toEqual({ row: 0, col: 3 });
    expect(tabCell({ row: 2, col: 3 }, false, 3, 4)).toBeNull();
    expect(tabCell({ row: 0, col: 0 }, true, 3, 4)).toBeNull();
  });

  it('reads rows and columns copied from a spreadsheet', () => {
    expect(parseClipboard('8\t50\r\n6\t75\r\n')).toEqual([['8', '50'], ['6', '75']]);
    expect(parseClipboard('8')).toEqual([['8']]);
    expect(parseClipboard('a\n\nb')).toEqual([['a'], [''], ['b']]);
  });

  it('places pasted cells from the chosen cell and drops what overflows', () => {
    expect(planPaste({ row: 1, col: 2 }, [['8', '50'], [' 6 ', '75'], ['4', '25']], 3, 3)).toEqual([
      { row: 1, col: 2, raw: '8' },
      { row: 2, col: 2, raw: '6' },
    ]);
  });

  it('reads numbers with units and full-width digits', () => {
    expect(parseNumber('7.5h', { min: 0, max: 24 })).toEqual({ ok: true, value: 7.5 });
    expect(parseNumber('５０％', { min: 0, max: 100, integer: true })).toEqual({ ok: true, value: 50 });
    expect(parseNumber('8時間', { min: 0, max: 24 })).toEqual({ ok: true, value: 8 });
    expect(parseNumber('50.5', { min: 0, max: 100, integer: true })).toEqual({ ok: false });
    expect(parseNumber('25', { min: 0, max: 24 })).toEqual({ ok: false });
    expect(parseNumber('abc', { min: 0, max: 24 })).toEqual({ ok: false });
    expect(parseNumber('', { min: 0, max: 24 })).toEqual({ ok: false });
    expect(parseNumber('', { min: 1, max: 100, allowEmpty: true })).toEqual({ ok: true, value: null });
  });

  it('reads dates in the usual forms', () => {
    expect(parseDay('2026-11-05', 2026)).toEqual({ ok: true, value: '2026-11-05' });
    expect(parseDay('2026/11/5', 2026)).toEqual({ ok: true, value: '2026-11-05' });
    expect(parseDay('12/1', 2027)).toEqual({ ok: true, value: '2027-12-01' });
    expect(parseDay('', 2026)).toEqual({ ok: true, value: null });
    expect(parseDay('2026-02-30', 2026)).toEqual({ ok: false });
    expect(parseDay('tomorrow', 2026)).toEqual({ ok: false });
  });

  it('reads a choice by its label or value', () => {
    const options = [{ value: '', label: 'なし' }, { value: '3', label: '山田 花子' }];
    expect(parseChoice('山田 花子', options)).toEqual({ ok: true, value: '3' });
    expect(parseChoice('3', options)).toEqual({ ok: true, value: '3' });
    expect(parseChoice('なし', options)).toEqual({ ok: true, value: '' });
    expect(parseChoice('だれか', options)).toEqual({ ok: false });
  });
});
