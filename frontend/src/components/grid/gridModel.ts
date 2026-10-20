// セルを直接書き換える一覧の、画面に依らない部分（task #557 / ADR-0059 決定 3）。
// 選んだセルの動き（矢印・Enter・Tab）、表計算から貼り付けた文字の読み方、セルの値の読み方。

export interface CellPosition {
  row: number;
  col: number;
}

export type Direction = 'up' | 'down' | 'left' | 'right';

/** 矢印・Enter で動く。端では止まる。 */
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
 * Tab（Shift+Tab）で右（左）へ。行の端では次（前）の行の端へ回る。
 * 一覧の最後（最初）を越えるときは null（一覧の外へ焦点を出す）。
 */
export const tabCell = (pos: CellPosition, backwards: boolean, rowCount: number, colCount: number): CellPosition | null => {
  const index = pos.row * colCount + pos.col + (backwards ? -1 : 1);
  if (index < 0 || index >= rowCount * colCount) return null;
  return { row: Math.floor(index / colCount), col: index % colCount };
};

/** 表計算からコピーした文字（行は改行、列はタブ）を行と列に分ける。最後の改行は行に数えない。 */
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

/** 選んだセルを左上として、貼り付ける値をセルに当てはめる（一覧の外へはみ出す分は捨てる）。 */
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

/** 数（全角の数字・「h」「%」「時間」の後ろ付きも読む）。空は null。範囲の外・読めないものは失敗。 */
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
 * 日付。「2026-11-05」「2026/11/5」「11/5」（年は今年）を読み、YYYY-MM-DD にする。空は null。
 * 暦に無い日（2/30 など）は失敗。
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

/** 選ぶ列: 表示の名前か値のどちらでも読む（大文字・小文字と前後の空白は見ない）。 */
export const parseChoice = (raw: string, options: { value: string; label: string }[]): Parsed<string> => {
  const text = raw.trim().toLowerCase();
  const found = options.find((o) => o.value.toLowerCase() === text || o.label.trim().toLowerCase() === text);
  return found ? { ok: true, value: found.value } : { ok: false };
};
