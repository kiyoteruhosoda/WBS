// その人のカレンダー（task #557 / ADR-0059 決定 2、task #558 / ADR-0060。人の一覧の行から開く）。
// プロジェクトのカレンダー（稼働する曜日・休日・稼働日）を引き継いで下敷きに出し、その人だけの違いを上に重ねる:
// 休み・半休・その日の稼働時間（残業・短い日。稼働しない日なら休日出勤）。日を押すと小さなメニューで選ぶ。
// 違いは人に付き、ほかのプロジェクトでも同じ。入れられるのは本人と管理者だけ。
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Menu, MenuItem, TextField,
} from '@mui/material';
import { addMemberLeave, getTeamCalendar, removeMemberLeave, teamCalendarKey } from '../api/projects';
import type { ProjectMember, TeamCalendar } from '../types';
import { WEEKDAY_CODES } from '../calendar/eventForm';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { todayDate } from '../utils/format';
import MonthCalendarPicker from './calendar/MonthCalendarPicker';
import type { DayMark } from './calendar/MonthCalendarPicker';
import { parseNumber } from './grid/gridModel';

interface Props {
  projectId: number;
  member: ProjectMember | null;
  /** 直せるか（本人か管理者） */
  editable: boolean;
  onClose: () => void;
}

const FULL = 100;
const HALF = 50;

type Change =
  | { kind: 'off'; offPercent: number }
  | { kind: 'hours'; hours: number }
  | { kind: 'clear' };

const parseDay = (day: string): Date => {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d);
};

