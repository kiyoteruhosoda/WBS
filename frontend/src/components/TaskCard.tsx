import React from 'react';
import { Card, CardContent, Typography, Box } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import type { Task } from '../types';
import { formatDate, priorityLabel } from '../utils/format';
import StatusChip from './StatusChip';

interface Props { task: Task; }

const TaskCard: React.FC<Props> = ({ task }) => {
  const navigate = useNavigate();
  return (
    <Card variant="outlined" sx={{ mb: 1, cursor: 'pointer' }} onClick={() => navigate(`/tasks/${task.id}`)}>
      <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
        <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{task.title}</Typography>
        <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
          <StatusChip status={task.status} />
          <Typography variant="caption" color="text.secondary">{formatDate(task.due_date)}</Typography>
          <Typography variant="caption" color="warning.main">{priorityLabel(task.priority)}</Typography>
        </Box>
      </CardContent>
    </Card>
  );
};

export default TaskCard;
