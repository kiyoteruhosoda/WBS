// A list with directly editable cells (task #557 / ADR-0059 decision 3; like MS Project's resource sheet and the Gantt's left table).
// - Arrow keys move the selected cell. The selected cell has a thick outline
// - Typing, Enter or F2 starts editing; Enter commits and moves down, Tab commits and moves right (Shift+Tab left), Esc cancels
// - A commit saves in place (onCommit). Delete clears columns that can be empty
// - Pasting from a spreadsheet saves cell by cell with the selected cell as the top-left (unparsable or read-only cells are skipped)
import React, { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Box } from '@mui/material';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';
import type { CellPosition, Direction, Parsed } from './gridModel';
import { moveCell, parseClipboard, planPaste, tabCell } from './gridModel';

export interface GridColumn<R> {
  key: string;
  header: string;
  width: number;
  align?: 'left' | 'right';
  /** Kind of value being edited. readonly is read-only (Enter triggers onActivate). select is a choice */
  kind: 'text' | 'number' | 'select' | 'readonly';
  /** Text used when editing starts and when copying */
  value: (row: R) => string;
  /** What to render in the cell (value when omitted) */
  display?: (row: R) => React.ReactNode;
  /** Options for select */
  options?: (row: R) => { value: string; label: string }[];
  /** Whether editable (when omitted, editable unless readonly) */
  editable?: (row: R) => boolean;
  /** Parses typed text into the value to save. ok: false when unparsable */
  parse?: (raw: string, row: R) => Parsed<unknown>;
  /** Called when Enter is pressed on a readonly column (e.g. to open the task) */
  onActivate?: (row: R) => void;
  /** Label while editing (for screen readers). header when omitted */
  hint?: string;
}

interface Props<R> {
  rows: R[];
  rowKey: (row: R) => string | number;
  /** Row name (for screen readers, e.g. a person's name or a task title) */
  rowLabel: (row: R) => string;
  columns: GridColumn<R>[];
  /** Saves one cell. Throws on failure */
  onCommit: (row: R, columnKey: string, value: unknown) => Promise<void>;
  ariaLabel: string;
  rowHeight?: number;
  headerHeight?: number;
  /** Rows placed between the header and the rows (e.g. Gantt milestones; not selectable) */
  beforeRows?: React.ReactNode;
}

type Notice = { kind: 'error' | 'info'; text: string } | null;

const cellKey = (row: number, col: number) => `${row}:${col}`;

