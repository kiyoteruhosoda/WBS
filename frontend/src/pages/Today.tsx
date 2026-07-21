import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, CircularProgress, Alert, Checkbox } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { getDashboardToday } from '../api/dashboard';
import { completeTask, reopenTask } from '../api/tasks';
import { getCategories } from '../api/categories';
import type { Task } from '../types';
import { formatDate, isDueToday } from '../utils/format';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import { ds } from '../theme';
import StatusChip from '../components/StatusChip';
import PriorityChip from '../components/PriorityChip';
import CategoryDot from '../components/CategoryDot';

const bucketMeta: { key: string; labelKey: TranslationKey; accent?: string }[] = [
  { key: 'OVERDUE', labelKey: 'today.overdue', accent: ds.dangerText },
  { key: 'TODAY', labelKey: 'common.today', accent: ds.primary },
  { key: 'DOING', labelKey: 'status.DOING' },
  { key: 'TOMORROW', labelKey: 'today.tomorrow' },
];

const Today: React.FC = () => {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { t: translate } = useI18n();
  const { data: today, isLoading, error } = useQuery({ queryKey: ['dashboard-today'], queryFn: getDashboardToday });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });

  const toggleDone = useMutation({
    mutationFn: (task: Task) => (task.status === 'DONE' ? reopenTask(task) : completeTask(task)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dashboard-today'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      qc.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">{translate('common.loadError')}</Alert>;

  return (
    <Box sx={{ maxWidth: 880 }}>
      {bucketMeta.map(({ key, labelKey, accent }) => {
        const tasks = (today?.buckets as Record<string, Task[]> | undefined)?.[key] ?? [];
        return (
          <Box key={key} sx={{ mb: '20px' }}>
            <Box sx={{ display: 'flex', alignItems: 'baseline', gap: '8px', mb: '8px' }}>
              <Box sx={{ fontSize: 15, fontWeight: 700, color: accent ?? ds.text }}>{translate(labelKey)}</Box>
              <Box sx={{ fontSize: 12, color: ds.textSub }}>{translate('today.count', { count: tasks.length })}</Box>
            </Box>
            <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', overflow: 'hidden' }}>
              {tasks.length === 0 && (
                <Box sx={{ px: '16px', py: '14px', fontSize: 13, color: ds.textMuted }}>{translate('today.empty')}</Box>
              )}
              {tasks.map((t) => {
                const done = t.status === 'DONE';
                return (
                  <Box key={t.id} sx={{
                    display: 'flex', alignItems: 'center', gap: '10px', px: '10px', py: '6px',
                    borderBottom: `1px solid ${ds.hairline}`, '&:last-child': { borderBottom: 'none' },
                    '&:hover': { bgcolor: '#FAFAFA' },
                  }}>
                    <Checkbox
                      size="small"
                      checked={done}
                      onChange={() => toggleDone.mutate(t)}
                      sx={{ color: ds.todoGray, '&.Mui-checked': { color: ds.success } }}
                    />
                    <CategoryDot categoryId={t.category_id} categories={categories} size={7} />
                    <Box
                      onClick={() => navigate(`/tasks/${t.id}`)}
                      sx={{
                        flex: 1, minWidth: 0, fontSize: 14, cursor: 'pointer',
                        color: done ? ds.textMuted : ds.text,
                        textDecoration: done ? 'line-through' : 'none',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        '&:hover': { color: ds.primary },
                      }}
                    >
                      {t.title}
                    </Box>
                    <Box sx={{
                      fontSize: 12, whiteSpace: 'nowrap',
                      fontWeight: isDueToday(t) && !done ? 700 : 400,
                      color: isDueToday(t) && !done ? ds.dangerText : ds.textSub,
                    }}>
                      {isDueToday(t) ? translate('common.today') : formatDate(t.due_date)}
                    </Box>
                    <PriorityChip priority={t.priority} />
                    <StatusChip task={t} />
                  </Box>
                );
              })}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
};

export default Today;
