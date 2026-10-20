// プロジェクトのカレンダー（task #557 / ADR-0059 決定 1。もとは #554 の「稼働日と休み」）。
// - 稼働する曜日はいちばん上のプロジェクトに 1 つ（どの段から開いても根のもの）
// - 休日は開いたプロジェクトに足す。親（先祖）の休日は引き継ぎ、ここでは消せない
// - 終わる見込みの計算では、そのプロジェクトと下のプロジェクトのタスクは休日に進まない
// 変えられるのは管理者だけ。各人の休みは人の一覧の行から開く「その人のカレンダー」で入れる。
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  TextField, ToggleButton, ToggleButtonGroup,
} from '@mui/material';
import {
  addTeamDayOff, getTeamCalendar, importTeamJapaneseHolidays, removeTeamDayOff, setTeamWorkdays, teamCalendarKey,
} from '../api/projects';
import type { Project, TeamCalendar, WeekdayCode } from '../types';
import { WEEKDAY_CODES } from '../calendar/eventForm';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { todayDate } from '../utils/format';
import MonthCalendarPicker from './calendar/MonthCalendarPicker';
import type { DayMark } from './calendar/MonthCalendarPicker';

interface Props {
  project: Project | null;
  /** いちばん上のプロジェクトの名前（曜日の説明に出す） */
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
  const workdaySet = useMemo(() => new Set(calendar.data?.workdays ?? []), [calendar.data]);

  const saved = (data: TeamCalendar) => {
    qc.setQueryData(teamCalendarKey(projectId), data);
    // 下のプロジェクトのカレンダーと、見込みの終わりが変わる
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
  const importJapan = useMutation({ mutationFn: () => importTeamJapaneseHolidays(projectId, year), onSuccess: saved });
  const failed = [workdays, addDay, removeDay, importJapan].find((m) => m.isError);
  const busy = addDay.isPending || removeDay.isPending;

  const markOf = (day: string): DayMark | null => {
    const off = dayOffByDate.get(day);
    if (off) return { tone: off.inherited ? 'inherited' : 'off', label: off.inherited ? t('projectCalendar.inherited') : (off.name || t('projectCalendar.dayOff')) };
    if (!workdaySet.has(WEEKDAY_CODES[parseDay(day).getDay()])) return { tone: 'quiet', label: t('projectCalendar.nonWorking') };
    return null;
  };
  const pick = (day: string) => {
    const off = dayOffByDate.get(day);
    if (off?.inherited) return;
    if (off) removeDay.mutate(day);
    else addDay.mutate({ day, name: null });
  };
  const daysInYear = (calendar.data?.days_off ?? []).filter((d) => d.day.startsWith(`${year}-`));

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
                isLocked={(day) => dayOffByDate.get(day)?.inherited ?? false}
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