function EditableGrid<R>({
  rows, rowKey, rowLabel, columns, onCommit, ariaLabel, rowHeight = 40, headerHeight = 40, beforeRows,
}: Props<R>) {
  const { t } = useI18n();
  const gridId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement | HTMLSelectElement | null>(null);
  const [active, setActive] = useState<CellPosition>({ row: 0, col: 0 });
  const [editing, setEditing] = useState<{ draft: string; invalid: boolean } | null>(null);
  const [saving, setSaving] = useState<Set<string>>(new Set());
  const [failed, setFailed] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<Notice>(null);
  const rowCount = rows.length;
  const colCount = columns.length;
  const width = useMemo(() => columns.reduce((sum, c) => sum + c.width, 0), [columns]);

  // When rows shrink, bring the selected cell back inside the list
  useEffect(() => {
    if (rowCount > 0 && active.row >= rowCount) setActive((a) => ({ ...a, row: rowCount - 1 }));
  }, [rowCount, active.row]);

  const isEditable = useCallback((row: R, col: GridColumn<R>) => (
    col.kind !== 'readonly' && (col.editable ? col.editable(row) : true)
  ), []);

  const cellId = (row: number, col: number) => `${gridId}-c${row}-${col}`;

  const focusGrid = () => containerRef.current?.focus({ preventScroll: true });

  // Scroll the selected cell into view
  useEffect(() => {
    document.getElementById(cellId(active.row, active.col))?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [active]);

  // When editing starts, move focus to the input before the next key and put the caret after the typed text
  const isEditingNow = editing !== null;
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!isEditingNow || !el) return;
    el.focus();
    if (el instanceof HTMLInputElement) el.setSelectionRange(el.value.length, el.value.length);
  }, [isEditingNow]);

  const mark = (setter: React.Dispatch<React.SetStateAction<Set<string>>>, key: string, on: boolean) => {
    setter((prev) => {
      const next = new Set(prev);
      if (on) next.add(key); else next.delete(key);
      return next;
    });
  };

  /** Parses and saves one cell. Returns false when unparsable (nothing saved). */
  const save = async (pos: CellPosition, raw: string): Promise<'saved' | 'unchanged' | 'invalid' | 'failed'> => {
    const row = rows[pos.row];
    const col = columns[pos.col];
    if (!row || !col || !isEditable(row, col)) return 'invalid';
    if (raw === col.value(row)) return 'unchanged';
    const parsed = col.parse ? col.parse(raw, row) : { ok: true as const, value: raw };
    if (!parsed.ok) return 'invalid';
    const key = cellKey(pos.row, pos.col);
    mark(setSaving, key, true);
    mark(setFailed, key, false);
    try {
      await onCommit(row, col.key, parsed.value);
      return 'saved';
    } catch {
      mark(setFailed, key, true);
      return 'failed';
    } finally {
      mark(setSaving, key, false);
    }
  };

  const startEditing = (draft?: string) => {
    const row = rows[active.row];
    const col = columns[active.col];
    if (!row || !col) return;
    if (!isEditable(row, col)) {
      if (col.kind === 'readonly' && col.onActivate && draft === undefined) col.onActivate(row);
      else setNotice({ kind: 'info', text: t('grid.readOnly') });
      return;
    }
    setNotice(null);
    setEditing({ draft: draft ?? col.value(row), invalid: false });
  };

  /** Commits the edit and moves. Keeps editing on an unparsable value (discarded when leaving by clicking elsewhere). */
  const commitAndMove = (next: CellPosition | null, refocus = true) => {
    if (!editing) return;
    const pos = active;
    const row = rows[pos.row];
    const col = columns[pos.col];
    if (row && col && editing.draft !== col.value(row) && col.parse && !col.parse(editing.draft, row).ok) {
      if (!refocus) {
        setEditing(null);
        setNotice({ kind: 'error', text: t('grid.invalid', { column: col.header }) });
        return;
      }
      setEditing({ ...editing, invalid: true });
      setNotice({ kind: 'error', text: t('grid.invalid', { column: col.header }) });
      return;
    }
    setEditing(null);
    void save(pos, editing.draft).then((result) => {
      if (result === 'failed') setNotice({ kind: 'error', text: t('grid.saveFailed') });
    });
    if (next) setActive(next);
    if (refocus) focusGrid();
  };

  const move = (direction: Direction) => setActive((a) => moveCell(a, direction, rowCount, colCount));

  const onGridKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (editing || rowCount === 0) return;
    const arrows: Record<string, Direction> = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' };
    if (arrows[e.key]) {
      e.preventDefault();
      move(arrows[e.key]);
      return;
    }
    if (e.key === 'Tab') {
      const next = tabCell(active, e.shiftKey, rowCount, colCount);
      if (next) {
        e.preventDefault();
        setActive(next);
      }
      return;
    }
    if (e.key === 'Home' || e.key === 'End') {
      e.preventDefault();
      setActive((a) => ({ ...a, col: e.key === 'Home' ? 0 : colCount - 1 }));
      return;
    }
    if (e.key === 'Enter' || e.key === 'F2') {
      e.preventDefault();
      startEditing();
      return;
    }
    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      void save(active, '').then((result) => {
        if (result === 'invalid') setNotice({ kind: 'info', text: t('grid.cannotClear') });
        if (result === 'failed') setNotice({ kind: 'error', text: t('grid.saveFailed') });
      });
      return;
    }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const col = columns[active.col];
      if (col && col.kind !== 'select') {
        e.preventDefault();
        startEditing(e.key);
      }
    }
  };

  const onEditorKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitAndMove(moveCell(active, e.shiftKey ? 'up' : 'down', rowCount, colCount));
    } else if (e.key === 'Tab') {
      e.preventDefault();
      commitAndMove(tabCell(active, e.shiftKey, rowCount, colCount) ?? active);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      setEditing(null);
      setNotice(null);
      focusGrid();
    }
  };

  const onPaste = async (e: React.ClipboardEvent<HTMLDivElement>) => {
    if (editing) return;
    const text = e.clipboardData.getData('text/plain');
    if (!text) return;
    e.preventDefault();
    const targets = planPaste(active, parseClipboard(text), rowCount, colCount);
    let saved = 0;
    let skipped = 0;
    // One at a time (when editing values on the same row in a row, wait for the previous save)
    for (const target of targets) {
      const result = await save({ row: target.row, col: target.col }, target.raw);
      if (result === 'saved' || result === 'unchanged') saved += 1;
      else skipped += 1;
    }
    setNotice({
      kind: skipped > 0 ? 'error' : 'info',
      text: skipped > 0 ? t('grid.pastedWithSkips', { saved, skipped }) : t('grid.pasted', { saved }),
    });
  };

  const onCopy = (e: React.ClipboardEvent<HTMLDivElement>) => {
    if (editing) return;
    const row = rows[active.row];
    const col = columns[active.col];
    if (!row || !col) return;
    e.preventDefault();
    e.clipboardData.setData('text/plain', col.value(row));
  };

  const editor = (row: R, col: GridColumn<R>) => {
    const common = {
      'aria-label': `${rowLabel(row)}: ${col.hint ?? col.header}`,
      'aria-invalid': editing?.invalid ?? false,
      onKeyDown: onEditorKeyDown,
      onBlur: () => { if (editing) commitAndMove(null, false); },
      style: {
        width: '100%', height: '100%', boxSizing: 'border-box' as const, border: 'none', outline: 'none',
        padding: '0 8px', font: 'inherit', fontSize: 13, background: ds.paper, color: ds.text,
        textAlign: col.align ?? 'left',
      },
    };
    if (col.kind === 'select') {
      return (
        <select
          {...common}
          ref={(el) => { inputRef.current = el; }}
          value={editing?.draft ?? ''}
          onChange={(e) => setEditing({ draft: e.target.value, invalid: false })}
        >
          {(col.options?.(row) ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    }
    return (
      <input
        {...common}
        ref={(el) => { inputRef.current = el; }}
        inputMode={col.kind === 'number' ? 'decimal' : undefined}
        value={editing?.draft ?? ''}
        onChange={(e) => setEditing({ draft: e.target.value, invalid: false })}
      />
    );
  };

  return (
    <Box>
      <Box
        ref={containerRef}
        role="grid"
        aria-label={ariaLabel}
        aria-rowcount={rowCount + 1}
        aria-colcount={colCount}
        aria-activedescendant={rowCount > 0 && !editing ? cellId(active.row, active.col) : undefined}
        aria-describedby={`${gridId}-help`}
        tabIndex={0}
        onKeyDown={onGridKeyDown}
        onPaste={onPaste}
        onCopy={onCopy}
        sx={{ width, outline: 'none', '&:focus-visible [data-active="true"]': { outlineWidth: 3 } }}
      >
        <Box role="row" aria-rowindex={1} sx={{
          display: 'flex', height: headerHeight, bgcolor: '#F7F7F8', borderBottom: `1px solid ${ds.border}`,
        }}>
          {columns.map((c) => (
            <Box key={c.key} role="columnheader" sx={{
              width: c.width, flexShrink: 0, px: '8px', display: 'flex', alignItems: 'center',
              justifyContent: c.align === 'right' ? 'flex-end' : 'flex-start',
              fontSize: 12, fontWeight: 700, color: ds.textSub, boxSizing: 'border-box',
              borderLeft: `1px solid ${ds.borderPale}`, '&:first-of-type': { borderLeft: 'none' },
            }}>
              {c.header}
            </Box>
          ))}
        </Box>
        {beforeRows}
        {rows.map((row, r) => (
          <Box key={rowKey(row)} role="row" aria-rowindex={r + 2} sx={{
            display: 'flex', height: rowHeight, borderBottom: '1px solid #ECECEE',
          }}>
            {columns.map((c, ci) => {
              const isActive = active.row === r && active.col === ci;
              const isEditing = isActive && editing !== null;
              const key = cellKey(r, ci);
              const editable = isEditable(row, c);
              const isFailed = failed.has(key);
              return (
                <Box
                  key={c.key}
                  id={cellId(r, ci)}
                  role="gridcell"
                  aria-colindex={ci + 1}
                  aria-selected={isActive}
                  aria-readonly={!editable}
                  aria-invalid={isFailed || undefined}
                  aria-busy={saving.has(key) || undefined}
                  aria-label={`${rowLabel(row)}: ${c.header}`}
                  data-active={isActive ? 'true' : undefined}
                  onMouseDown={(e) => {
                    // Only move focus to the list so buttons and links inside stay clickable
                    if (isEditing) return;
                    setActive({ row: r, col: ci });
                    if ((e.target as HTMLElement).closest('button, a, input, [role="checkbox"]')) return;
                    e.preventDefault();
                    focusGrid();
                  }}
                  onDoubleClick={() => { if (!isEditing) startEditing(); }}
                  sx={{
                    position: 'relative', width: c.width, flexShrink: 0, boxSizing: 'border-box',
                    display: 'flex', alignItems: 'center', minWidth: 0,
                    justifyContent: c.align === 'right' ? 'flex-end' : 'flex-start',
                    px: isEditing ? 0 : '8px', fontSize: 13, color: editable || c.kind === 'readonly' ? ds.text : ds.textMuted,
                    bgcolor: isFailed ? ds.dangerPale : saving.has(key) ? ds.primaryPale : 'transparent',
                    borderLeft: `1px solid ${ds.borderPale}`, '&:first-of-type': { borderLeft: 'none' },
                    outline: isActive ? `2px solid ${isFailed ? ds.danger : ds.primary}` : 'none',
                    outlineOffset: '-2px',
                    cursor: editable ? 'cell' : 'default',
                  }}
                >
                  {isEditing ? editor(row, c) : (
                    <Box sx={{ minWidth: 0, width: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign: c.align ?? 'left' }}>
                      {c.display ? c.display(row) : c.value(row)}
                    </Box>
                  )}
                </Box>
              );
            })}
          </Box>
        ))}
      </Box>
      <Box id={`${gridId}-help`} sx={{ display: 'none' }}>{t('grid.help')}</Box>
      <Box
        role="status" aria-live="polite"
        sx={{ minHeight: 0, fontSize: 12, px: '8px', py: notice ? '6px' : 0, color: notice?.kind === 'error' ? ds.dangerText : ds.textSub }}
      >
        {notice?.text}
      </Box>
    </Box>
  );
}

export default EditableGrid;
