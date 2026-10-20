// プロジェクトのメンバー＝人の一覧（task #544、ADR-0055。一覧の入力は task #557、ADR-0059）。
// メンバーはいちばん上のプロジェクトに付くので、どの段から開いても根の名簿を出す。
// 加える・外す・役割を変えるのは管理者だけ。メンバーは自分だけ「抜ける」ができる。
// 1 日の工数と従事率（task #554、ADR-0058）は管理者がだれのでも、メンバーは自分のだけ直せる。
// 一覧はセルを直接書き換える（Enter・Tab で次へ、その場で保存、表計算から貼り付け）。行の「カレンダー」でその人の休みを入れる。
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, TextField,
} from '@mui/material';
import {
  addProjectMember, changeProjectMemberCapacity, changeProjectMemberRole, getPeople, getProjectMembers, projectMembersKey, removeProjectMember,
  PEOPLE_KEY, PROJECTS_KEY,
} from '../api/projects';
import type { Project, ProjectMember, ProjectMembers, ProjectRole } from '../types';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import EditableGrid from './grid/EditableGrid';
import type { GridColumn } from './grid/EditableGrid';
import { parseChoice, parseNumber } from './grid/gridModel';
import PersonCalendarDialog from './PersonCalendarDialog';

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
  const capacity = useMutation({
    mutationFn: ({ userId, daily, engagement }: { userId: number; daily: number; engagement: number }) => (
      changeProjectMemberCapacity(projectId, userId, daily, engagement)
    ),
    onSuccess: (data) => {
      // 貼り付けで同じ行の 2 つの列を続けて直すとき、次の保存が今の値を読めるよう先に入れる
      qc.setQueryData(projectMembersKey(projectId), data);
      // 見込みの終わりが変わる
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['milestones'] });
    },
  });
  const remove = useMutation({
    mutationFn: ({ userId }: { userId: number; you: boolean }) => removeProjectMember(projectId, userId),
    onSuccess: (_, { you }) => { changed(); if (you) onClose(); },
  });
  const failed = [add, changeRole, remove].find((m) => m.isError);
  const [calendarOf, setCalendarOf] = useState<ProjectMember | null>(null);

  /** 1 つのセルを保存する。1 日の工数と従事率は 2 つで 1 組なので、もう片方は今の値（保存したばかりのものを含む） */
  const commit = async (member: ProjectMember, key: string, value: unknown) => {
    if (key === 'role') {
      await changeRole.mutateAsync({ userId: member.user_id, next: value as ProjectRole });
      return;
    }
    const latest = qc.getQueryData<ProjectMembers>(projectMembersKey(projectId))?.members
      .find((m) => m.user_id === member.user_id) ?? member;
    await capacity.mutateAsync({
      userId: member.user_id,
      daily: key === 'daily' ? value as number : latest.daily_hours,
      engagement: key === 'engagement' ? value as number : latest.engagement_percent,
    });
  };
  const roleOptions = ROLES.map((r) => ({ value: r, label: t(`member.role.${r}`) }));
  const nameOf = (m: ProjectMember) => m.display_name || m.email;
  const columns: GridColumn<ProjectMember>[] = [
    {
      key: 'name', header: t('member.name'), width: 190, kind: 'readonly',
      value: nameOf,
      display: (m) => (
        <>
          {nameOf(m)}
          {m.is_you && <Box component="span" sx={{ color: ds.textMuted }}>{`（${t('member.you')}）`}</Box>}
        </>
      ),
    },
    {
      key: 'role', header: t('member.roleLabel'), width: 100, kind: 'select',
      value: (m) => m.role, display: (m) => t(`member.role.${m.role}`),
      options: () => roleOptions, editable: () => canManage,
      parse: (raw) => parseChoice(raw, roleOptions),
    },
    {
      key: 'daily', header: t('member.dailyHoursShort'), hint: t('member.dailyHours'), width: 96, kind: 'number', align: 'right',
      value: (m) => String(m.daily_hours), editable: (m) => canManage || m.is_you,
      parse: (raw) => parseNumber(raw, { min: 0, max: 24 }),
    },
    {
      key: 'engagement', header: t('member.engagement'), width: 90, kind: 'number', align: 'right',
      value: (m) => String(m.engagement_percent), editable: (m) => canManage || m.is_you,
      parse: (raw) => parseNumber(raw, { min: 0, max: 100, integer: true }),
    },
    {
      key: 'perDay', header: t('member.perDayShort'), width: 104, kind: 'readonly', align: 'right',
      value: (m) => String(Math.round(m.daily_hours * m.engagement_percent) / 100),
      display: (m) => t('member.hours', { hours: Math.round(m.daily_hours * m.engagement_percent) / 100 }),
    },
    {
      key: 'calendar', header: t('member.calendar'), width: 110, kind: 'readonly',
      value: () => '',
      onActivate: (m) => setCalendarOf(m),
      display: (m) => (
        <Button size="small" variant="text" tabIndex={-1} onClick={() => setCalendarOf(m)} sx={{ minWidth: 0, px: '6px', fontSize: 12 }}>
          {t('member.openCalendar')}
        </Button>
      ),
    },
    {
      key: 'remove', header: '', width: 84, kind: 'readonly',
      value: () => '',
      onActivate: (m) => { if (canManage || m.is_you) remove.mutate({ userId: m.user_id, you: m.is_you }); },
      display: (m) => (canManage || m.is_you) && (
        <Button
          size="small" color="error" tabIndex={-1} disabled={remove.isPending} sx={{ minWidth: 0, px: '6px', fontSize: 12 }}
          onClick={() => remove.mutate({ userId: m.user_id, you: m.is_you })}
        >
          {m.is_you ? t('member.leave') : t('member.remove')}
        </Button>
      ),
    },
  ];

  return (
    <Dialog open={project !== null} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('member.title')}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '14px', pt: '4px !important' }}>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('member.hint', { name: rootName })}</Box>
        <Box sx={{ fontSize: 12, color: ds.textMuted }}>{t('member.capacityHint')}</Box>
        {failed && <Alert severity="error">{t(errorKey(failed.error))}</Alert>}
        {members.isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}><CircularProgress size={24} /></Box>}
        {members.data && (
          <Box sx={{ overflowX: 'auto', border: `1px solid ${ds.border}`, borderRadius: '8px' }}>
            <EditableGrid
              rows={members.data.members} rowKey={(m) => m.user_id} rowLabel={nameOf}
              columns={columns} onCommit={commit} ariaLabel={t('member.title')}
            />
          </Box>
        )}
        <Box sx={{ fontSize: 12, color: ds.textMuted }}>{t('grid.howTo')}</Box>
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
      <PersonCalendarDialog
        projectId={projectId} member={calendarOf} editable={calendarOf !== null && (canManage || calendarOf.is_you)}
        onClose={() => setCalendarOf(null)}
      />
    </Dialog>
  );
};

export default ProjectMembersDialog;
