import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Checkbox, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel,
  IconButton, MenuItem, Switch, TextField,
} from '@mui/material';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';
import { TrashIcon } from '../icons';
import type { BusinessCalendar, WeekdayCode } from '../../types';
import {
  addHoliday, createBusinessCalendar, deleteBusinessCalendar, getBusinessCalendars, importJapaneseHolidays,
  removeHoliday, updateBusinessCalendar,
} from '../../api/calendar';
import type { BusinessCalendarInput } from '../../api/calendar';
import { WEEKDAY_CODES } from '../../calendar/eventForm';
import { errorDetailOf } from '../../calendar/calendarRequests';
import { toZonedPoint, resolveTimeZone, yearMonthOf } from '../../calendar/zonedTime';

// 日本の祝日を暦から出せる年（ADR-0009）。
const FIRST_JAPAN_YEAR = 2007;
const LAST_JAPAN_YEAR = 2099;
const WEEKDAYS_MON_FRI: WeekdayCode[] = ['MO', 'TU', 'WE', 'TH', 'FR'];

const card = { bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px' } as const;
const sectionHeader = {
  px: '18px', py: '14px', borderBottom: `1px solid ${ds.borderPale}`, fontSize: 15, fontWeight: 700, color: ds.text,
} as const;

const useInvalidate = () => {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ['business-calendars'] });
    void qc.invalidateQueries({ queryKey: ['calendar-holidays'] });
    void qc.invalidateQueries({ queryKey: ['calendar-occurrences'] });
  };
};

interface EditorProps {
  calendar: BusinessCalendar;
  thisYear: number;
}