const PersonCalendarDialog: React.FC<Props> = ({ projectId, member, editable, onClose }) => {
  const { t, weekdays } = useI18n();
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
  const [menu, setMenu] = useState<{ day: string; anchor: HTMLElement } | null>(null);
  const [custom, setCustom] = useState<{ day: string; draft: string } | null>(null);
  const userId = member?.user_id ?? 0;
  const usualHours = member?.daily_hours ?? 8;
  const mine = useMemo(
    () => new Map((calendar.data?.leave ?? []).filter((l) => l.user_id === userId).map((l) => [l.day, l])),
    [calendar.data, userId],
  );
  const dayOff = useMemo(() => new Map((calendar.data?.days_off ?? []).map((d) => [d.day, d])), [calendar.data]);
  const extraWork = useMemo(() => new Map((calendar.data?.extra_workdays ?? []).map((d) => [d.day, d])), [calendar.data]);
  const workdays = useMemo(() => new Set(calendar.data?.workdays ?? []), [calendar.data]);

  /** プロジェクトのカレンダーでその日に働くか（その人の違いを重ねる前） */
  const projectWorks = (day: string) => {
    if (extraWork.has(day)) return true;
    if (dayOff.has(day)) return false;
    return workdays.has(WEEKDAY_CODES[parseDay(day).getDay()]);
  };

  const saved = (data: TeamCalendar) => {
    qc.setQueryData(teamCalendarKey(projectId), data);
    // 違いは人に付くので、ほかのプロジェクトのカレンダーと見込みも変わる
    qc.invalidateQueries({ queryKey: ['projects'] });
    qc.invalidateQueries({ queryKey: ['tasks'] });
    qc.invalidateQueries({ queryKey: ['milestones'] });
  };
  const change = useMutation({
    mutationFn: ({ day, next }: { day: string; next: Change }) => {
      if (next.kind === 'clear') return removeMemberLeave(projectId, userId, day);
      if (next.kind === 'hours') return addMemberLeave(projectId, userId, day, FULL, next.hours);
      return addMemberLeave(projectId, userId, day, next.offPercent);
    },
    onSuccess: saved,
  });
  const apply = (day: string, next: Change) => { setMenu(null); change.mutate({ day, next }); };

  const hoursLabel = (hours: number, works: boolean) => {
    if (hours <= 0) return t('personCalendar.full');
    if (!works) return t('personCalendar.holidayWork', { hours });
    if (hours > usualHours) return t('personCalendar.overtime', { hours });
    return t('personCalendar.hours', { hours });
  };
  const markOf = (day: string): DayMark | null => {
    const own = mine.get(day);
    const works = projectWorks(day);
    if (own) {
      if (own.hours !== null) {
        const tone = own.hours <= 0 ? 'off' : !works || own.hours > usualHours ? 'work' : own.hours < usualHours ? 'half' : 'work';
        return { tone, label: hoursLabel(own.hours, works) };
      }
      if (!works) return { tone: 'quiet', label: t('projectCalendar.nonWorking') };
      return own.off_percent >= FULL
        ? { tone: 'off', label: t('personCalendar.full') }
        : { tone: 'half', label: own.off_percent === HALF ? t('personCalendar.half') : t('personCalendar.offPercent', { percent: own.off_percent }) };
    }
    // ここから下はプロジェクトのカレンダーから引き継いだもの
    const off = dayOff.get(day);
    if (off) return { tone: 'quiet', label: off.name || t('projectCalendar.dayOff') };
    const work = extraWork.get(day);
    if (work) return { tone: 'inherited', label: work.name || t('projectCalendar.extraWorkday') };
    if (!works) return { tone: 'quiet', label: t('projectCalendar.nonWorking') };
    return null;
  };

  const name = member ? member.display_name || member.email : '';
  const forbidden = change.isError && isAxiosError(change.error) && change.error.response?.status === 403;
  const menuDay = menu?.day ?? '';
  const menuWorks = menu ? projectWorks(menu.day) : true;
  const dayName = (day: string) => {
    const d = parseDay(day);
    return t('monthPicker.dayLabel', { month: d.getMonth() + 1, day: d.getDate(), weekday: weekdays[d.getDay()] });
  };
  const customParsed = custom ? parseNumber(custom.draft, { min: 0, max: 24 }) : null;
  const saveCustom = () => {
    if (!custom || !customParsed?.ok || customParsed.value === null) return;
    change.mutate({ day: custom.day, next: { kind: 'hours', hours: customParsed.value } });
    setCustom(null);
  };

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
            month={month} onMonthChange={setMonth} markOf={markOf}
            onPick={(day, anchor) => setMenu({ day, anchor })}
            disabled={!editable || change.isPending}
            ariaLabel={t('personCalendar.title', { name })}
          />
        )}
        <Box sx={{ fontSize: 12, color: ds.textSub }}>{t('personCalendar.legend')}</Box>
      </DialogContent>
      <DialogActions sx={{ px: '24px', pb: '18px' }}>
        <Button onClick={onClose} sx={{ color: ds.textSub }}>{t('member.close')}</Button>
      </DialogActions>

      <Menu
        open={menu !== null} anchorEl={menu?.anchor} onClose={() => setMenu(null)}
        slotProps={{ list: { 'aria-label': menu ? dayName(menuDay) : undefined } }}
      >
        {menuWorks && <MenuItem onClick={() => apply(menuDay, { kind: 'off', offPercent: FULL })}>{t('personCalendar.menuOff')}</MenuItem>}
        {menuWorks && <MenuItem onClick={() => apply(menuDay, { kind: 'off', offPercent: HALF })}>{t('personCalendar.menuHalf')}</MenuItem>}
        {!menuWorks && (
          <MenuItem onClick={() => apply(menuDay, { kind: 'hours', hours: usualHours })}>
            {t('personCalendar.menuHolidayWork', { hours: usualHours })}
          </MenuItem>
        )}
        <MenuItem onClick={() => {
          const own = mine.get(menuDay);
          setCustom({ day: menuDay, draft: String(own?.hours ?? usualHours) });
          setMenu(null);
        }}
        >
          {t('personCalendar.menuCustom')}
        </MenuItem>
        {mine.has(menuDay) && (
          <MenuItem onClick={() => apply(menuDay, { kind: 'clear' })}>{t('personCalendar.menuClear')}</MenuItem>
        )}
      </Menu>

      <Dialog open={custom !== null} onClose={() => setCustom(null)} maxWidth="xs">
        <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>
          {custom ? t('personCalendar.customTitle', { day: dayName(custom.day) }) : ''}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '8px', pt: '4px !important' }}>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); saveCustom(); }}>
            <TextField
              autoFocus fullWidth size="small" label={t('personCalendar.customLabel')}
              value={custom?.draft ?? ''} error={customParsed !== null && !customParsed.ok}
              slotProps={{ htmlInput: { inputMode: 'decimal' } }}
              helperText={t('personCalendar.customHint', { hours: usualHours })}
              onChange={(e) => setCustom((c) => (c ? { ...c, draft: e.target.value } : c))}
            />
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '16px' }}>
          <Button onClick={() => setCustom(null)} sx={{ color: ds.textSub }}>{t('gantt.cancel')}</Button>
          <Button variant="contained" disabled={!customParsed?.ok || customParsed.value === null} onClick={saveCustom}>
            {t('gantt.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Dialog>
  );
};

export default PersonCalendarDialog;
