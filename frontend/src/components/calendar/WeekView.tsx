import React, { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { Box, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import RepeatIcon from '@mui/icons-material/Repeat';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import { useI18n } from '../../i18n';
import type { CalendarHoliday, CalendarOccurrence } from '../../types';
import type { DaySegment } from '../../calendar/daySegments';
import { formatSegmentTimeRange } from '../../calendar/daySegments';
import {
  ALL_DAY_CHIP_HEIGHT, ALL_DAY_ROW_HEIGHT, MINIMUM_BAND_HEIGHT, defaultScrollTop, layoutAllDayLane, layoutTimedSegments,
  pastShadeHeight,
} from '../../calendar/weekLayout';
import type { DayBand, WeekEventBlock } from '../../calendar/weekLayout';
import { holidaysByDate, isNamedDayOff } from '../../calendar/monthCells';
import { darken, dayColumnBackground, pastEventColor, occurrencePattern } from '../../calendar/calendarColors';
import type { LinkedTask } from '../../calendar/taskScheduling';
import { linkedTaskLabel, occurrenceColor } from '../../calendar/taskScheduling';
import { formatWeekHeader } from '../../calendar/calendarTitles';
import { dayOfWeek, MINUTES_PER_DAY } from '../../calendar/zonedTime';
import { formatTimingRange, ghostPieces, resizeEdgeAt, tapCreateMinute } from '../../calendar/weekGestures';
import type { CalendarInteractions, TaskDropPreview } from './calendarInteractions';
import { useWeekDrag } from './useWeekDrag';
import DeadlineChip from './DeadlineChip';
import DoneMark from './DoneMark';
import HourLabels from './HourLabels';
import type { CalendarDeadline } from '../../calendar/taskDeadlines';

// 時刻の列の幅（移植元 WeekCalendarView.xaml の ColumnDefinition 56）。
export const TIME_COLUMN_WIDTH = 56;
// 予定の左の余白と、列幅に対する最大の幅（移植元 ChipMarginLeft・0.8）。
const CHIP_MARGIN_LEFT = 4;
const CHIP_MAX_WIDTH_RATIO = 0.8;
// 狭い画面で何日も並べるとき（列が 50px ほど）は、右の 2 割を空けると題名が 1 文字しか入らない。
// 列いっぱいに描き、題名は折り返す（打刻の帯を重ねる日だけは帯の場所を空けたまま）。
const NARROW_CHIP_MARGIN = 2;
const NARROW_TITLE_LINE = 12;
// 予定と並べて重ねる帯（打刻）の幅と右の余白。予定のブロックが空けている右の 2 割に置く。
const BAND_WIDTH = 10;
const BAND_MARGIN_RIGHT = 3;
// 見出し・終日の帯にも、時間グリッドの縦のスクロールバーと同じ幅の溝を取る。取らないと、スクロールバーが
// 幅を取る環境（Windows の Chrome・Edge など）で、見出しと終日の列だけがスクロールバーの幅だけ広くなり、
// 右へ行くほど日の列が本体とずれる。スクロールバーが重なって出る環境（スマホ・macOS）では溝は 0。
const SCROLLBAR_GUTTER = { overflowY: 'hidden', scrollbarGutter: 'stable' } as const;
// 終日の帯と時間グリッドの境の線の太さ。正時の線（1px）より太くして、帯の終わりを見分けられるようにする。
const ALL_DAY_DIVIDER = 2;

interface Props extends Pick<
  CalendarInteractions,
  'onCreateRange' | 'onRescheduleOccurrence' | 'onEditOccurrence' | 'onCreateEvent' | 'onToggleDone' | 'onOpenDeadline'
> {
  dates: string[];
  timeZone: string;
  segmentsByDate: ReadonlyMap<string, DaySegment[]>;
  holidays: readonly CalendarHoliday[];
  deadlines: readonly CalendarDeadline[];
  today: string;
  nowMinute: number;
  selectedDate: string | null;
  selectedSegmentKey: string | null;
  /** 見出しの日付を押した（日の一覧を開く・閉じる。ほかの場所を押しても呼ばない。ADR-0034） */
  onSelectDate: (date: string) => void;
  /** 予定・タスクのブロックを押した（カレンダーと「今日」は編集を開く） */
  onSelectSegment: (segment: DaySegment) => void;
  /** 予定に結んだタスクの印（色・題名） */
  linkedTasks?: ReadonlyMap<number, LinkedTask>;
  /** タスクの一覧から引いている途中の行き先 */
  dropPreview?: TaskDropPreview | null;
  /** 日ごとに、予定と並べて重ねる帯（「今日」の画面の打刻。task #160） */
  bands?: ReadonlyMap<string, readonly DayBand[]>;
  /** 予定のブロックの題名の横に置く操作（「今日」の画面の Start。押してもブロックの選択にはしない） */
  occurrenceAction?: (occurrence: CalendarOccurrence) => React.ReactNode;
  /** 今日を含むとき、開いた位置を今の何分前にするか（既定は 4 時間前） */
  scrollLeadMinutes?: number;
  /** 曜日の休み（営業日の層が表示のとき。ADR-0029）。null・省略は土日の色だけ */
  nonWorkdays?: ReadonlySet<string> | null;
}

/**
 * 週表示・平日表示（移植元 WeekCalendarView）。左に時刻の列、上に終日の帯、下に 1px = 1 分の時間グリッド。
 */
const WeekView: React.FC<Props> = ({
  dates, timeZone, segmentsByDate, holidays, deadlines, today, nowMinute, selectedDate, selectedSegmentKey,
  onSelectDate, onSelectSegment, onCreateRange, onRescheduleOccurrence, onEditOccurrence, onCreateEvent, onToggleDone,
  onOpenDeadline, linkedTasks, dropPreview, bands, occurrenceAction, scrollLeadMinutes, nonWorkdays,
}) => {
  const { t, weekdays } = useI18n();
  const theme = useTheme();
  const c = theme.palette.calendar;
  // 狭い画面で何日も並べるときは、見出しを曜日と日付の 2 行にする（1 行だと列の幅に収まらず、今日の太字が枠で切れる）
  const stackHeader = useMediaQuery(theme.breakpoints.down('sm')) && dates.length > 1;
  const narrowColumns = stackHeader;
  const scrollRef = useRef<HTMLDivElement>(null);
  const columns = `${TIME_COLUMN_WIDTH}px repeat(${dates.length}, minmax(0, 1fr))`;
  const isCurrentWeek = dates.includes(today);
  const holidayMap = useMemo(() => holidaysByDate(holidays), [holidays]);
  const drag = useWeekDrag({ dates, timeZone, scrollRef, onCreateRange, onRescheduleOccurrence });
  const ghost = drag.ghost;
  const ghostByDate = useMemo(() => {
    const map = new Map<string, { startMinute: number; endMinute: number; first: boolean }>();
    if (ghost) ghostPieces(ghost.timing).forEach((p, i) => map.set(p.date, { ...p, first: i === 0 }));
    return map;
  }, [ghost]);
  const dropByDate = useMemo(() => {
    const map = new Map<string, { startMinute: number; endMinute: number; first: boolean }>();
    if (dropPreview) ghostPieces(dropPreview).forEach((p, i) => map.set(p.date, { ...p, first: i === 0 }));
    return map;
  }, [dropPreview]);

  const allDay = useMemo(() => {
    const segments = dates.flatMap((d) => segmentsByDate.get(d) ?? []);
    return layoutAllDayLane(segments, dates[0], dates.length, holidays, deadlines);
  }, [dates, segmentsByDate, holidays, deadlines]);

  const blocksByDate = useMemo(() => {
    const map = new Map<string, WeekEventBlock[]>();
    for (const d of dates) map.set(d, layoutTimedSegments(segmentsByDate.get(d) ?? []));
    return map;
  }, [dates, segmentsByDate]);

  // 週を変えたら送る（今週なら今の 4 時間前、それ以外は 9:00）。時計の進みでは動かさない。
  const nowRef = useRef(nowMinute);
  useEffect(() => { nowRef.current = nowMinute; }, [nowMinute]);
  const firstDate = dates[0];
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = defaultScrollTop(isCurrentWeek, nowRef.current, scrollLeadMinutes);
  }, [firstDate, dates.length, isCurrentWeek, scrollLeadMinutes]);

  const dayBackground = (date: string): string => {
    return dayColumnBackground(c, dayOfWeek(date), holidayMap.get(date), nonWorkdays ? nonWorkdays.has(date) : null);
  };

  const headerColor = (date: string): string => {
    if (date === today) return c.blue;
    const dow = dayOfWeek(date);
    if (dow === 0 || isNamedDayOff(holidayMap.get(date))) return c.holidayText;
    if (dow === 6) return c.blue;
    return c.weekHeaderText;
  };

  // 日の境の縦線。今日の列は青い枠（上は見出し、中は終日の帯、下は時間グリッドで閉じる）。
  const divider = (date: string, part: 'top' | 'middle' | 'bottom') => {
    if (date !== today) {
      // 見出しは今日の列だけ上に 2px の枠が付く。ほかの列にも同じ厚みの透明な枠を置いて、文字の高さを揃える。
      return { borderLeft: `1px solid ${c.gridLine}`, ...(part === 'top' ? { borderTop: '2px solid transparent' } : {}) };
    }
    const blue = `2px solid ${c.blue}`;
    return {
      borderLeft: blue,
      borderRight: blue,
      ...(part === 'top' ? { borderTop: blue, borderRadius: '6px 6px 0 0' } : {}),
      ...(part === 'bottom' ? { borderBottom: blue, borderRadius: '0 0 6px 6px' } : {}),
    };
  };

  // 上端・下端のつかみ。日をまたいで続く側の端（前日から・翌日へ）は伸ばせないので移動にする。
  const edgeOf = (e: React.PointerEvent<HTMLElement>, segment: DaySegment): 'top' | 'bottom' | null => {
    const rect = e.currentTarget.getBoundingClientRect();
    const edge = resizeEdgeAt(e.clientY - rect.top, rect.height);
    if (edge === 'top' && segment.continuesFromPreviousDay) return null;
    if (edge === 'bottom' && segment.continuesToNextDay) return null;
    return edge;
  };

  // 空き枠のタップは作成の意図（:00 / :30 に丸める。移植元 OnLaneTapped）。日の一覧は開かない（ADR-0034）。
  const onGridClick = (e: React.MouseEvent<HTMLElement>, date: string) => {
    if (drag.shouldSuppressClick()) return;
    if (onCreateEvent) onCreateEvent(date, tapCreateMinute(e.clientY - e.currentTarget.getBoundingClientRect().top));
  };

  const chipText = { color: c.onColor, fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } as const;
  // 済みのタスクの回は薄く・取り消し線（ADR-0025）
  const doneText = (o: CalendarOccurrence) => (o.is_done ? { textDecoration: 'line-through' } : {});
  const DONE_OPACITY = 0.55;

  // タスクの分類の回の印。押すと済みを切り替える（ドラッグの直後の click は既存の判定で捨てる）。
  const doneMark = (o: CalendarOccurrence, sx?: object) => {
    if (o.event_type !== 'TASK') return null;
    return (
      <DoneMark
        done={o.is_done}
        color={c.onColor}
        onToggle={onToggleDone ? () => { if (!drag.shouldSuppressClick()) onToggleDone(o); } : undefined}
        sx={sx}
      />
    );
  };

  // 繰り返し・振替の印は題名と同じ白（移植元も White）。`overlay` は時間の予定の右下に重ねる（移植元 WeekCalendarView の
  // HorizontalAlignment Right・VerticalAlignment Bottom）。題名の横に並べると題名の幅を食う。
  // 狭い列は題名を折り返すので、右下に重ねると最後の行の字に被る。`float` で 1 行目の右に置き、題名を回り込ませる。
  const occurrenceMark = (segment: DaySegment, place: 'inline' | 'overlay' | 'float' = 'inline') => {
    const o = segment.occurrence;
    const sx = {
      fontSize: 10, flexShrink: 0, color: c.onColor,
      ...(place === 'overlay' ? { position: 'absolute', right: '1px', bottom: '1px', pointerEvents: 'none' } : {}),
      ...(place === 'float' ? { float: 'right', mt: '1px' } : {}),
    } as const;
    if (o.is_moved || o.is_overridden) {
      return <SwapHorizIcon titleAccess={t(o.is_moved ? 'calendar.badgeMoved' : 'calendar.badgeModified')} sx={sx} />;
    }
    if (o.is_recurring) return <RepeatIcon titleAccess={t('calendar.recurring')} sx={sx} />;
    return null;
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, bgcolor: c.surface }}>
      {/* 曜日と日付 */}
      <Box sx={{ display: 'grid', gridTemplateColumns: columns, pt: '2px', flexShrink: 0, ...SCROLLBAR_GUTTER }}>
        <Box />
        {dates.map((date) => (
          <Box
            key={date}
            role="button"
            tabIndex={0}
            data-date={date}
            data-day-select=""
            aria-pressed={date === selectedDate}
            onClick={() => onSelectDate(date)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectDate(date); } }}
            sx={{
              textAlign: 'center', fontSize: 11, lineHeight: 1.3, pt: '2px', pb: '6px', cursor: 'pointer',
              whiteSpace: 'pre-line',
              color: headerColor(date), fontWeight: date === today || date === selectedDate ? 700 : 400,
              textDecoration: date === selectedDate ? 'underline' : 'none',
              ...divider(date, 'top'),
            }}
          >
            {stackHeader ? formatWeekHeader(date, t, weekdays).replace(' ', '\n') : formatWeekHeader(date, t, weekdays)}
          </Box>
        ))}
      </Box>

      {/* 終日の帯（祝日は 0 段目）。下に時間グリッドとの境の線（正時の線より太い 2px。カレンダー・「今日」で同じ部品） */}
      <Box
        data-testid="all-day-lane"
        sx={{
          display: 'grid', gridTemplateColumns: columns, height: allDay.height, flexShrink: 0, ...SCROLLBAR_GUTTER,
          borderBottom: `${ALL_DAY_DIVIDER}px solid ${c.gridLine}`,
        }}
      >
        <Box sx={{ fontSize: 10, alignSelf: 'center', mx: '2px', color: c.textSecondary }}>{t('calendar.allDay')}</Box>
        {dates.map((date, i) => {
          const blocks = allDay.blocks.filter((b) => b.column === i);
          const hasEvents = blocks.some((b) => b.segment != null);
          return (
            <Box
              key={date}
              sx={{ position: 'relative', minWidth: 0, bgcolor: hasEvents ? c.allDayTint : 'transparent', ...divider(date, 'middle') }}
            >
              {blocks.map((b) => {
                if (b.deadline) {
                  const deadline = b.deadline;
                  return (
                    <Box
                      key={b.deadline.key}
                      sx={{ position: 'absolute', top: b.row * ALL_DAY_ROW_HEIGHT + 1, left: 0, right: '4px' }}
                    >
                      <DeadlineChip
                        deadline={b.deadline}
                        height={ALL_DAY_CHIP_HEIGHT}
                        fontSize={10}
                        // タスク・マイルストーンを開く（日の一覧は開かない。ADR-0034）
                        onClick={onOpenDeadline ? (e) => { e.stopPropagation(); onOpenDeadline(deadline); } : undefined}
                      />
                    </Box>
                  );
                }
                const segment = b.segment;
                if (!segment && b.holiday?.subtle) {
                  // 曜日の休み: 地の色の上に、層の色の細い線と控えめな文字だけ（ほかの休みの帯より目立たせない）
                  return (
                    <Box
                      key={`weekly@${b.holiday.date}`}
                      title={b.holiday.name ?? ''}
                      sx={{
                        position: 'absolute', zIndex: 1, top: b.row * ALL_DAY_ROW_HEIGHT + 1, left: 0, right: '4px',
                        height: ALL_DAY_CHIP_HEIGHT, px: '4px', boxSizing: 'border-box',
                        display: 'flex', alignItems: 'center', pointerEvents: 'none',
                        borderLeft: `3px solid ${b.holiday.color ?? c.textSecondary}`,
                        color: c.textSecondary, fontSize: 10,
                      }}
                    >
                      <Box sx={{ ...chipText, flex: 1, color: 'inherit' }}>{b.holiday.name}</Box>
                    </Box>
                  );
                }
                const color = segment ? occurrenceColor(segment.occurrence, linkedTasks) : b.holiday?.color ?? c.red;
                // 過ぎた日の予定は影の上に描き、地だけ沈める（文字は白のまま読める）
                const bg = date < today ? pastEventColor(color, c) : color;
                const title = segment ? segment.occurrence.title : b.holiday?.name ?? '';
                const selected = segment != null && segment.key === selectedSegmentKey;
                return (
                  <Box
                    key={segment?.key ?? `holiday@${b.holiday?.date}`}
                    title={title}
                    onClick={segment ? (e) => { e.stopPropagation(); onSelectSegment(segment); } : undefined}
                    onDoubleClick={segment && onEditOccurrence ? (e) => { e.stopPropagation(); onEditOccurrence(segment.occurrence); } : undefined}
                    sx={{
                      position: 'absolute', zIndex: 1, top: b.row * ALL_DAY_ROW_HEIGHT + 1, left: 0, right: '4px',
                      height: ALL_DAY_CHIP_HEIGHT, px: '6px', py: '2px', borderRadius: '2px', boxSizing: 'border-box',
                      display: 'flex', alignItems: 'center', gap: '2px',
                      bgcolor: bg, opacity: segment ? (segment.occurrence.is_done ? DONE_OPACITY : 0.82) : 0.7,
                      backgroundImage: segment ? occurrencePattern(segment.occurrence) : 'none',
                      border: selected ? `2px solid ${c.onColor}` : `1px solid ${darken(bg)}`,
                      cursor: segment ? 'pointer' : 'default', pointerEvents: segment ? 'auto' : 'none',
                    }}
                  >
                    {segment && doneMark(segment.occurrence)}
                    <Box sx={{ ...chipText, flex: 1, ...(segment ? doneText(segment.occurrence) : {}) }}>{title}</Box>
                    {segment && occurrenceMark(segment)}
                  </Box>
                );
              })}
              {date < today && (
                <Box sx={{ position: 'absolute', inset: 0, zIndex: 0, bgcolor: c.pastShade, pointerEvents: 'none' }} />
              )}
            </Box>
          );
        })}
      </Box>

      {/* 時間グリッド（1px = 1 分） */}
      <Box ref={scrollRef} data-testid="week-scroll" sx={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', scrollbarGutter: 'stable' }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: columns, height: MINUTES_PER_DAY }}>
          <Box sx={{ position: 'relative' }}>
            <HourLabels color={c.textSecondary} paddingLeft={2} />
          </Box>
          {dates.map((date) => (
            <Box
              key={date}
              data-date={date}
              data-day-column={date}
              onPointerDown={onCreateRange ? (e) => {
                // 予定の上で押したら作らない（移植元 IsWithinEventChip）。
                if (e.target instanceof Element && e.target.closest('[data-occurrence-id]')) return;
                drag.onGridPointerDown(e);
              } : undefined}
              onClick={(e) => onGridClick(e, date)}
              sx={{
                position: 'relative', minWidth: 0, height: MINUTES_PER_DAY, boxSizing: 'border-box',
                // 指: 縦のスクロールは許す（範囲作りは長押しから）。長押しの選択・吹き出しは出さない。
                touchAction: 'pan-y', userSelect: 'none', WebkitUserSelect: 'none', WebkitTouchCallout: 'none',
                bgcolor: dayBackground(date),
                // 正時の線と 30 分の線
                backgroundImage: `linear-gradient(to bottom, ${c.gridLine} 1px, transparent 1px),`
                  + ` linear-gradient(to bottom, transparent 30px, ${c.gridHalfLine} 30px, ${c.gridHalfLine} 31px, transparent 31px)`,
                backgroundSize: '100% 60px',
                ...divider(date, 'bottom'),
              }}
            >
              {(blocksByDate.get(date) ?? []).map((block) => {
                // 狭い列では列いっぱい（打刻の帯を重ねる日は帯の場所を空ける）
                const fill = narrowColumns && !(bands?.get(date)?.length);
                const chipLeft = fill ? NARROW_CHIP_MARGIN : CHIP_MARGIN_LEFT;
                const chipWidthRatio = fill ? block.widthRatio : Math.min(block.widthRatio, CHIP_MAX_WIDTH_RATIO);
                const chipRightGap = fill ? NARROW_CHIP_MARGIN * 2 : CHIP_MARGIN_LEFT;
                const segment = block.segment;
                const o = segment.occurrence;
                // 終わった予定は影の上に描き、地だけ沈める（文字は白のまま読める）
                const ended = date < today || (date === today && segment.endMinute <= nowMinute);
                const bg = ended ? pastEventColor(occurrenceColor(o, linkedTasks), c) : occurrenceColor(o, linkedTasks);
                const selected = segment.key === selectedSegmentKey;
                const range = formatSegmentTimeRange(segment);
                const taskLabel = linkedTaskLabel(o, linkedTasks);
                const dragging = ghost != null && ghost.occurrenceId === o.id;
                // 取り込んだ予定（ADR-0037）は読み取り専用。動かさない（押せば中身だけを見せる）
                const movable = onRescheduleOccurrence != null && !o.is_imported;
                return (
                  <Box
                    key={segment.key}
                    data-occurrence-id={o.id}
                    title={`${o.title}\n${range}${taskLabel ? `\n${t('calendar.linkedTask', { title: taskLabel })}` : ''}${o.location ? `\n${o.location}` : ''}`}
                    onPointerDown={movable ? (e) => { e.stopPropagation(); drag.onEventPointerDown(e, block, edgeOf(e, segment)); } : undefined}
                    onPointerMove={movable ? (e) => {
                      // 端は上下の矢印、ほかは移動の矢印（移植元 OnChipPointerMoved）。ドラッグ中は変えない。
                      if (ghost) return;
                      e.currentTarget.style.cursor = edgeOf(e, segment) ? 'ns-resize' : 'move';
                    } : undefined}
                    onClick={(e) => { e.stopPropagation(); if (!drag.shouldSuppressClick()) onSelectSegment(segment); }}
                    onDoubleClick={onEditOccurrence ? (e) => { e.stopPropagation(); onEditOccurrence(o); } : undefined}
                    sx={{
                      position: 'absolute', zIndex: 1, boxSizing: 'border-box', overflow: 'hidden',
                      top: block.top, height: block.height,
                      left: `calc(${block.leftRatio * 100}% + ${chipLeft}px)`,
                      width: `calc(${chipWidthRatio * 100}% - ${chipRightGap}px)`,
                      px: fill ? '2px' : '4px', borderRadius: '2px', bgcolor: bg, cursor: 'pointer', touchAction: 'none',
                      backgroundImage: occurrencePattern(o),
                      opacity: dragging ? 0.5 : o.is_done ? DONE_OPACITY : 1,
                      border: selected ? `2px solid ${c.onColor}` : `1px solid ${darken(bg)}`,
                      boxShadow: selected ? `0 0 0 1px ${c.blue}` : 'none',
                      display: 'flex', flexDirection: 'column', justifyContent: block.height < 30 ? 'center' : 'flex-start',
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: fill ? 'flex-start' : 'center', gap: '2px', minWidth: 0 }}>
                      {!fill && doneMark(o)}
                      <Box sx={fill
                        ? {
                          ...chipText, flex: 1, whiteSpace: 'normal', wordBreak: 'break-all', lineHeight: `${NARROW_TITLE_LINE}px`,
                          display: '-webkit-box', WebkitBoxOrient: 'vertical',
                          WebkitLineClamp: Math.max(1, Math.floor((block.height - 2) / NARROW_TITLE_LINE)),
                          ...doneText(o),
                        }
                        : { ...chipText, flex: 1, ...doneText(o) }}
                      >
                        {/* 重なって列を分けた細いチップ（1 字幅）は題名を優先する */}
                        {fill && block.widthRatio > 0.99 && o.event_type !== 'TASK' && occurrenceMark(segment, 'float')}
                        {/* 狭い列は題名を印に回り込ませる（印に 1 列を取られると題名が 1 字幅になる）。繰り返しの印より済みの印を優先する */}
                        {fill && doneMark(o, { float: 'left', mt: '1px', mr: '1px' })}
                        {o.title}
                      </Box>
                      {occurrenceAction?.(o)}
                    </Box>
                    {!fill && occurrenceMark(segment, 'overlay')}
                    {/* 狭い列は題名を折り返して使い切る（時刻は目盛りで分かる。全部は title の吹き出しに出る） */}
                    {!fill && taskLabel && block.height >= 32 && (
                      <Box data-testid="occurrence-task" sx={{ ...chipText, fontSize: 9, fontWeight: 600 }}>
                        {t('calendar.linkedTask', { title: taskLabel })}
                      </Box>
                    )}
                    {!fill && block.height >= (taskLabel ? 46 : 32) && <Box sx={{ ...chipText, fontSize: 9, opacity: 0.9 }}>{range}</Box>}
                  </Box>
                );
              })}
              {/* ドラッグの行き先（半透明のゴースト。移植元 WeekInteractionOverlayView） */}
              {ghost && (() => {
                const piece = ghostByDate.get(date);
                if (!piece) return null;
                const fullWidth = ghost.kind === 'create';
                // 動かす途中の形は、置いたときのチップと同じ幅（狭い列は列いっぱい）
                const ghostFill = narrowColumns && !(bands?.get(date)?.length);
                const ghostLeft = ghostFill ? NARROW_CHIP_MARGIN : CHIP_MARGIN_LEFT;
                const ghostRatio = ghostFill ? ghost.widthRatio : Math.min(ghost.widthRatio, CHIP_MAX_WIDTH_RATIO);
                const ghostRightGap = ghostFill ? NARROW_CHIP_MARGIN * 2 : CHIP_MARGIN_LEFT;
                return (
                  <Box
                    data-testid={piece.first ? 'drag-ghost' : undefined}
                    sx={{
                      position: 'absolute', zIndex: 4, pointerEvents: 'none', boxSizing: 'border-box',
                      top: piece.startMinute, height: Math.max(piece.endMinute - piece.startMinute, 15),
                      left: fullWidth ? 0 : `calc(${ghost.leftRatio * 100}% + ${ghostLeft}px)`,
                      width: fullWidth ? '100%' : `max(24px, calc(${ghostRatio * 100}% - ${ghostRightGap}px))`,
                      bgcolor: c.dragGhost, borderRadius: '6px',
                      borderTop: piece.first ? `2px solid ${c.blue}` : 'none',
                      px: '6px', pt: '4px', color: c.onColor, fontSize: 10, whiteSpace: 'nowrap', overflow: 'hidden',
                    }}
                  >
                    {piece.first ? formatTimingRange(ghost.timing) : null}
                  </Box>
                );
              })()}
              {/* タスクの一覧から引いている行き先（task #159） */}
              {dropPreview && (() => {
                const piece = dropByDate.get(date);
                if (!piece) return null;
                return (
                  <Box
                    data-testid={piece.first ? 'task-drop-ghost' : undefined}
                    sx={{
                      position: 'absolute', zIndex: 4, pointerEvents: 'none', boxSizing: 'border-box',
                      top: piece.startMinute, height: Math.max(piece.endMinute - piece.startMinute, 15), left: 0, width: '100%',
                      bgcolor: c.dragGhost, borderRadius: '6px', borderTop: piece.first ? `2px solid ${c.blue}` : 'none',
                      px: '6px', pt: '4px', color: c.onColor, fontSize: 10, whiteSpace: 'nowrap', overflow: 'hidden',
                    }}
                  >
                    {piece.first ? `${formatTimingRange(dropPreview)}  ${dropPreview.title}` : null}
                  </Box>
                );
              })()}
              {/* 予定と並べて重ねる帯（打刻。task #160） */}
              {(bands?.get(date) ?? []).map((band) => (
                <Box
                  key={band.key}
                  data-testid="day-band"
                  title={band.label}
                  sx={{
                    position: 'absolute', zIndex: 3, boxSizing: 'border-box', right: BAND_MARGIN_RIGHT, width: BAND_WIDTH,
                    top: band.startMinute, height: Math.max(band.endMinute - band.startMinute, MINIMUM_BAND_HEIGHT),
                    bgcolor: band.color, borderRadius: '3px', border: `1px solid ${darken(band.color)}`,
                    boxShadow: band.running ? `0 0 0 2px ${c.surface}, 0 0 0 3px ${band.color}` : 'none',
                  }}
                />
              ))}
              {/* 過ぎた時間の影（過ぎた日は下まで、今日は今まで）。予定のチップ（zIndex 1）より下に敷く */}
              <Box sx={{
                position: 'absolute', top: 0, left: 0, right: 0, zIndex: 0, pointerEvents: 'none',
                height: pastShadeHeight(date, today, nowMinute, MINUTES_PER_DAY), bgcolor: c.pastShade,
              }} />
              {/* 現在時刻の線（今週の列すべて） */}
              {isCurrentWeek && (
                <Box
                  data-testid={date === today ? 'now-line' : undefined}
                  sx={{
                    position: 'absolute', left: 0, right: 0, top: nowMinute - 1, height: 2, zIndex: 3,
                    bgcolor: c.currentTimeLine, pointerEvents: 'none',
                  }}
                />
              )}
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
};

export default WeekView;
