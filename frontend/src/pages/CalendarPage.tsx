import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Typography, CircularProgress, Alert } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import { getTasks } from '../api/tasks';
import { getMilestones } from '../api/milestones';
import type { EventClickArg } from '@fullcalendar/core';

const CalendarPage: React.FC = () => {
  const navigate = useNavigate();
  const { data: tasksData, isLoading, error } = useQuery({
    queryKey: ['tasks-calendar'],
    queryFn: () => getTasks({ per_page: 500 }),
  });
  const { data: milestones } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });

  const events = useMemo(() => {
    const taskEvents = (tasksData?.items ?? [])
      .filter(t => t.due_date)
      .map(t => ({ id: `task-${t.id}`, title: t.title, date: t.due_date!, color: '#1976d2', extendedProps: { type: 'task', taskId: t.id } }));
    const milestoneEvents = (milestones ?? [])
      .filter(m => m.due_date)
      .map(m => ({ id: `ms-${m.id}`, title: `🏁 ${m.name}`, date: m.due_date!, color: '#e91e63', extendedProps: { type: 'milestone' } }));
    return [...taskEvents, ...milestoneEvents];
  }, [tasksData, milestones]);

  const handleEventClick = (info: EventClickArg) => {
    const { type, taskId } = info.event.extendedProps;
    if (type === 'task') navigate(`/tasks/${taskId}`);
  };

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">読み込みエラー</Alert>;

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>カレンダー</Typography>
      <FullCalendar
        plugins={[dayGridPlugin]}
        initialView="dayGridMonth"
        events={events}
        eventClick={handleEventClick}
        locale="ja"
        headerToolbar={{ left: 'prev,next today', center: 'title', right: '' }}
      />
    </Box>
  );
};

export default CalendarPage;
