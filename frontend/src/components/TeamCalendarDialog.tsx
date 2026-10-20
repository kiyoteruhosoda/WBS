// チームの稼働する曜日・休日と、各人の休み（task #554、ADR-0058 決定 2）。
// どれもいちばん上のプロジェクトに付き、終わる見込みの日の計算で「作業しない日」として数える。
// 曜日とチームの休日は管理者だけ、各人の休みは本人と管理者が入れられる（休みは日付だけ。プロジェクトをまたいで同じ）。
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, IconButton,
  TextField, ToggleButton, ToggleButtonGroup,
} from '@mui/material';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import {
  addMemberLeave, addTeamDayOff, getProjectMembers, getTeamCalendar, importTeamJapaneseHolidays, projectMembersKey,
  removeMemberLeave, removeTeamDayOff, setTeamWorkdays, teamCalendarKey,
} from '../api/projects';
import type { Project, TeamCalendar, WeekdayCode } from '../types';
import { WEEKDAY_CODES } from '../calendar/eventForm';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { todayDate } from '../utils/format';

interface Props {
  project: Project | null;
  /** いちばん上のプロジェクトの名前（説明に出す） */
  rootName: string;
  onClose: () => void;
}

const WEEKDAYS_IN_ORDER: readonly WeekdayCode[] = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'];

const errorKey = (error: unknown) => {
  const status = isAxiosError(error) ? error.response?.status : undefined;
  if (status === 403) return 'teamCalendar.managerOnly' as const;
  return 'teamCalendar.error' as const;
};

const parseDay = (day: string): Date => {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d);
};

