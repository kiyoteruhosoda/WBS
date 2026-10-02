// 選んだタスクをまとめて別のプロジェクトへ移す（task #187、ADR-0030）。
// 子タスクは親に従う（ADR-0024 の 4）ので、送るのは親の無いタスクだけ。親と一緒に移るもの・
// 親を選んでいないので移さないものを、押す前に数で見せる。
import React, { useState } from 'react';
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, TextField,
} from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { moveTasksToProject } from '../../api/tasks';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';
import { pickableProjects } from '../../projects/projectScope';
import { moveToProjectRequest, type ProjectMovePlan } from '../../projects/taskListView';
import type { Project, TaskMoveToProjectResult } from '../../types';

interface Props {
  open: boolean;
  plan: ProjectMovePlan;
  projects: Project[];
  onClose: () => void;
  onMoved: (result: TaskMoveToProjectResult, targetLabel: string) => void;
}

const NONE = 'none';

const MoveToProjectDialog: React.FC<Props> = ({ open, plan, projects, onClose, onMoved }) => {
  const { t } = useI18n();
  const qc = useQueryClient();
  // 移し先は空から始める（絞り込み中のプロジェクトから外へ出すことが多い）
  const [target, setTarget] = useState<string>('');
  const projectId = target === NONE || target === '' ? null : Number(target);
  const label = target === NONE ? t('scope.none') : projects.find((p) => p.id === projectId)?.path ?? '';
  const request = moveToProjectRequest(plan, projectId);

  const move = useMutation({
    mutationFn: () => {
      if (request === null) throw new Error('nothing to move');
      return moveTasksToProject(request);
    },
    onSuccess: async (result) => {
      // 一覧・各タスク・ガント・実績など、プロジェクトで絞る画面を全部読み直す
      await qc.invalidateQueries();
      setTarget('');
      onMoved(result, label);
    },
  });

  const close = () => {
    if (move.isPending) return;
    move.reset();
    setTarget('');
    onClose();
  };

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="xs">
      <DialogTitle>{t('taskList.moveTitle')}</DialogTitle>
      <DialogContent>
        <Box sx={{ fontSize: 13, color: ds.text, mb: '14px' }}>
          {t('taskList.moveCount', { count: plan.roots.length })}
        </Box>
        <TextField
          select fullWidth size="small" autoFocus
          label={t('taskList.moveTarget')}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          data-testid="tasklist-move-target"
        >
          <MenuItem value={NONE}>{t('scope.none')}</MenuItem>
          {pickableProjects(projects).map(({ project, depth }) => (
            <MenuItem key={project.id} value={String(project.id)} sx={{ pl: `${16 + depth * 14}px` }}>
              <Box component="span" sx={{
                width: 8, height: 8, borderRadius: '50%', mr: '8px', flexShrink: 0,
                bgcolor: project.color ?? ds.textMuted,
              }} />
              {project.name}
            </MenuItem>
          ))}
        </TextField>
        <Box component="ul" sx={{ m: '12px 0 0', pl: '18px', fontSize: 12, color: ds.textSub, '& li': { mb: '4px' } }}>
          {plan.carried + plan.followers.length > 0 && (
            <li>{t('taskList.moveCarried', { count: plan.carried + plan.followers.length })}</li>
          )}
          {plan.stranded.length > 0 && (
            <Box component="li" sx={{ color: ds.warnText }}>
              {t('taskList.moveStranded', { count: plan.stranded.length })}
            </Box>
          )}
          <li>{t('taskList.moveMilestoneNote')}</li>
        </Box>
        {move.isError && <Alert severity="error" sx={{ mt: '12px' }}>{t('taskList.moveFailed')}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={close} disabled={move.isPending}>{t('taskList.cancel')}</Button>
        <Button
          variant="contained"
          disabled={target === '' || request === null || move.isPending}
          onClick={() => move.mutate()}
          data-testid="tasklist-move-submit"
        >
          {t('taskList.moveSubmit')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default MoveToProjectDialog;
