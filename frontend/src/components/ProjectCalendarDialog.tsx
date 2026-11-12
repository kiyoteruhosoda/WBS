// Project calendar (task #557 / ADR-0059 decision 1; originally "working days and time off" from #554).
// - Working weekdays: one set on the top-level project (the root's, from any level)
// - Holidays and working days (work on a non-working weekday. ADR-0060) are added to the opened project. Those of parents (ancestors) are inherited
//   and the same day can be reversed here (the nearest wins). A parent's entries can't be deleted here
// - In forecast calculation, tasks of this project and its sub-projects don't progress on holidays and do on working days
// Only admins can change it. Each person's time off is entered in "their calendar", opened from their row in the people list.
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  TextField, ToggleButton, ToggleButtonGroup,
} from '@mui/material';
import {
  addExtraWorkday, addTeamDayOff, getTeamCalendar, importTeamJapaneseHolidays, removeExtraWorkday, removeTeamDayOff,
  setTeamWorkdays, teamCalendarKey,
} from '../api/projects';
import type { Project, TeamCalendar, WeekdayCode } from '../types';
import { WEEKDAYS_SUNDAY_FIRST as WEEKDAY_CODES } from '../calendar/projectCalendarDays';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { todayDate } from '../utils/format';
import MonthCalendarPicker from './calendar/MonthCalendarPicker';
import type { DayMark } from './calendar/MonthCalendarPicker';

