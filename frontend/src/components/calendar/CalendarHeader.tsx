import React from 'react';
import { Box, Button, IconButton, ToggleButton, ToggleButtonGroup, Tooltip } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import ChevronLeft from '@mui/icons-material/ChevronLeft';
import ChevronRight from '@mui/icons-material/ChevronRight';
import UndoIcon from '@mui/icons-material/Undo';
import RedoIcon from '@mui/icons-material/Redo';
import { useI18n } from '../../i18n';
import type { CalendarMode } from '../../calendar/calendarNavigation';

interface Props {
  mode: CalendarMode;
  title: string;
  onModeChange: (mode: CalendarMode) => void;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
  /** 表示の切り替えの行の左（「時間を取る」のタスクの一覧を出す・しまう。ADR-0035） */
  toolbarStart?: React.ReactNode;
  /** 表示の切り替えの行の右端（表示するカレンダー。触る頻度がいちばん低いので端に。ADR-0035） */
  toolbarEnd?: React.ReactNode;
}

const modes: { mode: CalendarMode; testId: string; labelKey: 'calendar.modeMonth' | 'calendar.modeWeek' | 'calendar.modeWeekdays' }[] = [
  { mode: 'month', testId: 'mode-month', labelKey: 'calendar.modeMonth' },
  { mode: 'week', testId: 'mode-week', labelKey: 'calendar.modeWeek' },
  { mode: 'weekdays', testId: 'mode-weekdays', labelKey: 'calendar.modeWeekdays' },
];

/**
 * 見出し（移植元 CalendarPage.xaml の Row 0）: 前へ・年月・元に戻す・やり直し・今日・次へ。いちばん触るので上。
 * その下の行に、左にタスクの一覧の出し入れ、右に月・週・平日の切り替えと、右端に表示するカレンダー
 * （ADR-0035。触る頻度の順に上・大きく。表示するカレンダーは常時の列をやめて、ここから開く）。
 */
const CalendarHeader: React.FC<Props> = ({
  mode, title, onModeChange, onPrev, onNext, onToday, onUndo, onRedo, canUndo, canRedo, toolbarStart, toolbarEnd,
}) => {
  const { t } = useI18n();
  const c = useTheme().palette.calendar;
  const round = { width: 36, height: 36, color: c.textSecondary };

  return (
    <Box sx={{ bgcolor: c.surface }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: '48px minmax(0, 1fr) auto auto auto 48px', alignItems: 'center', height: 48, mt: '4px' }}>
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <IconButton aria-label={t('calendar.prev')} onClick={onPrev} sx={round}>
            <ChevronLeft fontSize="small" />
          </IconButton>
        </Box>
        <Box
          data-testid="calendar-title"
          sx={{
            fontSize: { xs: 15, sm: 18 }, fontWeight: 600, color: c.textPrimary, textAlign: 'center',
            overflow: 'hidden', textOverflow: 'ellipsis',
            // 狭い画面は 2 行まで折り返す（1 行のままだと週の範囲の終わりの日が「…」で切れて見えない）
            whiteSpace: { xs: 'normal', sm: 'nowrap' }, lineHeight: { xs: 1.25, sm: 'normal' },
            display: { xs: '-webkit-box', sm: 'block' }, WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
          }}
        >
          {title}
        </Box>
        {/* 元に戻す・やり直し（週のドラッグ操作の履歴。履歴は呼び手が持つ） */}
        <Tooltip title={t('calendar.undo')}>
          <span>
            <IconButton aria-label={t('calendar.undo')} onClick={onUndo} disabled={!onUndo || !canUndo} sx={{ ...round, mx: '2px' }}>
              <UndoIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title={t('calendar.redo')}>
          <span>
            <IconButton aria-label={t('calendar.redo')} onClick={onRedo} disabled={!onRedo || !canRedo} sx={{ ...round, mx: '2px' }}>
              <RedoIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </span>
        </Tooltip>
        <Button
          variant="outlined"
          onClick={onToday}
          sx={{
            height: 32, px: '10px', py: 0, mx: '4px', minWidth: 0, borderRadius: '6px', fontSize: 13,
            color: c.blue, borderColor: c.border, borderWidth: 1,
            '&:hover': { borderColor: c.border, bgcolor: c.surfaceVariant },
          }}
        >
          {t('common.today')}
        </Button>
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <IconButton aria-label={t('calendar.next')} onClick={onNext} sx={round}>
            <ChevronRight fontSize="small" />
          </IconButton>
        </Box>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', px: '12px', pb: '8px' }}>
        {toolbarStart}
        <Box sx={{ flex: 1 }} />
        <ToggleButtonGroup
          size="small"
          exclusive
          value={mode}
          onChange={(_, value: CalendarMode | null) => { if (value) onModeChange(value); }}
          aria-label={t('nav.calendar')}
        >
          {modes.map((m) => (
            <ToggleButton
              key={m.mode}
              value={m.mode}
              data-testid={m.testId}
              sx={{ px: { xs: '8px', sm: '12px' }, py: '3px', fontSize: 12, fontWeight: 700, textTransform: 'none' }}
            >
              {t(m.labelKey)}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        {toolbarEnd}
      </Box>
    </Box>
  );
};

export default CalendarHeader;
