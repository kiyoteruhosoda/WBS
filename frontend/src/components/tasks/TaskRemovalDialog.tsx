// Confirmation dialog for deleting or archiving a task (task #388, #394, ADR-0046).
// Deleted if it has no confirmed actuals; otherwise archived instead (hidden from lists and reassignment targets, kept in the actuals tables).
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
import { archiveTask, deleteTask, getTaskRemoval } from '../../api/tasks';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';

interface Props {
  taskId: number;
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}

const TaskRemovalDialog: React.FC<Props> = ({ taskId, open, onClose, onDone }) => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data: removal, isLoading, error } = useQuery({
    queryKey: ['task-removal', taskId], queryFn: () => getTaskRemoval(taskId), enabled: open,
  });
  const run = useMutation({
    mutationFn: () => (removal?.action === 'archive' ? archiveTask(taskId) : deleteTask(taskId)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['tasks'] });
      void qc.invalidateQueries({ queryKey: ['task'] });
      onDone();
    },
  });

  const archive = removal?.action === 'archive';
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs" data-testid="task-removal-dialog">
      <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>
        {removal
          ? t(archive ? 'taskRemoval.archiveTitle' : 'taskRemoval.deleteTitle', { title: removal.title })
          : t('taskRemoval.loadingTitle')}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', py: '12px' }}><CircularProgress size={24} /></Box>}
        {error && <Alert severity="error">{t('common.loadError')}</Alert>}
        {run.isError && <Alert severity="error">{t('taskRemoval.failed')}</Alert>}
        {removal && (
          <Box sx={{ fontSize: 14, color: ds.textSub, lineHeight: 1.7 }}>
            {removal.work_log_hours > 0
              ? t('taskRemoval.workLogs', { hours: `${Number(removal.work_log_hours.toFixed(2))}h` })
              : t('taskRemoval.noWorkLogs')}
            {archive && <Box component="span" sx={{ display: 'block', mt: '6px' }}>{t('taskRemoval.archiveExplain')}</Box>}
          </Box>
        )}
      </DialogContent>
      <DialogActions sx={{ px: '24px', pb: '18px' }}>
        <Button onClick={onClose} sx={{ color: ds.textSub }}>{t('taskRemoval.cancel')}</Button>
        <Button
          variant="contained" color={archive ? 'primary' : 'error'}
          disabled={!removal || run.isPending}
          onClick={() => run.mutate()} sx={{ px: '24px' }} data-testid="task-removal-run"
        >
          {t(archive ? 'taskRemoval.archive' : 'taskRemoval.delete')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default TaskRemovalDialog;
