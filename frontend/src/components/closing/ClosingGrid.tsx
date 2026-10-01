import React, { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useI18n } from '../../i18n';
import type { CalendarOccurrence, TimeEntry } from '../../types';
import type { DaySegment } from '../../calendar/daySegments';
import { formatSegmentTimeRange } from '../../calendar/daySegments';
import type { WeekEventBlock } from '../../calendar/weekLayout';
import { layoutTimedSegments } from '../../calendar/weekLayout';
import { ghostPieces, resizeEdgeAt } from '../../calendar/weekGestures';
import { darken } from '../../calendar/calendarColors';
import type { LinkedTask } from '../../calendar/taskScheduling';
import { occurrenceColor } from '../../calendar/taskScheduling';
import { formatWeekHeader } from '../../calendar/calendarTitles';
import { MINUTES_PER_DAY, dayOfWeek, formatMinute } from '../../calendar/zonedTime';
import type { EntryMarks, EntrySegment } from '../../closing/closingBoard';
import { formatEntryRange, formatEntrySegmentRange, zonedMinuteOf } from '../../closing/closingBoard';
import type { EntryRange } from '../../closing/closingRequests';
import { entryTiming, snapMinutesFor } from '../../closing/entryGestures';
import { ENTRY_LANE_ATTRIBUTE, useClosingDrag } from './useClosingDrag';
import { entryElementId, occurrenceElementId } from './closingElementIds';

/** 時刻の列の幅（週表示と同じ）。 */
const TIME_COLUMN_WIDTH = 56;
/** 1 日の列の最小の幅（左右 2 本）。期間は最大 16 日なので、入らなければ横に送る。 */
const DAY_MIN_WIDTH = 156;
/** 開いたときに見せる時刻（8:00）。 */
const DEFAULT_SCROLL_MINUTE = 8 * 60;
const CHIP_MARGIN = 2;

/** 打刻の色（タスクのカテゴリの色。未割当は灰）。 */
const UNASSIGNED_COLOR = '#8a8f98';


interface Props {
  dates: string[];
  timeZone: string;
  nowMs: number;
  occurrenceSegmentsByDate: ReadonlyMap<string, DaySegment[]>;
  entrySegmentsByDate: ReadonlyMap<string, EntrySegment[]>;
  linkedTasks: ReadonlyMap<number, LinkedTask>;
  marks: EntryMarks;
  missedOccurrenceIds: ReadonlySet<string>;
  selectedEntryIds: ReadonlySet<number>;
  /** 一覧から飛んできた打刻・回（しばらく目立たせる） */
  focusedEntryIds: ReadonlySet<number>;
  focusedOccurrenceId: string | null;
  readOnly: boolean;
  splitMode: boolean;
  onToggleEntry: (entry: TimeEntry) => void;
  onOpenEntry: (entry: TimeEntry) => void;
  onClearSelection: () => void;
  onOccurrenceClick: (occurrence: CalendarOccurrence, anchor: HTMLElement) => void;
  onReschedule: (entryId: number, range: EntryRange) => void;
  onCreate: (range: EntryRange) => void;
  /** 分ける位置（その日の 0:00 からの分。刻みは `fine` で決める） */
  onSplitAt: (entry: TimeEntry, date: string, offsetMinute: number, fine: boolean) => void;
}

/**
 * 締めの画面の時間グリッド（task #161 / ADR-0015）。週表示と同じ 1px = 1 分の時間グリッドで、
 * 各日の列を左（予定）と右（打刻）の 2 本に分ける。期間（最大 16 日）を横に並べ、入らなければ横に送る。
 */