const TeamCalendarDialog: React.FC<Props> = ({ project, rootName, onClose }) => {
  const { t, weekdays } = useI18n();
  const qc = useQueryClient();
  const projectId = project?.id ?? 0;
  const calendar = useQuery({
    queryKey: teamCalendarKey(projectId),
    queryFn: () => getTeamCalendar(projectId),
    enabled: project !== null,
  });
  const members = useQuery({
    queryKey: projectMembersKey(projectId),
    queryFn: () => getProjectMembers(projectId),
    enabled: project !== null,
  });
  const [year, setYear] = useState(() => todayDate().getFullYear());
  const [newDay, setNewDay] = useState('');
  const [newName, setNewName] = useState('');
  const [leaveDraft, setLeaveDraft] = useState<Record<number, string>>({});

  const canManage = calendar.data?.can_manage ?? false;
  const inYear = (day: string) => day.startsWith(`${year}-`);
  const label = (day: string) => {
    const d = parseDay(day);
    return t('teamCalendar.dayLabel', { month: d.getMonth() + 1, day: d.getDate(), weekday: weekdays[d.getDay()] });
  };
  const leaveByUser = useMemo(() => {
    const map = new Map<number, string[]>();
    for (const l of calendar.data?.leave ?? []) {
      if (!l.day.startsWith(`${year}-`)) continue;
      map.set(l.user_id, [...(map.get(l.user_id) ?? []), l.day]);
    }
    return map;
  }, [calendar.data, year]);

  const saved = (data: TeamCalendar) => {
    qc.setQueryData(teamCalendarKey(projectId), data);
    // 見込みの終わりが変わる
    qc.invalidateQueries({ queryKey: ['tasks'] });
    qc.invalidateQueries({ queryKey: ['milestones'] });
  };
  const workdays = useMutation({
    mutationFn: (next: WeekdayCode[]) => setTeamWorkdays(projectId, next),
    onSuccess: saved,
  });
  const addDay = useMutation({
    mutationFn: () => addTeamDayOff(projectId, newDay, newName.trim() || null),
    onSuccess: (data) => { setNewDay(''); setNewName(''); saved(data); },
  });
  const removeDay = useMutation({ mutationFn: (day: string) => removeTeamDayOff(projectId, day), onSuccess: saved });
  const importJapan = useMutation({ mutationFn: () => importTeamJapaneseHolidays(projectId, year), onSuccess: saved });
  const addLeave = useMutation({
    mutationFn: ({ userId, day }: { userId: number; day: string }) => addMemberLeave(projectId, userId, day),
    onSuccess: (data, { userId }) => { setLeaveDraft((d) => ({ ...d, [userId]: '' })); saved(data); },
  });
  const removeLeave = useMutation({
    mutationFn: ({ userId, day }: { userId: number; day: string }) => removeMemberLeave(projectId, userId, day),
    onSuccess: saved,
  });
  const failed = [workdays, addDay, removeDay, importJapan, addLeave, removeLeave].find((m) => m.isError);

  const sectionTitle = (text: string) => (
    <Box component="h3" sx={{ fontSize: 14, fontWeight: 700, color: ds.text, m: 0 }}>{text}</Box>
  );

  return (
    <Dialog open={project !== null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('teamCalendar.title')}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '16px', pt: '4px !important' }}>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('teamCalendar.hint', { name: rootName })}</Box>
        {failed && <Alert severity="error">{t(errorKey(failed.error))}</Alert>}
        {calendar.isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}><CircularProgress size={24} /></Box>}
        {calendar.data && (
          <>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {sectionTitle(t('teamCalendar.workdays'))}
              <ToggleButtonGroup
                size="small" value={calendar.data.workdays} disabled={!canManage || workdays.isPending}
                aria-label={t('teamCalendar.workdays')} sx={{ flexWrap: 'wrap' }}
                onChange={(_, next: WeekdayCode[]) => { if (next.length > 0) workdays.mutate(next); }}
              >
                {WEEKDAYS_IN_ORDER.map((code) => (
                  <ToggleButton key={code} value={code} sx={{ minWidth: 40 }}>
                    {weekdays[WEEKDAY_CODES.indexOf(code)]}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
              <Box sx={{ fontSize: 12, color: ds.textMuted }}>{t('teamCalendar.workdaysHint')}</Box>
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <IconButton size="small" aria-label={t('teamCalendar.prevYear')} onClick={() => setYear((y) => y - 1)}>
                <ChevronLeftIcon fontSize="small" />
              </IconButton>
              <Box sx={{ fontSize: 14, fontWeight: 700, minWidth: 64, textAlign: 'center' }}>{t('teamCalendar.year', { year })}</Box>
              <IconButton size="small" aria-label={t('teamCalendar.nextYear')} onClick={() => setYear((y) => y + 1)}>
                <ChevronRightIcon fontSize="small" />
              </IconButton>
            </Box>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {sectionTitle(t('teamCalendar.daysOff'))}
              {calendar.data.days_off.filter((d) => inYear(d.day)).length === 0 ? (
                <Box sx={{ fontSize: 13, color: ds.textMuted }}>{t('teamCalendar.noDaysOff')}</Box>
              ) : (
                <Box component="ul" aria-label={t('teamCalendar.daysOff')} sx={{ listStyle: 'none', m: 0, p: 0, display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {calendar.data.days_off.filter((d) => inYear(d.day)).map((d) => (
                    <Box component="li" key={d.day}>
                      <Chip
                        size="small" variant="outlined"
                        label={d.name ? `${label(d.day)} ${d.name}` : label(d.day)}
                        onDelete={canManage ? () => removeDay.mutate(d.day) : undefined}
                      />
                    </Box>
                  ))}
                </Box>
              )}
              {canManage && (
                <Box sx={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <TextField
                    size="small" type="date" label={t('teamCalendar.day')} value={newDay}
                    slotProps={{ inputLabel: { shrink: true } }} sx={{ width: 170 }}
                    onChange={(e) => setNewDay(e.target.value)}
                  />
                  <TextField
                    size="small" label={t('teamCalendar.dayName')} value={newName} sx={{ flex: 1, minWidth: 140 }}
                    slotProps={{ htmlInput: { maxLength: 100 } }}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                  <Button variant="outlined" disabled={newDay === '' || addDay.isPending} onClick={() => addDay.mutate()}>
                    {t('teamCalendar.add')}
                  </Button>
                  <Button size="small" disabled={importJapan.isPending} onClick={() => importJapan.mutate()}>
                    {t('teamCalendar.importJapan', { year })}
                  </Button>
                </Box>
              )}
            </Box>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {sectionTitle(t('teamCalendar.leave'))}
              <Box sx={{ fontSize: 12, color: ds.textMuted }}>{t('teamCalendar.leaveHint')}</Box>
              <Box component="ul" aria-label={t('teamCalendar.leave')} sx={{ listStyle: 'none', m: 0, p: 0, border: `1px solid ${ds.border}`, borderRadius: '8px' }}>
                {(members.data?.members ?? []).map((m) => {
                  const editable = canManage || m.is_you;
                  const days = leaveByUser.get(m.user_id) ?? [];
                  const draft = leaveDraft[m.user_id] ?? '';
                  const name = m.display_name || m.email;
                  return (
                    <Box
                      component="li" key={m.user_id}
                      sx={{
                        display: 'flex', flexDirection: 'column', gap: '6px', px: '12px', py: '8px',
                        borderTop: `1px solid ${ds.borderPale}`, '&:first-of-type': { borderTop: 'none' },
                      }}
                    >
                      <Box sx={{ fontSize: 14, fontWeight: 600, color: ds.text }}>
                        {name}{m.is_you && <Box component="span" sx={{ fontWeight: 400, color: ds.textMuted }}>{`（${t('member.you')}）`}</Box>}
                      </Box>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
                        {days.length === 0 && <Box sx={{ fontSize: 13, color: ds.textMuted }}>{t('teamCalendar.noLeave')}</Box>}
                        {days.map((day) => (
                          <Chip
                            key={day} size="small" variant="outlined" label={label(day)}
                            onDelete={editable ? () => removeLeave.mutate({ userId: m.user_id, day }) : undefined}
                          />
                        ))}
                      </Box>
                      {editable && (
                        <Box sx={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                          <TextField
                            size="small" type="date" label={t('teamCalendar.day')} value={draft}
                            slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': t('teamCalendar.leaveDayOf', { name }) } }}
                            sx={{ width: 170 }}
                            onChange={(e) => setLeaveDraft((d) => ({ ...d, [m.user_id]: e.target.value }))}
                          />
                          <Button
                            variant="outlined" size="small" disabled={draft === '' || addLeave.isPending}
                            onClick={() => addLeave.mutate({ userId: m.user_id, day: draft })}
                          >
                            {t('teamCalendar.add')}
                          </Button>
                        </Box>
                      )}
                    </Box>
                  );
                })}
              </Box>
            </Box>
          </>
        )}
      </DialogContent>
      <DialogActions sx={{ px: '24px', pb: '18px' }}>
        <Button onClick={onClose} sx={{ color: ds.textSub }}>{t('member.close')}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default TeamCalendarDialog;
