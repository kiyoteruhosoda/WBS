// その人のカレンダー（task #557 / ADR-0059 決定 2。人の一覧の行から開く）。
// 日を押すたびに「休み（終日）→ 半休 → なし」と切り替わる。休みは人に付き、ほかのプロジェクトでも同じ日が休みになる。
// プロジェクトの休日と稼働しない曜日は薄く出す（ここでは変えない）。入れられるのは本人と管理者だけ。
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
import { addMemberLeave, getTeamCalendar, removeMemberLeave, teamCalendarKey } from '../api/projects';
import type { ProjectMember, TeamCalendar } from '../types';
import { WEEKDAY_CODES } from '../calendar/eventForm';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { todayDate } from '../utils/format';
import MonthCalendarPicker from './calendar/MonthCalendarPicker';
import type { DayMark } from './calendar/MonthCalendarPicker';

interface Props {
  projectId: number;
  member: ProjectMember | null;
  /** 直せるか（本人か管理者） */
  editable: boolean;
  onClose: () => void;
}

const FULL = 100;
const HALF = 50;

const parseDay = (day: string): Date => {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d);
};

const PersonCalendarDialog: React.FC<Props> = ({ projectId, member, editable, onClose }) => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const calendar = useQuery({
    queryKey: teamCalendarKey(projectId),
    queryFn: () => getTeamCalendar(projectId),
    enabled: member !== null,
  });
  const [month, setMonth] = useState(() => {
    const today = todayDate();
    return new Date(today.getFullYear(), today.getMonth(), 1);
  });
  const userId = member?.user_id ?? 0;
  const leave = useMemo(
    () => new Map((calendar.data?.leave ?? []).filter((l) => l.user_id === userId).map((l) => [l.day, l.off_percent])),
    [calendar.data, userId],
  );
  const dayOff = useMemo(() => new Map((calendar.data?.days_off ?? []).map((d) => [d.day, d])), [calendar.data]);
  const workdays = useMemo(() => new Set(calendar.data?.workdays ?? []), [calendar.data]);

  const saved = (data: TeamCalendar) => {
    qc.setQueryData(teamCalendarKey(projectId), data);
    // 休みは人に付くので、ほかのプロジェクトのカレンダーと見込みも変わる
    qc.invalidateQueries({ queryKey: ['projects'] });
    qc.invalidateQueries({ queryKey: ['tasks'] });
    qc.invalidateQueries({ queryKey: ['milestones'] });
  };
  const change = useMutation({
    mutationFn: ({ day, next }: { day: string; next: number | null }) => (
      next === null ? removeMemberLeave(projectId, userId, day) : addMemberLeave(projectId, userId, day, next)
    ),
    onSuccess: saved,
  });

  const markOf = (day: string): DayMark | null => {
    const off = leave.get(day);
    if (off !== undefined) return off >= FULL ? { tone: 'off', label: t('personCalendar.full') } : { tone: 'half', label: t('personCalendar.half') };
    const projectOff = dayOff.get(day);
    if (projectOff) return { tone: 'quiet', label: projectOff.name || t('projectCalendar.dayOff') };
    if (!workdays.has(WEEKDAY_CODES[parseDay(day).getDay()])) return { tone: 'quiet', label: t('projectCalendar.nonWorking') };
    return null;
  };
  // なし → 終日 → 半休 → なし
  const pick = (day: string) => {
    const off = leave.get(day);
    const next = off === undefined ? FULL : off >= FULL ? HALF : null;
    change.mutate({ day, next });
  };
  const name = member ? member.display_name || member.email : '';
  const forbidden = change.isError && isAxiosError(change.error) && change.error.response?.status === 403;

  return (
    <Dialog open={member !== null} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('personCalendar.title', { name })}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '12px', pt: '4px !important' }}>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('personCalendar.hint')}</Box>
        {!editable && <Box sx={{ fontSize: 12, color: ds.textMuted }}>{t('personCalendar.readOnly')}</Box>}
        {change.isError && <Alert severity="error">{t(forbidden ? 'teamCalendar.managerOnly' : 'teamCalendar.error')}</Alert>}
        {calendar.isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}><CircularProgress size={24} /></Box>}
        {calendar.data && (
          <MonthCalendarPicker
            month={month} onMonthChange={setMonth} markOf={markOf} onPick={pick}
            disabled={!editable || change.isPending}
            ariaLabel={t('personCalendar.title', { name })}
          />
        )}
        <Box sx={{ display: 'flex', gap: '12px', flexWrap: 'wrap', fontSize: 12, color: ds.textSub }}>
          <span>{t('personCalendar.legend')}</span>
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: '24px', pb: '18px' }}>
        <Button onClick={onClose} sx={{ color: ds.textSub }}>{t('member.close')}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default PersonCalendarDialog;
