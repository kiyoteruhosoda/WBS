import React from 'react';
import { Box } from '@mui/material';
import type { Task } from '../types';
import type { DisplayStatus } from '../utils/format';
import { statusLabel, displayStatus } from '../utils/format';
import { ds } from '../theme';

const styles: Record<DisplayStatus, { color: string; bg: string }> = {
  TODO: { color: ds.priorityLowText, bg: ds.priorityLowBg },
  DOING: { color: ds.primary, bg: ds.primaryPale },
  WAITING: { color: ds.warnText, bg: ds.warnPale },
  DONE: { color: ds.successDark, bg: ds.successPale },
  CANCELLED: { color: ds.textMuted, bg: ds.priorityLowBg },
  LATE: { color: ds.dangerText, bg: ds.dangerPale2 },
};

interface Props {
  status?: DisplayStatus;
  task?: Pick<Task, 'due_date' | 'status'>;
}

// task を渡すと期限超過を「遅延」として表示する
const StatusChip: React.FC<Props> = ({ status, task }) => {
  const s: DisplayStatus = status ?? (task ? displayStatus(task) : 'TODO');
  const st = styles[s];
  return (
    <Box component="span" sx={{
      display: 'inline-block', px: '10px', py: '2px', borderRadius: '10px',
      fontSize: 11, fontWeight: 700, lineHeight: 1.7,
      color: st.color, bgcolor: st.bg, whiteSpace: 'nowrap',
    }}>
      {s === 'LATE' ? '遅延' : statusLabel[s]}
    </Box>
  );
};

export default StatusChip;
