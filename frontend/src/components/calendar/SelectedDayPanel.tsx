import React, { useRef } from 'react';
import { Box, IconButton, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import CheckBoxIcon from '@mui/icons-material/CheckBox';
import CheckBoxOutlineBlankIcon from '@mui/icons-material/CheckBoxOutlineBlank';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import { useI18n } from '../../i18n';
import { TrashIcon } from '../icons';
import type { CalendarHoliday } from '../../types';
import type { DaySegment } from '../../calendar/daySegments';
import { formatOccurrenceTimeRange } from '../../calendar/daySegments';
import type { LinkedTask } from '../../calendar/taskScheduling';
import { linkedTaskLabel, occurrenceColor } from '../../calendar/taskScheduling';
import { formatSelectedDay } from '../../calendar/calendarTitles';
import type { CalendarInteractions } from './calendarInteractions';
import type { CalendarDeadline } from '../../calendar/taskDeadlines';
import DeadlineChip from './DeadlineChip';
import { isDismissSwipe } from '../../calendar/dayPanel';

interface Props extends Pick<
  CalendarInteractions, 'onCreateEvent' | 'onEditOccurrence' | 'onDeleteOccurrence' | 'onOpenDeadline' | 'onToggleDone'
> {
  date: string;
  segments: readonly DaySegment[];
  deadlines: readonly CalendarDeadline[];
  holidays: readonly CalendarHoliday[];
  timeZone: string;
  selectedSegmentKey: string | null;
  onClose: () => void;
  /** 予定に結んだタスクの印（色・題名） */
  linkedTasks?: ReadonlyMap<number, LinkedTask>;
  /** 外側を押したら閉じる判定に使う（ClickAwayListener が渡す） */
  ref?: React.Ref<HTMLDivElement>;
}

/**
 * 選んだ日の予定の一覧（移植元 CalendarPage.xaml の SelectedDayPanel）。日付の見出し・月のマスを押したときだけ
 * カレンダーの下に出す（ADR-0034）。閉じ方: ×・同じ日をもう一度押す・外側を押す・Esc・見出しを下へ払う（狭い画面）。
 */
const SelectedDayPanel: React.FC<Props> = ({
  date, segments, deadlines, holidays, timeZone, selectedSegmentKey, onClose, onCreateEvent, onEditOccurrence, onDeleteOccurrence,
  onOpenDeadline, onToggleDone, linkedTasks, ref,
}) => {
  const { t, weekdays } = useI18n();
  const theme = useTheme();
  const c = theme.palette.calendar;
  const narrow = useMediaQuery(theme.breakpoints.down('md'));
  const holidayNames = holidays.filter((h) => h.date === date).map((h) => h.name).filter((n): n is string => !!n);
  const iconButton = { width: 40, height: 40, color: c.textSecondary };
  // 見出しを下へ払うと閉じる（指で。中の一覧のスクロールとは取り違えない）
  const swipeStart = useRef<{ x: number; y: number } | null>(null);
  const swipe = {
    onPointerDown: (e: React.PointerEvent) => { swipeStart.current = { x: e.clientX, y: e.clientY }; },
    onPointerUp: (e: React.PointerEvent) => {
      const start = swipeStart.current;
      swipeStart.current = null;
      if (start && isDismissSwipe(e.clientX - start.x, e.clientY - start.y)) onClose();
    },
    onPointerCancel: () => { swipeStart.current = null; },
  };

  return (
    <Box
      ref={ref}
      data-testid="selected-day-panel"
      role="region"
      aria-label={formatSelectedDay(date, t, weekdays)}
      sx={{ borderTop: `1px solid ${c.border}`, bgcolor: c.surface, flexShrink: 0, boxShadow: '0 -2px 6px rgba(0, 0, 0, 0.06)' }}
    >
      {narrow && (
        // 払って閉じられる印（掴む場所）
        <Box {...swipe} data-testid="selected-day-grabber" sx={{ display: 'flex', justifyContent: 'center', pt: '6px', touchAction: 'none' }}>
          <Box sx={{ width: 36, height: 4, borderRadius: '2px', bgcolor: c.border }} />
        </Box>
      )}
      <Box {...swipe} sx={{ display: 'flex', alignItems: 'center', px: '12px', py: narrow ? '2px' : '8px', gap: '8px', touchAction: narrow ? 'none' : 'auto' }}>
        <Box sx={{ flex: 1, fontSize: 14, fontWeight: 600, color: c.textPrimary }}>
          {formatSelectedDay(date, t, weekdays)}
        </Box>
        {onCreateEvent && (
          <IconButton aria-label={t('calendar.addEvent')} onClick={() => onCreateEvent(date)} sx={{ ...iconButton, color: c.blue }}>
            <AddIcon />
          </IconButton>
        )}
        <IconButton aria-label={t('calendar.closeDay')} onClick={onClose} sx={iconButton}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>
      {holidayNames.length > 0 && (
        <Box sx={{ fontSize: 12, mx: '12px', mb: '4px', color: c.holidayText }}>{holidayNames.join('  /  ')}</Box>
      )}
      {deadlines.length > 0 && (
        <Box data-testid="selected-day-deadlines" sx={{ display: 'flex', flexDirection: 'column', gap: '4px', mx: '12px', mb: '6px' }}>
          {deadlines.map((d) => (
            <DeadlineChip
              key={d.key}
              deadline={d}
              height={28}
              fontSize={13}
              onClick={onOpenDeadline ? () => onOpenDeadline(d) : undefined}
            />
          ))}
        </Box>
      )}
      {segments.length === 0 ? (
        <Box sx={{ fontSize: 13, mx: '12px', my: '8px', color: c.textSecondary }}>{t('calendar.noEvents')}</Box>
      ) : (
        <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, maxHeight: { xs: '32svh', md: 240 }, overflowY: 'auto' }}>
          {segments.map((segment) => {
            const o = segment.occurrence;
            const range = formatOccurrenceTimeRange(o, timeZone);
            const badges = [
              o.is_moved ? t('calendar.badgeMoved') : null,
              o.is_overridden ? t('calendar.badgeModified') : null,
              o.is_private ? t('calendar.privateMark') : null,
              o.is_imported ? t('calendar.importedMark') : null,
            ].filter(Boolean).join('  ');
            const taskLabel = linkedTaskLabel(o, linkedTasks);
            return (
              <Box
                component="li"
                key={segment.key}
                data-occurrence-id={o.id}
                sx={{
                  display: 'flex', alignItems: 'center', minHeight: 48, px: '12px', py: '4px', gap: '8px',
                  bgcolor: segment.key === selectedSegmentKey ? c.surfaceVariant : 'transparent',
                }}
              >
                <Box sx={{ width: 4, height: 32, borderRadius: '2px', bgcolor: occurrenceColor(o, linkedTasks), flexShrink: 0 }} />
                {/* タスクの分類の回は済みのチェック（ADR-0025） */}
                {o.event_type === 'TASK' && (
                  <IconButton
                    role="checkbox"
                    aria-checked={o.is_done}
                    aria-label={t(o.is_done ? 'calendar.markUndone' : 'calendar.markDone')}
                    disabled={!onToggleDone}
                    onClick={() => onToggleDone?.(o)}
                    sx={{ ...iconButton, ml: '-8px', mr: '-4px', color: o.is_done ? c.blue : c.textSecondary }}
                  >
                    {o.is_done ? <CheckBoxIcon /> : <CheckBoxOutlineBlankIcon />}
                  </IconButton>
                )}
                <Box sx={{ flex: 1, minWidth: 0, opacity: o.is_done ? 0.6 : 1 }}>
                  <Box sx={{
                    fontSize: 14, color: c.textPrimary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    textDecoration: o.is_done ? 'line-through' : 'none',
                  }}>
                    {o.title}
                  </Box>
                  {taskLabel && (
                    <Box sx={{ fontSize: 12, color: c.textSecondary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t('calendar.linkedTask', { title: taskLabel })}
                    </Box>
                  )}
                  <Box sx={{ fontSize: 12, color: c.textSecondary }}>
                    {range ?? t('calendar.allDay')}
                    {o.location ? `  ${o.location}` : ''}
                    {badges ? `  ${badges}` : ''}
                  </Box>
                </Box>
                {onEditOccurrence && (
                  <IconButton
                    aria-label={t(o.is_imported ? 'calendar.importedDetails' : 'calendar.editEvent')}
                    onClick={() => onEditOccurrence(o)}
                    sx={iconButton}
                  >
                    <EditOutlinedIcon fontSize="small" />
                  </IconButton>
                )}
                {onDeleteOccurrence && !o.is_imported && (
                  <IconButton aria-label={t('calendar.deleteEvent')} onClick={() => onDeleteOccurrence(o)} sx={iconButton}>
                    <TrashIcon size={18} />
                  </IconButton>
                )}
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
};

export default SelectedDayPanel;
