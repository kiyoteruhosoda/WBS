import React, { useEffect, useRef, useState } from 'react';
import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useI18n } from '../../i18n';
import type { MonthCell } from '../../calendar/monthCells';
import { availableChipRows, visibleChipCount } from '../../calendar/monthCells';
import { eventColor } from '../../calendar/calendarColors';
import { formatOccurrenceTimeRange } from '../../calendar/daySegments';
import DeadlineChip from './DeadlineChip';

interface Props {
  cells: MonthCell[];
  selectedDate: string | null;
  timeZone: string;
  onSelectDate: (date: string) => void;
}

// 移植元の既定のマスの高さ。これより低くはしない。
const MIN_CELL_HEIGHT = 88;

/** 月表示（移植元 CalendarPage.xaml の MonthGrid）。6×7 のマスに色チップを入るだけ並べる。 */
const MonthView: React.FC<Props> = ({ cells, selectedDate, timeZone, onSelectDate }) => {
  const { t, weekdays } = useI18n();
  const c = useTheme().palette.calendar;
  const gridRef = useRef<HTMLDivElement>(null);
  const [cellHeight, setCellHeight] = useState(MIN_CELL_HEIGHT);

  // マスの高さに合わせてチップの段数を変える（移植元 UpdateDayCellChipCount）。
  useEffect(() => {
    const el = gridRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      setCellHeight(Math.max(MIN_CELL_HEIGHT, entry.contentRect.height / 6));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const background = (cell: MonthCell): string => {
    if (!cell.isCurrentMonth) return 'transparent';
    if (cell.holiday) return c.holidayBg;
    if (cell.dayOfWeek === 0) return c.sundayBg;
    if (cell.dayOfWeek === 6) return c.saturdayBg;
    return 'transparent';
  };

  const dayTextColor = (cell: MonthCell, selected: boolean): string => {
    if (cell.isToday || selected) return c.onColor;
    if (cell.holiday && cell.isCurrentMonth) return c.holidayText;
    if (cell.isCurrentMonth) return c.textPrimary;
    return c.outOfMonthText;
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, bgcolor: c.surface }}>
      {/* 曜日（日曜は赤・土曜は青） */}
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', height: 36, alignItems: 'center', flexShrink: 0 }}>
        {weekdays.map((w, i) => (
          <Box key={w} sx={{ textAlign: 'center', fontSize: 11, color: i === 0 ? c.red : i === 6 ? c.blue : c.textSecondary }}>
            {w}
          </Box>
        ))}
      </Box>
      <Box sx={{ height: '1px', bgcolor: c.border, flexShrink: 0 }} />
      <Box
        ref={gridRef}
        sx={{
          flex: 1, minHeight: 6 * MIN_CELL_HEIGHT, display: 'grid',
          gridTemplateColumns: 'repeat(7, minmax(0, 1fr))',
          gridTemplateRows: `repeat(6, minmax(${MIN_CELL_HEIGHT}px, 1fr))`,
        }}
      >
        {cells.map((cell) => {
          const selected = cell.date === selectedDate;
          const rows = availableChipRows(cellHeight, cell.holiday != null);
          // 予定のチップの後に期限のチップを続け、あふれは合わせて「+N 件」。
          const total = cell.segments.length + cell.deadlines.length;
          const shown = visibleChipCount(total, rows);
          const extra = total - shown;
          const shownDeadlines = cell.deadlines.slice(0, Math.max(0, shown - cell.segments.length));
          return (
            <Box
              key={cell.date}
              data-date={cell.date}
              role="button"
              tabIndex={0}
              aria-pressed={selected}
              onClick={() => onSelectDate(cell.date)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectDate(cell.date); } }}
              sx={{
                position: 'relative', minWidth: 0, overflow: 'hidden', cursor: 'pointer', p: '2px',
                borderRight: `1px solid ${c.border}`, borderBottom: `1px solid ${c.border}`,
                bgcolor: background(cell),
                '&:nth-of-type(7n)': { borderRight: 'none' },
                '&:focus-visible': { outline: `2px solid ${c.blue}`, outlineOffset: -2 },
              }}
            >
              <Box sx={{
                width: 28, height: 28, mx: 'auto', mt: '4px', mb: '2px', borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13,
                bgcolor: cell.isToday ? c.blue : selected ? c.selectedCircle : 'transparent',
                color: dayTextColor(cell, selected),
              }}>
                {Number(cell.date.slice(8, 10))}
              </Box>
              {cell.holiday && (
                <Box
                  title={cell.holiday.name ?? ''}
                  sx={{
                    height: 14, lineHeight: '14px', borderRadius: '3px', mx: '1px', mb: '2px', px: '3px',
                    bgcolor: c.red, color: c.onColor, fontSize: 10,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}
                >
                  {cell.holiday.name ?? ''}
                </Box>
              )}
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {cell.segments.slice(0, shown).map((segment) => {
                  const o = segment.occurrence;
                  const range = formatOccurrenceTimeRange(o, timeZone);
                  return (
                    <Box
                      key={segment.key}
                      title={range ? `${o.title}\n${range}` : o.title}
                      sx={{
                        height: 14, lineHeight: '14px', borderRadius: '3px', mx: '1px', px: '3px',
                        bgcolor: eventColor(o.color_key), color: c.onColor, fontSize: 10,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}
                    >
                      {o.title}
                    </Box>
                  );
                })}
                {shownDeadlines.map((deadline) => (
                  <Box key={deadline.key} sx={{ mx: '1px' }}>
                    <DeadlineChip deadline={deadline} height={14} fontSize={10} />
                  </Box>
                ))}
              </Box>
              {extra > 0 && (
                <Box sx={{ fontSize: 10, m: '1px 3px 0', color: c.textSecondary }}>
                  {t('calendar.more', { count: extra })}
                </Box>
              )}
              {/* 過ぎた日の影。中身ごと沈める。押せるように pointer は通す。 */}
              {cell.isPast && (
                <Box sx={{ position: 'absolute', inset: 0, bgcolor: c.pastShade, pointerEvents: 'none' }} />
              )}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};

export default MonthView;