interface Props {
  project: Project | null;
  /** Name of the top-level project (shown in the weekday description) */
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

const ProjectCalendarDialog: React.FC<Props> = ({ project, rootName, onClose }) => {
  const { t, weekdays } = useI18n();
  const qc = useQueryClient();
  const projectId = project?.id ?? 0;
  const calendar = useQuery({
    queryKey: teamCalendarKey(projectId),
    queryFn: () => getTeamCalendar(projectId),
    enabled: project !== null,
  });
  const [month, setMonth] = useState(() => {
    const today = todayDate();
    return new Date(today.getFullYear(), today.getMonth(), 1);
  });
  const year = month.getFullYear();
  const [newDay, setNewDay] = useState('');
  const [newName, setNewName] = useState('');

  const canManage = calendar.data?.can_manage ?? false;
  const label = (day: string) => {
    const d = parseDay(day);
    return t('teamCalendar.dayLabel', { month: d.getMonth() + 1, day: d.getDate(), weekday: weekdays[d.getDay()] });
  };
  const dayOffByDate = useMemo(() => new Map((calendar.data?.days_off ?? []).map((d) => [d.day, d])), [calendar.data]);
  const workdayByDate = useMemo(() => new Map((calendar.data?.extra_workdays ?? []).map((d) => [d.day, d])), [calendar.data]);
  const workdaySet = useMemo(() => new Set(calendar.data?.workdays ?? []), [calendar.data]);

  const saved = (data: TeamCalendar) => {
    qc.setQueryData(teamCalendarKey(projectId), data);
    // Sub-project calendars and forecast end dates change
    qc.invalidateQueries({ queryKey: ['projects'] });
    qc.invalidateQueries({ queryKey: ['tasks'] });
    qc.invalidateQueries({ queryKey: ['milestones'] });
  };
  const workdays = useMutation({
    mutationFn: (next: WeekdayCode[]) => setTeamWorkdays(projectId, next),
    onSuccess: saved,
  });
  const addDay = useMutation({
    mutationFn: ({ day, name }: { day: string; name: string | null }) => addTeamDayOff(projectId, day, name),
    onSuccess: (data) => { setNewDay(''); setNewName(''); saved(data); },
  });
  const removeDay = useMutation({ mutationFn: (day: string) => removeTeamDayOff(projectId, day), onSuccess: saved });
  const addWork = useMutation({ mutationFn: (day: string) => addExtraWorkday(projectId, day, null), onSuccess: saved });
  const removeWork = useMutation({ mutationFn: (day: string) => removeExtraWorkday(projectId, day), onSuccess: saved });
  const importJapan = useMutation({ mutationFn: () => importTeamJapaneseHolidays(projectId, year), onSuccess: saved });
  const failed = [workdays, addDay, removeDay, addWork, removeWork, importJapan].find((m) => m.isError);
  const busy = addDay.isPending || removeDay.isPending || addWork.isPending || removeWork.isPending;
  const isUsualWorkday = (day: string) => workdaySet.has(WEEKDAY_CODES[parseDay(day).getDay()]);

  const markOf = (day: string): DayMark | null => {
    const off = dayOffByDate.get(day);
    if (off) return { tone: off.inherited ? 'inherited' : 'off', label: off.inherited ? t('projectCalendar.inheritedOff') : (off.name || t('projectCalendar.dayOff')) };
    const work = workdayByDate.get(day);
    if (work) return { tone: work.inherited ? 'inherited' : 'work', label: work.inherited ? t('projectCalendar.inheritedWork') : (work.name || t('projectCalendar.extraWorkday')) };
    if (!isUsualWorkday(day)) return { tone: 'quiet', label: t('projectCalendar.nonWorking') };
    return null;
  };
  // Remove our own entry (back to the parent's / the weekday default). Otherwise make it a holiday if it's a working day, or a working day if not
  const pick = (day: string) => {
    const off = dayOffByDate.get(day);
    const work = workdayByDate.get(day);
    if (off && !off.inherited) removeDay.mutate(day);
    else if (work && !work.inherited) removeWork.mutate(day);
    else if (off || (!work && !isUsualWorkday(day))) addWork.mutate(day);
    else addDay.mutate({ day, name: null });
  };
  const daysInYear = (calendar.data?.days_off ?? []).filter((d) => d.day.startsWith(`${year}-`));
  const workdaysInYear = (calendar.data?.extra_workdays ?? []).filter((d) => d.day.startsWith(`${year}-`));

  const sectionTitle = (text: string) => (
    <Box component="h3" sx={{ fontSize: 14, fontWeight: 700, color: ds.text, m: 0 }}>{text}</Box>
  );

  return (
    <Dialog open={project !== null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('projectCalendar.title', { name: project?.name ?? '' })}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '16px', pt: '4px !important' }}>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('projectCalendar.hint')}</Box>
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
              <Box sx={{ fontSize: 12, color: ds.textMuted }}>{t('projectCalendar.workdaysHint', { name: rootName })}</Box>
            </Box>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {sectionTitle(t('projectCalendar.daysOff'))}
              <Box sx={{ fontSize: 12, color: ds.textMuted }}>
                {canManage ? t('projectCalendar.pickHint') : t('teamCalendar.managerOnly')}
              </Box>
              <MonthCalendarPicker
                month={month} onMonthChange={setMonth} markOf={markOf}
                onPick={pick} disabled={!canManage || busy}
                ariaLabel={t('projectCalendar.daysOff')}
              />
            </Box>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {sectionTitle(t('projectCalendar.listTitle', { year }))}
              {daysInYear.length === 0 ? (
                <Box sx={{ fontSize: 13, color: ds.textMuted }}>{t('teamCalendar.noDaysOff')}</Box>
              ) : (
                <Box component="ul" aria-label={t('projectCalendar.listTitle', { year })} sx={{ listStyle: 'none', m: 0, p: 0, display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {daysInYear.map((d) => {
                    const text = [label(d.day), d.name, d.inherited ? `（${t('projectCalendar.inherited')}）` : null].filter(Boolean).join(' ');
                    return (
                      <Box component="li" key={d.day}>
                        <Chip
                          size="small" variant="outlined" label={text}
                          onDelete={canManage && !d.inherited ? () => removeDay.mutate(d.day) : undefined}
                        />
                      </Box>
                    );
                  })}
                </Box>
              )}
              {workdaysInYear.length > 0 && (
                <Box component="ul" aria-label={t('projectCalendar.workListTitle', { year })} sx={{ listStyle: 'none', m: 0, p: 0, display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {workdaysInYear.map((d) => {
                    const text = [label(d.day), d.name || t('projectCalendar.extraWorkday'), d.inherited ? `（${t('projectCalendar.inherited')}）` : null].filter(Boolean).join(' ');
                    return (
                      <Box component="li" key={d.day}>
                        <Chip
                          size="small" variant="outlined" color="success" label={text}
                          onDelete={canManage && !d.inherited ? () => removeWork.mutate(d.day) : undefined}
                        />
                      </Box>
                    );
                  })}
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
                  <Button
                    variant="outlined" disabled={newDay === '' || addDay.isPending}
                    onClick={() => addDay.mutate({ day: newDay, name: newName.trim() || null })}
                  >
                    {t('teamCalendar.add')}
                  </Button>
                  <Button size="small" disabled={importJapan.isPending} onClick={() => importJapan.mutate()}>
                    {t('teamCalendar.importJapan', { year })}
                  </Button>
                </Box>
              )}
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

export default ProjectCalendarDialog;
