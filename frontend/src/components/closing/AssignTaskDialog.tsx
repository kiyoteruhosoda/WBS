import React from 'react';
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, useMediaQuery, useTheme } from '@mui/material';
import { useI18n } from '../../i18n';
import type { Project, Task } from '../../types';
import type { ProjectScope } from '../../projects/projectScope';
import type { PickerHead } from '../../projects/taskPicker';
import TaskPicker from '../TaskPicker';

interface Props {
  open: boolean;
  entryCount: number;
  tasks: readonly Task[];
  projects: readonly Project[];
  /** 先頭の候補（同じ時間の予定のタスク・直前に使ったタスク） */
  head: readonly PickerHead[];
  scope: ProjectScope;
  onCancel: () => void;
  /** null は未割当へ戻す */
  onChoose: (taskId: number | null) => void;
}

/**
 * 選んだ打刻にまとめてタスクを振る（task #161・#189）。先頭の候補のあとは、プロジェクトの木で束ねた
 * タスク（サイドバーの範囲の中が先）。並べ方は上部の打刻ボタンと同じ部品（TaskPicker）。
 */
const AssignTaskDialog: React.FC<Props> = ({ open, entryCount, tasks, projects, head, scope, onCancel, onChoose }) => {
  const { t } = useI18n();
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down('sm'));
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth fullScreen={narrow}>
      <DialogTitle>{t('closing.assignTitle', { count: entryCount })}</DialogTitle>
      <DialogContent dividers sx={{ p: 0, display: 'flex', flexDirection: 'column' }}>
        <TaskPicker
          tasks={tasks} projects={projects} head={head} scope={scope} onChoose={onChoose} autoFocus={!narrow}
          maxHeight={narrow ? 'none' : 420}
        />
      </DialogContent>
      <DialogActions sx={{ justifyContent: 'space-between' }}>
        <Button color="inherit" onClick={() => onChoose(null)}>{t('closing.assignClear')}</Button>
        <Button onClick={onCancel}>{t('calendar.cancel')}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default AssignTaskDialog;
