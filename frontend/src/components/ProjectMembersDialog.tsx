// プロジェクトのメンバー（task #544、ADR-0055）。
// メンバーはいちばん上のプロジェクトに付くので、どの段から開いても根の名簿を出す。
// 加える・外す・役割を変えるのは管理者だけ。メンバーは自分だけ「抜ける」ができる。
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, TextField,
} from '@mui/material';
import {
  addProjectMember, changeProjectMemberRole, getPeople, getProjectMembers, projectMembersKey, removeProjectMember,
  PEOPLE_KEY, PROJECTS_KEY,
} from '../api/projects';
import type { Project, ProjectRole } from '../types';
import { useI18n } from '../i18n';
import { ds } from '../theme';

interface Props {
  project: Project | null;
  /** いちばん上のプロジェクトの名前（説明に出す） */
  rootName: string;
  onClose: () => void;
}

const ROLES: ProjectRole[] = ['manager', 'member'];

const errorKey = (error: unknown) => {
  const status = isAxiosError(error) ? error.response?.status : undefined;
  if (status === 403) return 'member.managerOnly' as const;
  if (status === 409) return 'member.lastManager' as const;
  return 'member.error' as const;
};

const ProjectMembersDialog: React.FC<Props> = ({ project, rootName, onClose }) => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const projectId = project?.id ?? 0;
  const members = useQuery({
    queryKey: projectMembersKey(projectId),
    queryFn: () => getProjectMembers(projectId),
    enabled: project !== null,
  });
  const canManage = members.data?.can_manage ?? false;
  const people = useQuery({ queryKey: PEOPLE_KEY, queryFn: getPeople, enabled: project !== null && canManage });
  const [person, setPerson] = useState('');
  const [role, setRole] = useState<ProjectRole>('member');

  const memberIds = useMemo(() => new Set((members.data?.members ?? []).map((m) => m.user_id)), [members.data]);
  const choices = (people.data ?? []).filter((p) => !memberIds.has(p.id));

  const changed = () => {
    qc.invalidateQueries({ queryKey: projectMembersKey(projectId) });
    // 抜けたら木ごと見えなくなる。担当者の候補も変わる
    qc.invalidateQueries({ queryKey: PROJECTS_KEY });
    qc.invalidateQueries({ queryKey: ['tasks'] });
  };
  const add = useMutation({
    mutationFn: () => addProjectMember(projectId, Number(person), role),
    onSuccess: () => { setPerson(''); setRole('member'); changed(); },
  });
  const changeRole = useMutation({
    mutationFn: ({ userId, next }: { userId: number; next: ProjectRole }) => changeProjectMemberRole(projectId, userId, next),
    onSuccess: changed,
  });
  const remove = useMutation({
    mutationFn: ({ userId }: { userId: number; you: boolean }) => removeProjectMember(projectId, userId),
    onSuccess: (_, { you }) => { changed(); if (you) onClose(); },
  });
  const failed = [add, changeRole, remove].find((m) => m.isError);

  return (
    <Dialog open={project !== null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('member.title')}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '14px', pt: '4px !important' }}>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('member.hint', { name: rootName })}</Box>
        {failed && <Alert severity="error">{t(errorKey(failed.error))}</Alert>}
        {members.isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}><CircularProgress size={24} /></Box>}
        {members.data && (
          <Box component="ul" aria-label={t('member.title')} sx={{ listStyle: 'none', m: 0, p: 0, border: `1px solid ${ds.border}`, borderRadius: '8px' }}>
            {members.data.members.map((m) => (
              <Box
                component="li" key={m.user_id}
                sx={{
                  display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', px: '12px', py: '8px',
                  borderTop: `1px solid ${ds.borderPale}`, '&:first-of-type': { borderTop: 'none' },
                }}
              >
                <Box sx={{ flex: 1, minWidth: 160 }}>
                  <Box sx={{ fontSize: 14, fontWeight: 600, color: ds.text }}>
                    {m.display_name || m.email}{m.is_you && <Box component="span" sx={{ fontWeight: 400, color: ds.textMuted }}>{`（${t('member.you')}）`}</Box>}
                  </Box>
                  {m.display_name && <Box sx={{ fontSize: 12, color: ds.textMuted }}>{m.email}</Box>}
                </Box>
                {canManage ? (
                  <TextField
                    select size="small" label={t('member.roleLabel')} value={m.role} sx={{ width: 130 }}
                    onChange={(e) => changeRole.mutate({ userId: m.user_id, next: e.target.value as ProjectRole })}
                  >
                    {ROLES.map((r) => <MenuItem key={r} value={r}>{t(`member.role.${r}`)}</MenuItem>)}
                  </TextField>
                ) : (
                  <Box sx={{ fontSize: 13, color: ds.textSub }}>{t(`member.role.${m.role}`)}</Box>
                )}
                {(canManage || m.is_you) && (
                  <Button
                    size="small" color="error" disabled={remove.isPending}
                    onClick={() => remove.mutate({ userId: m.user_id, you: m.is_you })}
                  >
                    {m.is_you ? t('member.leave') : t('member.remove')}
                  </Button>
                )}
              </Box>
            ))}
          </Box>
        )}
        {canManage ? (
          <Box sx={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <TextField
              select size="small" label={t('member.person')} value={person} sx={{ flex: 1, minWidth: 200 }}
              helperText={t('member.peopleHint')}
              onChange={(e) => setPerson(e.target.value)}
            >
              {choices.map((p) => (
                <MenuItem key={p.id} value={String(p.id)}>
                  <Box>
                    <Box sx={{ fontSize: 14 }}>{p.display_name || p.email}</Box>
                    {p.display_name && <Box sx={{ fontSize: 12, color: ds.textMuted }}>{p.email}</Box>}
                  </Box>
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select size="small" label={t('member.roleLabel')} value={role} sx={{ width: 130 }}
              onChange={(e) => setRole(e.target.value as ProjectRole)}
            >
              {ROLES.map((r) => <MenuItem key={r} value={r}>{t(`member.role.${r}`)}</MenuItem>)}
            </TextField>
            <Button variant="contained" disabled={person === '' || add.isPending} onClick={() => add.mutate()} sx={{ height: 40 }}>
              {t('member.add')}
            </Button>
          </Box>
        ) : (
          members.data && <Box sx={{ fontSize: 12, color: ds.textMuted }}>{t('member.managerOnly')}</Box>
        )}
      </DialogContent>
      <DialogActions sx={{ px: '24px', pb: '18px' }}>
        <Button onClick={onClose} sx={{ color: ds.textSub }}>{t('member.close')}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default ProjectMembersDialog;
