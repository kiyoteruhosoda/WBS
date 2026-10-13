// タスクを消す・しまう確認の窓（task #388、ADR-0046）。
// 打刻も実績も無ければ消す。あれば消さずに「しまう」（一覧と付け替え先に出ない。実績と締めの表には残る）。
// 打刻の件数・時間と、そのタスクを指す WinTrack の規則の件数（しまうと止まる）を出す。
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
import { archiveTask, deleteTask, getTaskRemoval } from '../../api/tasks';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';
import { formatSecondsAsHours } from '../../utils/format';

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
      void qc.invalidateQueries({ queryKey: ['today'] });
      void qc.invalidateQueries({ queryKey: ['tracking-rules'] });
      onDone();
    },
  });

  const archive = removal?.action === 'archive';
  const blocked = removal?.blocked_by === 'running';
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
            {removal.time_entries > 0
              ? t('taskRemoval.entries', {
                count: removal.time_entries, hours: formatSecondsAsHours(removal.tracked_seconds),
              })
              : t('taskRemoval.noEntries')}
            {removal.work_log_hours > 0 && t('taskRemoval.workLogs', { hours: `${Number(removal.work_log_hours.toFixed(2))}h` })}
            {t('taskRemoval.rules', { count: removal.tracking_rules })}
            {archive && <Box component="span" sx={{ display: 'block', mt: '6px' }}>{t('taskRemoval.archiveExplain')}</Box>}
          </Box>
        )}
        {blocked && <Alert severity="warning">{t('taskRemoval.blockedRunning')}</Alert>}
      </DialogContent>
      <DialogActions sx={{ px: '24px', pb: '18px' }}>
        <Button onClick={onClose} sx={{ color: ds.textSub }}>{t('taskRemoval.cancel')}</Button>
        <Button
          variant="contained" color={archive ? 'primary' : 'error'}
          disabled={!removal || blocked || run.isPending}
          onClick={() => run.mutate()} sx={{ px: '24px' }} data-testid="task-removal-run"
        >
          {t(archive ? 'taskRemoval.archive' : 'taskRemoval.delete')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default TaskRemovalDialog;
