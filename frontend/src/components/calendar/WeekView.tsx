import React, { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import RepeatIcon from '@mui/icons-material/Repeat';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import { useI18n } from '../../i18n';
import type { CalendarHoliday } from '../../types';
import type { DaySegment } from '../../calendar/daySegments';
import { formatSegmentTimeRange } from '../../calendar/daySegments';
import {
  ALL_DAY_CHIP_HEIGHT, ALL_DAY_ROW_HEIGHT, defaultScrollTop, layoutAllDayLane, layoutTimedSegments,
  minuteAtOffset, pastShadeHeight,
} from '../../calendar/weekLayout';
import type { WeekEventBlock } from '../../calendar/weekLayout';
import { holidaysByDate } from '../../calendar/monthCells';
import { darken, eventColor } from '../../calendar/calendarColors';
import { formatWeekHeader } from '../../calendar/calendarTitles';
import { dayOfWeek, formatMinute, MINUTES_PER_DAY } from '../../calendar/zonedTime';
import type { CalendarInteractions } from './calendarInteractions';

// 時刻の列の幅（移植元 WeekCalendarView.xaml の ColumnDefinition 56）。
export const TIME_COLUMN_WIDTH = 56;
// 予定の左の余白と、列幅に対する最大の幅（移植元 ChipMarginLeft・0.8）。
const CHIP_MARGIN_LEFT = 4;
const CHIP_MAX_WIDTH_RATIO = 0.8;
// 予定の上端・下端のつかみ（移植元 ResizeHandlePx）。
const RESIZE_HANDLE_PX = 10;

interface Props extends Pick<CalendarInteractions, 'onEventPointerDown' | 'onGridPointerDown' | 'onEditOccurrence' | 'onCreateEvent'> {
  dates: string[];
  segmentsByDate: ReadonlyMap<string, DaySegment[]>;
  holidays: readonly CalendarHoliday[];
  today: string;
  nowMinute: number;
  selectedDate: string | null;
  selectedSegmentKey: string | null;
  onSelectDate: (date: string) => void;
  onSelectSegment: (segment: DaySegment) => void;
}

/**
 * 週表示・平日表示（移植元 WeekCalendarView）。左に時刻の列、上に終日の帯、下に 1px = 1 分の時間グリッド。
 */
const WeekView: React.FC<Props> = ({
  dates, segmentsByDate, holidays, today, nowMinute, selectedDate, selectedSegmentKey,
  onSelectDate, onSelectSegment, onEventPointerDown, onGridPointerDown, onEditOccurrence, onCreateEvent,
}) => {
  const { t, weekdays } = useI18n();
  const c = useTheme().palette.calendar;
  const scrollRef = useRef<HTMLDivElement>(null);
  const columns = `${TIME_COLUMN_WIDTH}px repeat(${dates.length}, minmax(0, 1fr))`;
  const isCurrentWeek = dates.includes(today);
  const holidayMap = useMemo(() => holidaysByDate(holidays), [holidays]);

  const allDay = useMemo(() => {
    const segments = dates.flatMap((d) => segmentsByDate.get(d) ?? []);
    return layoutAllDayLane(segments, dates[0], dates.length, holidays);
  }, [dates, segmentsByDate, holidays]);

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
    if (el) el.scrollTop = defaultScrollTop(isCurrentWeek, nowRef.current);
  }, [firstDate, dates.length, isCurrentWeek]);

  const dayBackground = (date: string): string => {
    const dow = dayOfWeek(date);
    if (holidayMap.has(date) && dow !== 6) return c.holidayBg;
    if (dow === 0) return c.sundayBg;
    if (dow === 6) return c.saturdayBg;
    return 'transparent';
  };

  const headerColor = (date: string): string => {
    if (date === today) return c.blue;
    const dow = dayOfWeek(date);
    if (dow === 0 || holidayMap.has(date)) return c.holidayText;
    if (dow === 6) return c.blue;
    return c.weekHeaderText;
  };

  // 日の境の縦線。今日の列は青い枠（上は見出し、中は終日の帯、下は時間グリッドで閉じる）。
  const divider = (date: string, part: 'top' | 'middle' | 'bottom') => {
    if (date !== today) return { borderLeft: `1px solid ${c.gridLine}` };
    const blue = `2px solid ${c.blue}`;
    return {
      borderLeft: blue,
      borderRight: blue,
      ...(part === 'top' ? { borderTop: blue, borderRadius: '6px 6px 0 0' } : {}),
      ...(part === 'bottom' ? { borderBottom: blue, borderRadius: '0 0 6px 6px' } : {}),
    };
  };

  const gridPoint = (e: React.PointerEvent<HTMLElement> | React.MouseEvent<HTMLElement>, date: string) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return { date, minute: minuteAtOffset(e.clientY - rect.top) };
  };

  const edgeOf = (e: React.PointerEvent<HTMLElement>): 'top' | 'bottom' | null => {
    const rect = e.currentTarget.getBoundingClientRect();
    if (e.clientY - rect.top <= RESIZE_HANDLE_PX) return 'top';
    if (rect.bottom - e.clientY <= RESIZE_HANDLE_PX) return 'bottom';
    return null;
  };

  const chipText = { color: c.onColor, fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } as const;

  const occurrenceMark = (segment: DaySegment) => {
    const o = segment.occurrence;
    if (o.is_moved || o.is_overridden) {
      return <SwapHorizIcon titleAccess={t(o.is_moved ? 'calendar.badgeMoved' : 'calendar.badgeModified')} sx={{ fontSize: 10, flexShrink: 0 }} />;
    }
    if (o.is_recurring) return <RepeatIcon titleAccess={t('calendar.recurring')} sx={{ fontSize: 10, flexShrink: 0 }} />;
    return null;
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, bgcolor: c.surface }}>
      {/* 曜日と日付 */}
      <Box sx={{ display: 'grid', gridTemplateColumns: columns, pt: '2px', flexShrink: 0 }}>
        <Box />
        {dates.map((date) => (
          <Box
            key={date}
            role="button"
            tabIndex={0}
            data-date={date}
            onClick={() => onSelectDate(date)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectDate(date); } }}
            sx={{
              textAlign: 'center', fontSize: 11, pt: '2px', pb: '6px', cursor: 'pointer',
              color: headerColor(date), fontWeight: date === today || date === selectedDate ? 700 : 400,
              textDecoration: date === selectedDate ? 'underline' : 'none',
              ...divider(date, 'top'),
            }}
          >
            {formatWeekHeader(date, t, weekdays)}
          </Box>
        ))}
      </Box>

      {/* 終日の帯（祝日は 0 段目） */}
      <Box sx={{ display: 'grid', gridTemplateColumns: columns, height: allDay.height, flexShrink: 0 }}>
        <Box sx={{ fontSize: 10, alignSelf: 'center', mx: '2px', color: c.textSecondary }}>{t('calendar.allDay')}</Box>
        {dates.map((date, i) => {
          const blocks = allDay.blocks.filter((b) => b.column === i);
          const hasEvents = blocks.some((b) => b.segment != null);
          return (
            <Box
              key={date}
              onClick={() => onSelectDate(date)}
              sx={{ position: 'relative', minWidth: 0, bgcolor: hasEvents ? c.allDayTint : 'transparent', ...divider(date, 'middle') }}
            >
              {blocks.map((b) => {
                const segment = b.segment;
                const bg = segment ? eventColor(segment.occurrence.color_key) : c.red;
                const title = segment ? segment.occurrence.title : b.holiday?.name ?? '';
                const selected = segment != null && segment.key === selectedSegmentKey;
                return (
                  <Box
                    key={segment?.key ?? `holiday@${b.holiday?.date}`}
                    title={title}
                    onClick={segment ? (e) => { e.stopPropagation(); onSelectSegment(segment); } : undefined}
                    onDoubleClick={segment && onEditOccurrence ? (e) => { e.stopPropagation(); onEditOccurrence(segment.occurrence); } : undefined}
                    sx={{
                      position: 'absolute', top: b.row * ALL_DAY_ROW_HEIGHT + 1, left: 0, right: '4px',
                      height: ALL_DAY_CHIP_HEIGHT, px: '6px', py: '2px', borderRadius: '2px', boxSizing: 'border-box',
                      display: 'flex', alignItems: 'center', gap: '2px',
                      bgcolor: bg, opacity: segment ? 0.82 : 0.7,
                      border: selected ? `2px solid ${c.onColor}` : `1px solid ${darken(bg)}`,
                      cursor: segment ? 'pointer' : 'default', pointerEvents: segment ? 'auto' : 'none',
                    }}
                  >
                    <Box sx={{ ...chipText, flex: 1 }}>{title}</Box>
                    {segment && occurrenceMark(segment)}
                  </Box>
                );
              })}
              {date < today && (
                <Box sx={{ position: 'absolute', inset: 0, bgcolor: c.pastShade, pointerEvents: 'none' }} />
              )}
            </Box>
          );
        })}
      </Box>

      {/* 時間グリッド（1px = 1 分） */}
      <Box ref={scrollRef} data-testid="week-scroll" sx={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden' }}>
        <Box sx={{ display: 'grid', gridTemplateColumns: columns, height: MINUTES_PER_DAY }}>
          <Box>
            {Array.from({ length: 24 }, (_, h) => (
              <Box key={h} sx={{ height: 60, fontSize: 10, lineHeight: 1, pl: '2px', color: c.textSecondary }}>
                {formatMinute(h * 60)}
              </Box>
            ))}
          </Box>
          {dates.map((date) => (
            <Box
              key={date}
              data-date={date}
              onPointerDown={onGridPointerDown ? (e) => onGridPointerDown(e, gridPoint(e, date)) : undefined}
              onClick={() => onSelectDate(date)}
              onDoubleClick={onCreateEvent ? (e) => onCreateEvent(date, gridPoint(e, date).minute) : undefined}
              sx={{
                position: 'relative', minWidth: 0, height: MINUTES_PER_DAY, boxSizing: 'border-box',
                bgcolor: dayBackground(date),
                // 正時の線と 30 分の線
                backgroundImage: `linear-gradient(to bottom, ${c.gridLine} 1px, transparent 1px),`
                  + ` linear-gradient(to bottom, transparent 30px, ${c.gridHalfLine} 30px, ${c.gridHalfLine} 31px, transparent 31px)`,
                backgroundSize: '100% 60px',
                ...divider(date, 'bottom'),
              }}
            >
              {(blocksByDate.get(date) ?? []).map((block) => {
                const segment = block.segment;
                const o = segment.occurrence;
                const bg = eventColor(o.color_key);
                const selected = segment.key === selectedSegmentKey;
                const range = formatSegmentTimeRange(segment);
                return (
                  <Box
                    key={segment.key}
                    data-occurrence-id={o.id}
                    title={`${o.title}\n${range}${o.location ? `\n${o.location}` : ''}`}
                    onPointerDown={onEventPointerDown ? (e) => { e.stopPropagation(); onEventPointerDown(e, segment, edgeOf(e)); } : undefined}
                    onClick={(e) => { e.stopPropagation(); onSelectSegment(segment); }}
                    onDoubleClick={onEditOccurrence ? (e) => { e.stopPropagation(); onEditOccurrence(o); } : undefined}
                    sx={{
                      position: 'absolute', zIndex: 1, boxSizing: 'border-box', overflow: 'hidden',
                      top: block.top, height: block.height,
                      left: `calc(${block.leftRatio * 100}% + ${CHIP_MARGIN_LEFT}px)`,
                      width: `calc(${Math.min(block.widthRatio, CHIP_MAX_WIDTH_RATIO) * 100}% - ${CHIP_MARGIN_LEFT}px)`,
                      px: '4px', borderRadius: '2px', bgcolor: bg, cursor: 'pointer', touchAction: 'none',
                      border: selected ? `2px solid ${c.onColor}` : `1px solid ${darken(bg)}`,
                      boxShadow: selected ? `0 0 0 1px ${c.blue}` : 'none',
                      display: 'flex', flexDirection: 'column', justifyContent: block.height < 30 ? 'center' : 'flex-start',
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: '2px', minWidth: 0 }}>
                      <Box sx={{ ...chipText, flex: 1 }}>{o.title}</Box>
                      {occurrenceMark(segment)}
                    </Box>
                    {block.height >= 32 && <Box sx={{ ...chipText, fontSize: 9, opacity: 0.9 }}>{range}</Box>}
                  </Box>
                );
              })}
              {/* 過ぎた時間の影（過ぎた日は下まで、今日は今まで） */}
              <Box sx={{
                position: 'absolute', top: 0, left: 0, right: 0, zIndex: 2, pointerEvents: 'none',
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
