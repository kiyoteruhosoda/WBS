// The UI-independent part of the list with directly editable cells (task #557 / ADR-0059 decision 3).
// Selected-cell movement (arrows, Enter, Tab), parsing text pasted from a spreadsheet, and parsing cell values.

export interface CellPosition {
  row: number;
  col: number;
}

export type Direction = 'up' | 'down' | 'left' | 'right';

/** Moves with arrows/Enter. Stops at the edges. */
export const moveCell = (pos: CellPosition, direction: Direction, rowCount: number, colCount: number): CellPosition => {
  const clamp = (n: number, size: number) => Math.max(0, Math.min(size - 1, n));
  switch (direction) {
    case 'up': return { row: clamp(pos.row - 1, rowCount), col: pos.col };
    case 'down': return { row: clamp(pos.row + 1, rowCount), col: pos.col };
    case 'left': return { row: pos.row, col: clamp(pos.col - 1, colCount) };
    case 'right': return { row: pos.row, col: clamp(pos.col + 1, colCount) };
  }
};

/**
 * Tab (Shift+Tab) moves right (left). At the end of a row it wraps to the end of the next (previous) row.
 * Returns null past the last (first) cell (focus leaves the list).
 */
export const tabCell = (pos: CellPosition, backwards: boolean, rowCount: number, colCount: number): CellPosition | null => {
  const index = pos.row * colCount + pos.col + (backwards ? -1 : 1);
  if (index < 0 || index >= rowCount * colCount) return null;
  return { row: Math.floor(index / colCount), col: index % colCount };
};

/** Splits text copied from a spreadsheet (rows by newlines, columns by tabs). A trailing newline doesn't count as a row. */
export const parseClipboard = (text: string): string[][] => {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop();
  return lines.map((line) => line.split('\t'));
};

export interface PasteTarget {
  row: number;
  col: number;
  raw: string;
}

/** Maps pasted values onto cells with the selected cell as top-left (anything outside the list is dropped). */
export const planPaste = (start: CellPosition, matrix: string[][], rowCount: number, colCount: number): PasteTarget[] => {
  const targets: PasteTarget[] = [];
  matrix.forEach((cells, dr) => {
    cells.forEach((raw, dc) => {
      const row = start.row + dr;
      const col = start.col + dc;
      if (row < rowCount && col < colCount) targets.push({ row, col, raw: raw.trim() });
    });
  });
  return targets;
};

export type Parsed<T> = { ok: true; value: T } | { ok: false };

const NUMBER = /^[+-]?(\d+(\.\d*)?|\.\d+)$/;

/** Number (also accepts full-width digits and "h", "%", "時間" suffixes). Empty is null. Out of range or unparsable fails. */
export const parseNumber = (
  raw: string, { min, max, integer = false, allowEmpty = false }: { min: number; max: number; integer?: boolean; allowEmpty?: boolean },
): Parsed<number | null> => {
  const text = raw
    .replace(/[０-９．]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
    .replace(/(時間|ｈ|h|H|％|%)$/u, '')
    .trim();
  if (text === '') return allowEmpty ? { ok: true, value: null } : { ok: false };
  if (!NUMBER.test(text)) return { ok: false };
  const value = Number(text);
  if (value < min || value > max || (integer && !Number.isInteger(value))) return { ok: false };
  return { ok: true, value };
};

const pad = (n: number) => String(n).padStart(2, '0');

/**
 * Date. Parses "2026-11-05", "2026/11/5", "11/5" (current year) into YYYY-MM-DD. Empty is null.
 * Non-existent dates (e.g. 2/30) fail.
 */
export const parseDay = (raw: string, thisYear: number): Parsed<string | null> => {
  const text = raw.trim().replace(/[０-９／－]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0));
  if (text === '') return { ok: true, value: null };
  const full = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/.exec(text);
  const short = /^(\d{1,2})[-/.](\d{1,2})$/.exec(text);
  const [y, m, d] = full
    ? [Number(full[1]), Number(full[2]), Number(full[3])]
    : short ? [thisYear, Number(short[1]), Number(short[2])] : [NaN, NaN, NaN];
  if (Number.isNaN(y)) return { ok: false };
  const date = new Date(y, m - 1, d);
  if (date.getFullYear() !== y || date.getMonth() !== m - 1 || date.getDate() !== d) return { ok: false };
  return { ok: true, value: `${y}-${pad(m)}-${pad(d)}` };
};

/** Choice column: accepts either the display label or the value (case-insensitive, ignoring surrounding whitespace). */
export const parseChoice = (raw: string, options: { value: string; label: string }[]): Parsed<string> => {
  const text = raw.trim().toLowerCase();
  const found = options.find((o) => o.value.toLowerCase() === text || o.label.trim().toLowerCase() === text);
  return found ? { ok: true, value: found.value } : { ok: false };
};
