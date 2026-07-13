import React from 'react';
import { Chip } from '@mui/material';
import type { TaskStatus } from '../types';
import { statusLabel, statusColor } from '../utils/format';

interface Props { status: TaskStatus; size?: 'small' | 'medium'; }

const StatusChip: React.FC<Props> = ({ status, size = 'small' }) => (
  <Chip label={statusLabel[status] ?? status} color={statusColor[status] ?? 'default'} size={size} />
);

export default StatusChip;
