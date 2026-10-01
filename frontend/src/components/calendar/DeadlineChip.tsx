import React from 'react';
import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import FlagOutlinedIcon from '@mui/icons-material/FlagOutlined';
import TaskAltIcon from '@mui/icons-material/TaskAlt';
import { useI18n } from '../../i18n';
import type { CalendarDeadline } from '../../calendar/taskDeadlines';

interface Props {
  deadline: CalendarDeadline;
  /** px（月表示 14・週の終日の帯 20） */
  height: number;
  fontSize: number;
  onClick?: (e: React.MouseEvent<HTMLElement>) => void;
}

/**
 * タスク・マイルストーンの期限のチップ。予定（色で塗ったチップ）と見分けられるよう、地は塗らずに
 * 枠と左の帯だけ色を付け、頭に印（タスクはチェック、マイルストーンは旗）を置く。済みは打ち消し線。
 */
const DeadlineChip: React.FC<Props> = ({ deadline, height, fontSize, onClick }) => {
  const { t } = useI18n();
  const c = useTheme().palette.calendar;
  const Icon = deadline.kind === 'milestone' ? FlagOutlinedIcon : TaskAltIcon;
  const label = t(deadline.kind === 'milestone' ? 'calendar.milestoneDue' : 'calendar.taskDue', { title: deadline.title });
  return (
    <Box
      data-deadline={deadline.key}
      title={label}
      aria-label={label}
      onClick={onClick}
      sx={{
        height, boxSizing: 'border-box', display: 'flex', alignItems: 'center', gap: '2px', minWidth: 0,
        px: '3px', borderRadius: '3px', bgcolor: c.surface, color: c.textPrimary, fontSize,
        border: `1px dashed ${deadline.color}`, borderLeft: `3px solid ${deadline.color}`,
        opacity: deadline.done ? 0.6 : 1, cursor: onClick ? 'pointer' : 'inherit',
      }}
    >
      <Icon sx={{ fontSize: fontSize + 1, color: deadline.color, flexShrink: 0 }} />
      <Box sx={{
        flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        textDecoration: deadline.done ? 'line-through' : 'none',
      }}>
        {deadline.title}
      </Box>
    </Box>
  );
};

export default DeadlineChip;