const ClosingGrid: React.FC<Props> = ({
  dates, timeZone, nowMs, occurrenceSegmentsByDate, entrySegmentsByDate, linkedTasks, marks, missedOccurrenceIds,
  selectedEntryIds, focusedEntryIds, focusedOccurrenceId, readOnly, splitMode,
  onToggleEntry, onOpenEntry, onClearSelection, onOccurrenceClick, onReschedule, onCreate, onSplitAt,
}) => {
  const { t, weekdays } = useI18n();
  const c = useTheme().palette.calendar;
  const scrollRef = useRef<HTMLDivElement>(null);
  const drag = useClosingDrag({
    timeZone, nowMs, scrollRef,
    onReschedule: readOnly ? null : onReschedule,
    onCreate: readOnly ? null : onCreate,
  });
  const ghost = drag.ghost;
  const [splitHover, setSplitHover] = useState<{ key: string; minute: number } | null>(null);

  const now = zonedMinuteOf(nowMs, timeZone);
  const columns = `${TIME_COLUMN_WIDTH}px repeat(${dates.length}, minmax(${DAY_MIN_WIDTH}px, 1fr))`;

  const occurrenceBlocks = useMemo(() => {
    const map = new Map<string, WeekEventBlock[]>();
    for (const d of dates) map.set(d, layoutTimedSegments(occurrenceSegmentsByDate.get(d) ?? []));
    return map;
  }, [dates, occurrenceSegmentsByDate]);

  const entryBlocks = useMemo(() => {
    const map = new Map<string, WeekEventBlock<EntrySegment>[]>();
    for (const d of dates) map.set(d, layoutTimedSegments<EntrySegment>(entrySegmentsByDate.get(d) ?? []));
    return map;
  }, [dates, entrySegmentsByDate]);

  const ghostByDate = useMemo(() => {
    const map = new Map<string, { startMinute: number; endMinute: number; first: boolean }>();
    if (ghost) ghostPieces(entryTiming(ghost.range, timeZone)).forEach((p, i) => map.set(p.date, { ...p, first: i === 0 }));
    return map;
  }, [ghost, timeZone]);

  // 期間を変えたら 8:00 へ送る（横は先頭へ）。
  const firstDate = dates[0];
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = DEFAULT_SCROLL_MINUTE;
    el.scrollLeft = 0;
  }, [firstDate]);

  const dayBackground = (date: string): string => {
    const dow = dayOfWeek(date);
    if (dow === 0) return c.sundayBg;
    if (dow === 6) return c.saturdayBg;
    return 'transparent';
  };

  const gridLines = {
    backgroundImage: `linear-gradient(to bottom, ${c.gridLine} 1px, transparent 1px),`
      + ` linear-gradient(to bottom, transparent 30px, ${c.gridHalfLine} 30px, ${c.gridHalfLine} 31px, transparent 31px)`,
    backgroundSize: '100% 60px',
  };

  const chipText = { color: c.onColor, fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } as const;

  const edgeOf = (e: React.PointerEvent<HTMLElement>, segment: EntrySegment): 'top' | 'bottom' | null => {
    const rect = e.currentTarget.getBoundingClientRect();
    const edge = resizeEdgeAt(e.clientY - rect.top, rect.height);
    if (edge === 'top' && segment.continuesFromPreviousDay) return null;
    if (edge === 'bottom' && (segment.continuesToNextDay || segment.entry.is_running)) return null;
    return edge;
  };

  /** 打刻の上の位置 → その日の 0:00 からの分（打刻の列の上端から測る）。 */
  const laneMinuteOf = (e: React.MouseEvent<HTMLElement>): number => {
    const lane = e.currentTarget.closest(`[${ENTRY_LANE_ATTRIBUTE}]`);
    const top = lane ? lane.getBoundingClientRect().top : e.currentTarget.getBoundingClientRect().top;
    return e.clientY - top;
  };

  const entryColor = (entry: TimeEntry): string =>
    entry.task_id != null && !marks.unassigned.has(entry.id)
      ? linkedTasks.get(entry.task_id)?.color ?? c.blue
      : UNASSIGNED_COLOR;

  const renderOccurrence = (block: WeekEventBlock) => {
    const segment = block.segment;
    const o = segment.occurrence;
    const bg = occurrenceColor(o, linkedTasks);
    const missed = missedOccurrenceIds.has(o.id);
    const focused = focusedOccurrenceId === o.id;
    const first = !segment.continuesFromPreviousDay;
    return (
      <Box
        key={segment.key}
        id={first ? occurrenceElementId(o.id) : undefined}
        data-occurrence-id={o.id}
        role="button"
        tabIndex={0}
        title={`${o.title}\n${formatSegmentTimeRange(segment)}${missed ? `\n${t('closing.missedMark')}` : ''}`}
        onClick={(e) => { e.stopPropagation(); onOccurrenceClick(o, e.currentTarget); }}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOccurrenceClick(o, e.currentTarget); } }}
        sx={{
          position: 'absolute', zIndex: 1, boxSizing: 'border-box', overflow: 'hidden',
          top: block.top, height: block.height,
          left: `calc(${block.leftRatio * 100}% + ${CHIP_MARGIN}px)`,
          width: `calc(${block.widthRatio * 100}% - ${CHIP_MARGIN * 2}px)`,
          px: '3px', borderRadius: '2px', cursor: 'pointer',
          // 予定は「下敷き」なので薄く。打刻の無い予定は赤い破線
          bgcolor: bg, opacity: missed ? 0.9 : 0.55,
          border: missed ? `2px dashed ${c.red}` : `1px solid ${darken(bg)}`,
          boxShadow: focused ? `0 0 0 3px ${c.blue}` : 'none',
          display: 'flex', flexDirection: 'column',
        }}
      >
        <Box sx={{ ...chipText }}>{o.title}</Box>
        {block.height >= 30 && <Box sx={{ ...chipText, fontSize: 9 }}>{formatSegmentTimeRange(segment)}</Box>}
      </Box>
    );
  };

  const renderEntry = (block: WeekEventBlock<EntrySegment>) => {
    const segment = block.segment;
    const entry = segment.entry;
    const bg = entryColor(entry);
    const selected = selectedEntryIds.has(entry.id);
    const focused = focusedEntryIds.has(entry.id);
    const unassigned = marks.unassigned.has(entry.id);
    const longRunning = marks.longRunning.has(entry.id);
    const overlapping = marks.overlapping.has(entry.id);
    const dragging = ghost != null && ghost.entryId === entry.id;
    const first = !segment.continuesFromPreviousDay;
    const label = entry.task_title ?? t('closing.unassigned');
    const range = formatEntrySegmentRange(segment);
    const border = longRunning ? `2px solid ${c.red}` : overlapping ? '2px solid #e8710a' : `1px solid ${darken(bg)}`;
    const hover = splitMode && splitHover?.key === segment.key ? splitHover : null;
    return (
      <Box
        key={segment.key}
        id={first ? entryElementId(entry.id) : undefined}
        data-entry-id={entry.id}
        role="button"
        tabIndex={0}
        aria-pressed={selected}
        title={[
          label, formatEntryRange({ startMs: Date.parse(entry.started_at), endMs: entry.ended_at ? Date.parse(entry.ended_at) : nowMs }, timeZone),
          entry.memo ?? '', longRunning ? t('closing.findingLongRunning') : '', overlapping ? t('closing.findingOverlap') : '',
          entry.is_running ? t('closing.running') : '',
        ].filter(Boolean).join('\n')}
        onPointerDown={readOnly || splitMode ? undefined : (e) => { e.stopPropagation(); drag.onEntryPointerDown(e, block, edgeOf(e, segment)); }}
        onPointerMove={(e) => {
          if (splitMode) {
            const step = snapMinutesFor(e.shiftKey);
            setSplitHover({ key: segment.key, minute: Math.round(laneMinuteOf(e) / step) * step });
            return;
          }
          if (readOnly || ghost || entry.is_running) return;
          e.currentTarget.style.cursor = edgeOf(e, segment) ? 'ns-resize' : 'move';
        }}
        onPointerLeave={() => { if (splitMode) setSplitHover(null); }}
        onClick={(e) => {
          e.stopPropagation();
          if (drag.shouldSuppressClick()) return;
          if (splitMode && !readOnly) {
            onSplitAt(entry, segment.date, laneMinuteOf(e), e.shiftKey);
            return;
          }
          onToggleEntry(entry);
        }}
        onDoubleClick={readOnly ? undefined : (e) => { e.stopPropagation(); onOpenEntry(entry); }}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggleEntry(entry); } }}
        sx={{
          position: 'absolute', zIndex: selected ? 2 : 1, boxSizing: 'border-box', overflow: 'hidden',
          top: block.top, height: block.height,
          left: `calc(${block.leftRatio * 100}% + ${CHIP_MARGIN}px)`,
          width: `calc(${block.widthRatio * 100}% - ${CHIP_MARGIN * 2}px)`,
          px: '3px', borderRadius: '3px', cursor: splitMode ? 'crosshair' : 'pointer', touchAction: readOnly ? 'auto' : 'none',
          bgcolor: bg, opacity: dragging ? 0.45 : 1,
          // 未割当は斜線（確定の前に振るか消す）
          backgroundImage: unassigned
            ? 'repeating-linear-gradient(135deg, rgba(255,255,255,0.28) 0 6px, transparent 6px 12px)'
            : entry.is_running ? 'repeating-linear-gradient(90deg, rgba(255,255,255,0.18) 0 4px, transparent 4px 8px)' : 'none',
          border,
          outline: selected ? `3px solid ${c.blue}` : focused ? `3px dashed ${c.blue}` : 'none',
          outlineOffset: '1px',
          display: 'flex', flexDirection: 'column', justifyContent: block.height < 26 ? 'center' : 'flex-start',
        }}
      >
        <Box sx={{ ...chipText, fontWeight: 600 }}>{longRunning ? '⚠ ' : ''}{label}</Box>
        {block.height >= 26 && <Box sx={{ ...chipText, fontSize: 9 }}>{range}</Box>}
        {hover && (
          <Box sx={{
            position: 'absolute', left: 0, right: 0, top: hover.minute - block.top, height: 0,
            borderTop: `2px dashed ${c.onColor}`, pointerEvents: 'none',
          }} />
        )}
      </Box>
    );
  };

  return (
    <Box
      ref={scrollRef}
      data-testid="closing-scroll"
      sx={{ height: '100%', minHeight: 0, overflow: 'auto', bgcolor: c.surface, position: 'relative' }}
    >
      <Box sx={{ display: 'grid', gridTemplateColumns: columns, width: 'max-content', minWidth: '100%' }}>
        {/* 見出し（上に貼り付く） */}
        <Box sx={{ position: 'sticky', top: 0, left: 0, zIndex: 6, bgcolor: c.surface, borderBottom: `1px solid ${c.gridLine}` }} />
        {dates.map((date) => (
          <Box
            key={date}
            sx={{
              position: 'sticky', top: 0, zIndex: 5, bgcolor: c.surface, borderLeft: `1px solid ${c.gridLine}`,
              borderBottom: `1px solid ${c.gridLine}`, textAlign: 'center', pt: '4px',
            }}
          >
            <Box sx={{
              fontSize: 12, fontWeight: date === now.date ? 700 : 500,
              color: date === now.date ? c.blue : dayOfWeek(date) === 0 ? c.holidayText : dayOfWeek(date) === 6 ? c.blue : c.weekHeaderText,
            }}>
              {formatWeekHeader(date, t, weekdays)}
            </Box>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', fontSize: 10, color: c.textSecondary, pb: '2px' }}>
              <Box>{t('closing.laneSchedule')}</Box>
              <Box>{t('closing.laneEntries')}</Box>
            </Box>
          </Box>
        ))}

        {/* 時刻の列（左に貼り付く） */}
        <Box sx={{ position: 'sticky', left: 0, zIndex: 4, bgcolor: c.surface, height: MINUTES_PER_DAY }}>
          {Array.from({ length: 24 }, (_, h) => (
            <Box key={h} sx={{ height: 60, fontSize: 10, lineHeight: 1, pl: '4px', color: c.textSecondary }}>
              {formatMinute(h * 60)}
            </Box>
          ))}
        </Box>

        {dates.map((date) => (
          <Box
            key={date}
            data-date={date}
            sx={{
              display: 'grid', gridTemplateColumns: '1fr 1fr', height: MINUTES_PER_DAY, position: 'relative',
              borderLeft: `1px solid ${c.gridLine}`, bgcolor: dayBackground(date),
            }}
          >
            {/* 左: 予定（読むだけ。押すと「予定どおり」） */}
            <Box sx={{ position: 'relative', minWidth: 0, ...gridLines, borderRight: `1px dashed ${c.gridLine}` }}>
              {(occurrenceBlocks.get(date) ?? []).map(renderOccurrence)}
            </Box>
            {/* 右: 打刻（動かす・伸ばす・空き時間を引いて足す） */}
            <Box
              data-entry-lane={date}
              data-testid={`entry-lane-${date}`}
              onPointerDown={readOnly ? undefined : (e) => {
                if (e.target instanceof Element && e.target.closest('[data-entry-id]')) return;
                drag.onLanePointerDown(e);
              }}
              onClick={() => { if (!drag.shouldSuppressClick()) onClearSelection(); }}
              sx={{
                position: 'relative', minWidth: 0, ...gridLines,
                touchAction: 'pan-x pan-y', userSelect: 'none', WebkitUserSelect: 'none', WebkitTouchCallout: 'none',
                cursor: readOnly ? 'default' : 'crosshair',
              }}
            >
              {(entryBlocks.get(date) ?? []).map(renderEntry)}
              {ghost && (() => {
                const piece = ghostByDate.get(date);
                if (!piece) return null;
                const fullWidth = ghost.kind === 'create';
                return (
                  <Box
                    data-testid={piece.first ? 'closing-drag-ghost' : undefined}
                    sx={{
                      position: 'absolute', zIndex: 4, pointerEvents: 'none', boxSizing: 'border-box',
                      top: piece.startMinute, height: Math.max(piece.endMinute - piece.startMinute, 4),
                      left: fullWidth ? 0 : `calc(${ghost.leftRatio * 100}% + ${CHIP_MARGIN}px)`,
                      width: fullWidth ? '100%' : `max(24px, calc(${ghost.widthRatio * 100}% - ${CHIP_MARGIN * 2}px))`,
                      bgcolor: c.dragGhost, borderRadius: '4px', borderTop: piece.first ? `2px solid ${c.blue}` : 'none',
                      px: '4px', pt: '2px', color: c.onColor, fontSize: 10, whiteSpace: 'nowrap', overflow: 'hidden',
                    }}
                  >
                    {piece.first ? formatEntryRange(ghost.range, timeZone) : null}
                  </Box>
                );
              })()}
            </Box>
            {/* 今の時刻の線 */}
            {date === now.date && (
              <Box sx={{
                position: 'absolute', left: 0, right: 0, top: now.minute - 1, height: 2, zIndex: 3,
                bgcolor: c.currentTimeLine, pointerEvents: 'none',
              }} />
            )}
          </Box>
        ))}
      </Box>
    </Box>
  );
};

export default ClosingGrid;