/** 営業日カレンダー 1 つ（移植元 BusinessCalendarsTab の編集画面）: 名前・営業日・シフトの仕方・有効と祝日。 */
const BusinessCalendarEditor: React.FC<EditorProps> = ({ calendar, thisYear }) => {
  const { t, weekdays } = useI18n();
  const invalidate = useInvalidate();
  const [input, setInput] = useState<BusinessCalendarInput>({
    name: calendar.name,
    workdays: calendar.workdays,
    shift_on_holidays_only: calendar.shift_on_holidays_only,
    is_enabled: calendar.is_enabled,
  });
  const [year, setYear] = useState(thisYear);
  const [holidayDate, setHolidayDate] = useState('');
  const [holidayName, setHolidayName] = useState('');
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const onError = (e: unknown) => setMessage({ text: t('bizcal.error', { detail: errorDetailOf(e) ?? '' }), ok: false });
  const onDone = (text: string) => () => { setMessage({ text, ok: true }); invalidate(); };

  const save = useMutation({ mutationFn: () => updateBusinessCalendar(calendar.id, input), onSuccess: onDone(t('bizcal.saved')), onError });
  const remove = useMutation({ mutationFn: () => deleteBusinessCalendar(calendar.id), onSuccess: invalidate, onError });
  const importJapan = useMutation({
    mutationFn: () => importJapaneseHolidays(calendar.id, year),
    onSuccess: onDone(t('bizcal.imported', { year })),
    onError,
  });
  const add = useMutation({
    mutationFn: () => addHoliday(calendar.id, { date: holidayDate, name: holidayName.trim() || null }),
    onSuccess: () => { setHolidayDate(''); setHolidayName(''); onDone(t('bizcal.saved'))(); },
    onError,
  });
  const removeOne = useMutation({ mutationFn: (date: string) => removeHoliday(calendar.id, date), onSuccess: invalidate, onError });

  const holidaysOfYear = useMemo(
    () => calendar.holidays.filter((h) => yearMonthOf(h.date).year === year),
    [calendar.holidays, year],
  );
  // 選べる年: 日本の祝日を出せる年と、すでに祝日がある年。
  const years = useMemo(() => {
    const set = new Set<number>(Array.from({ length: LAST_JAPAN_YEAR - FIRST_JAPAN_YEAR + 1 }, (_, i) => FIRST_JAPAN_YEAR + i));
    for (const h of calendar.holidays) set.add(yearMonthOf(h.date).year);
    set.add(thisYear);
    return [...set].sort((a, b) => a - b);
  }, [calendar.holidays, thisYear]);
  const dirty = input.name !== calendar.name
    || input.workdays.length !== calendar.workdays.length || input.workdays.some((w) => !calendar.workdays.includes(w))
    || input.shift_on_holidays_only !== calendar.shift_on_holidays_only || input.is_enabled !== calendar.is_enabled;
  const busy = save.isPending || remove.isPending || importJapan.isPending || add.isPending || removeOne.isPending;

  const toggleWorkday = (code: WeekdayCode, checked: boolean) => setInput((i) => ({
    ...i, workdays: checked ? [...i.workdays.filter((w) => w !== code), code] : i.workdays.filter((w) => w !== code),
  }));

  return (
    <Box data-testid={`business-calendar-${calendar.id}`} sx={{ border: `1px solid ${ds.borderPale}`, borderRadius: '8px', p: '14px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <Box sx={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <TextField
          size="small"
          label={t('bizcal.name')}
          value={input.name}
          onChange={(e) => setInput((i) => ({ ...i, name: e.target.value }))}
          sx={{ flex: 1, minWidth: 200 }}
        />
        <FormControlLabel
          control={<Switch checked={input.is_enabled} onChange={(e) => setInput((i) => ({ ...i, is_enabled: e.target.checked }))} />}
          label={t('bizcal.enabled')}
        />
      </Box>
      <Box>
        <Box sx={{ fontSize: 12, color: ds.textSub, mb: '2px' }}>{t('bizcal.workdays')}</Box>
        <Box sx={{ display: 'flex', flexWrap: 'wrap' }}>
          {WEEKDAY_CODES.map((code, i) => (
            <FormControlLabel
              key={code}
              control={<Checkbox size="small" checked={input.workdays.includes(code)} onChange={(e) => toggleWorkday(code, e.target.checked)} />}
              label={weekdays[i]}
            />
          ))}
        </Box>
      </Box>
      <FormControlLabel
        control={(
          <Switch
            checked={input.shift_on_holidays_only}
            onChange={(e) => setInput((i) => ({ ...i, shift_on_holidays_only: e.target.checked }))}
          />
        )}
        label={t('bizcal.shiftOnHolidaysOnly')}
      />
      <Box sx={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <Button variant="contained" disabled={!dirty || busy || input.name.trim() === ''} onClick={() => save.mutate()}>
          {t('bizcal.save')}
        </Button>
        <Button color="error" disabled={busy} onClick={() => setConfirmDelete(true)}>{t('bizcal.delete')}</Button>
      </Box>

      {/* 祝日 */}
      <Box sx={{ borderTop: `1px solid ${ds.borderPale}`, pt: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <Box sx={{ fontSize: 14, fontWeight: 700, color: ds.text }}>{t('bizcal.holidays')}</Box>
          <TextField select size="small" label={t('bizcal.year')} value={year} onChange={(e) => setYear(Number(e.target.value))} sx={{ width: 110 }}>
            {years.map((y) => <MenuItem key={y} value={y}>{y}</MenuItem>)}
          </TextField>
          <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('bizcal.holidayCount', { count: holidaysOfYear.length })}</Box>
          <Button
            variant="outlined"
            size="small"
            disabled={busy || year < FIRST_JAPAN_YEAR || year > LAST_JAPAN_YEAR}
            onClick={() => importJapan.mutate()}
            data-testid="import-japanese-holidays"
          >
            {t('bizcal.importJapan')}
          </Button>
        </Box>
        {holidaysOfYear.length === 0 ? (
          <Box sx={{ fontSize: 13, color: ds.textMuted }}>{t('bizcal.noHolidays')}</Box>
        ) : (
          <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, maxHeight: 240, overflowY: 'auto' }}>
            {holidaysOfYear.map((h) => (
              <Box component="li" key={h.date} sx={{ display: 'flex', alignItems: 'center', gap: '12px', py: '2px' }}>
                <Box sx={{ fontSize: 13, fontFamily: 'ui-monospace, monospace', color: ds.text, width: 96 }}>{h.date}</Box>
                <Box sx={{ flex: 1, fontSize: 13, color: ds.text }}>{h.name ?? ''}</Box>
                <IconButton
                  size="small"
                  aria-label={t('bizcal.removeHoliday')}
                  disabled={busy}
                  onClick={() => removeOne.mutate(h.date)}
                >
                  <TrashIcon size={16} />
                </IconButton>
              </Box>
            ))}
          </Box>
        )}
        <Box sx={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            size="small"
            type="date"
            label={t('bizcal.holidayDate')}
            value={holidayDate}
            onChange={(e) => setHolidayDate(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField size="small" label={t('bizcal.holidayName')} value={holidayName} onChange={(e) => setHolidayName(e.target.value)} />
          <Button variant="outlined" disabled={busy || holidayDate === ''} onClick={() => add.mutate()}>{t('bizcal.addHoliday')}</Button>
        </Box>
      </Box>
      {message && <Alert severity={message.ok ? 'success' : 'error'} onClose={() => setMessage(null)}>{message.text}</Alert>}

      <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('bizcal.delete')}</DialogTitle>
        <DialogContent>{t('bizcal.deleteConfirm', { name: calendar.name })}</DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(false)}>{t('calendar.cancel')}</Button>
          <Button color="error" variant="contained" onClick={() => { setConfirmDelete(false); remove.mutate(); }}>
            {t('calendar.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

/**
 * 設定画面の「営業日カレンダーと祝日」（task #157）。移植元 NolumiaScheduler の
 * 「営業日カレンダー」タブの役目（カレンダーの作成・営業日・祝日の追加と、日本の祝日を年で入れる）。
 */
const BusinessCalendarSettings: React.FC = () => {
  const { t, timezone } = useI18n();
  const invalidate = useInvalidate();
  const { data: calendars, isLoading, error } = useQuery({ queryKey: ['business-calendars'], queryFn: getBusinessCalendars });
  const [openedAt] = useState(() => Date.now());
  const thisYear = yearMonthOf(toZonedPoint(openedAt, resolveTimeZone(timezone)).date).year;
  const create = useMutation({
    mutationFn: () => createBusinessCalendar({
      name: t('bizcal.defaultName'), workdays: WEEKDAYS_MON_FRI, shift_on_holidays_only: false, is_enabled: true,
    }),
    onSuccess: invalidate,
  });

  return (
    <Box sx={card} data-testid="business-calendar-settings">
      <Box sx={sectionHeader}>{t('bizcal.title')}</Box>
      <Box sx={{ p: '18px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('bizcal.help')}</Box>
        {isLoading && <CircularProgress size={24} />}
        {error && <Alert severity="error">{t('common.loadError')}</Alert>}
        {calendars?.length === 0 && <Box sx={{ fontSize: 13, color: ds.textMuted }}>{t('bizcal.none')}</Box>}
        {calendars?.map((c) => (
          <BusinessCalendarEditor key={c.id} calendar={c} thisYear={thisYear} />
        ))}
        {create.isError && <Alert severity="error">{t('bizcal.error', { detail: errorDetailOf(create.error) ?? '' })}</Alert>}
        <Box>
          <Button variant="outlined" disabled={create.isPending} onClick={() => create.mutate()}>{t('bizcal.add')}</Button>
        </Box>
      </Box>
    </Box>
  );
};

export default BusinessCalendarSettings;
