import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Snackbar,
  Switch, TextField, ToggleButton, ToggleButtonGroup,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import AddIcon from '@mui/icons-material/Add';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { Link as RouterLink } from 'react-router-dom';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import type { Calendar, CalendarViewPreset, EventColorKey, WeekdayCode } from '../types';
import DayOffLayerDays from '../components/calendar/DayOffLayerDays';
import {
  createCalendar, createCalendarViewPreset, deleteCalendar, deleteCalendarViewPreset, getCalendars, getCalendarViewPresets,
  updateCalendar, updateCalendarViewPreset,
} from '../api/calendars';
import {
  CALENDARS_QUERY, CALENDAR_VIEW_PRESETS_QUERY, DAY_OFF_MARKS_QUERY, OCCURRENCES_QUERY,
} from '../calendar/calendarQueries';
import { isPrivateCalendar, visibleCalendarIds } from '../calendar/calendarSelection';
import { EVENT_COLOR_KEYS, WEEKDAY_CODES } from '../calendar/eventForm';
import { eventColor } from '../calendar/calendarColors';
import { errorDetailOf } from '../calendar/calendarRequests';
import { todayDate } from '../utils/format';

// カレンダーの設定（ADR-0034）。カレンダーの画面から分けた「管理」: 予定のカレンダーの追加・名前と色・
// 仕事/プライベート（ADR-0033）、休みの 4 層の色・稼働する曜日・休みとして数えるか・日付（ADR-0029・0032）、
// 表示の組み合わせの作成・編集・削除（ADR-0027）。表示の切り替え（チェック・組み合わせを当てる）はカレンダーの画面に残す。

type CalendarDraft = {
  id: number | null;
  name: string;
  colorKey: EventColorKey;
  /** 休みの日の一覧の層: 休みとして数える */
  countsAsDayOff?: boolean;
  /** 営業日の層: 稼働する曜日 */
  workdays?: WeekdayCode[];
  /** 予定のカレンダー: プライベート（ADR-0033） */
  isPrivate?: boolean;
};

type PresetDraft = { id: number | null; name: string; calendarIds: number[] };

const WEEKDAYS_IN_ORDER: readonly WeekdayCode[] = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'];

const draftOf = (cal: Calendar): CalendarDraft => ({
  id: cal.id, name: cal.name, colorKey: cal.color_key,
  countsAsDayOff: cal.kind === 'DAYS_OFF' ? cal.counts_as_day_off : undefined,
  workdays: cal.kind === 'WORKWEEK' ? cal.workdays ?? [] : undefined,
  isPrivate: cal.kind === 'EVENTS' ? isPrivateCalendar(cal) : undefined,
});

const CalendarSettingsPage: React.FC = () => {
  const { t, weekdays } = useI18n();
  const c = useTheme().palette.calendar;
  const qc = useQueryClient();
  const [draft, setDraft] = useState<CalendarDraft | null>(null);
  const [deleting, setDeleting] = useState<Calendar | null>(null);
  const [presetDraft, setPresetDraft] = useState<PresetDraft | null>(null);
  const [presetDeleting, setPresetDeleting] = useState<CalendarViewPreset | null>(null);
  const [error, setError] = useState<string | null>(null);

  const calendarsQuery = useQuery({ queryKey: [CALENDARS_QUERY], queryFn: getCalendars });
  const calendars = calendarsQuery.data ?? [];
  const { data: presets } = useQuery({ queryKey: [CALENDAR_VIEW_PRESETS_QUERY], queryFn: getCalendarViewPresets });

  const failed = (e: unknown) => {
    void qc.invalidateQueries({ queryKey: [CALENDARS_QUERY] });
    setError(t('calendar.saveFailed', { detail: errorDetailOf(e) ?? '' }));
  };
  const refreshPresets = () => void qc.invalidateQueries({ queryKey: [CALENDAR_VIEW_PRESETS_QUERY] });

  const saveCalendar = useMutation({
    mutationFn: (d: CalendarDraft) => (d.id == null
      ? createCalendar({ name: d.name.trim(), color_key: d.colorKey, scope: d.isPrivate ? 'PRIVATE' : 'WORK' })
      : updateCalendar(d.id, {
        name: d.name.trim(), color_key: d.colorKey,
        ...(d.countsAsDayOff != null ? { counts_as_day_off: d.countsAsDayOff } : {}),
        ...(d.workdays != null ? { workdays: d.workdays } : {}),
        ...(d.isPrivate != null ? { scope: d.isPrivate ? 'PRIVATE' as const : 'WORK' as const } : {}),
      })),
    onSuccess: () => {
      setDraft(null);
      // 回の一覧はカレンダーの色を載せている。休みの層を変えたら塗りと営業日シフトの回も変わる
      for (const queryKey of [[CALENDARS_QUERY], [OCCURRENCES_QUERY], [DAY_OFF_MARKS_QUERY]]) {
        void qc.invalidateQueries({ queryKey });
      }
    },
    onError: failed,
  });

  const removeCalendar = useMutation({
    mutationFn: (calendar: Calendar) => deleteCalendar(calendar.id),
    onSuccess: () => {
      setDeleting(null);
      setDraft(null);
      for (const queryKey of [[CALENDARS_QUERY], [CALENDAR_VIEW_PRESETS_QUERY], [OCCURRENCES_QUERY]]) {
        void qc.invalidateQueries({ queryKey });
      }
    },
    onError: failed,
  });

  const savePreset = useMutation({
    mutationFn: (d: PresetDraft) => (d.id == null
      ? createCalendarViewPreset(d.name.trim(), d.calendarIds)
      : updateCalendarViewPreset(d.id, d.name.trim(), d.calendarIds)),
    onSuccess: () => {
      setPresetDraft(null);
      refreshPresets();
    },
    onError: failed,
  });

  const removePreset = useMutation({
    mutationFn: (preset: CalendarViewPreset) => deleteCalendarViewPreset(preset.id),
    onSuccess: () => {
      setPresetDeleting(null);
      refreshPresets();
    },
    onError: failed,
  });

  const defaultCalendar = calendars.find((cal) => cal.is_default);
  const eventCalendars = calendars.filter((cal) => cal.kind === 'EVENTS');
  const layers = calendars.filter((cal) => cal.kind !== 'EVENTS');
  const nameOf = (id: number) => calendars.find((cal) => cal.id === id)?.name;
  const editing = draft?.id != null ? calendars.find((cal) => cal.id === draft.id) ?? null : null;
  const thisYear = todayDate().getFullYear();

  const card = {
    bgcolor: c.surface, border: `1px solid ${c.border}`, borderRadius: '10px', overflow: 'hidden',
  } as const;
  const sectionHead = (titleKey: TranslationKey, hintKey: TranslationKey | null, action?: React.ReactNode) => (
    <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: '8px', px: '16px', pt: '12px', pb: '8px' }}>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box component="h2" sx={{ m: 0, fontSize: 15, fontWeight: 700, color: c.textPrimary }}>{t(titleKey)}</Box>
        {hintKey && <Box sx={{ fontSize: 12, color: c.textSecondary, mt: '2px' }}>{t(hintKey)}</Box>}
      </Box>
      {action}
    </Box>
  );
  const row = (key: React.Key, color: string | null, name: React.ReactNode, marks: React.ReactNode, actions: React.ReactNode) => (
    <Box
      component="li"
      key={key}
      sx={{
        display: 'flex', alignItems: 'center', gap: '10px', minHeight: 48, px: '16px',
        borderTop: `1px solid ${c.border}`,
      }}
    >
      {color && <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: color, flexShrink: 0 }} />}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ fontSize: 14, color: c.textPrimary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</Box>
        {marks && <Box sx={{ fontSize: 12, color: c.textSecondary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{marks}</Box>}
      </Box>
      {actions}
    </Box>
  );
  const listSx = { listStyle: 'none', m: 0, p: 0 } as const;

  const calendarMarks = (cal: Calendar): string => [
    cal.is_default ? t('calendar.calendarDefaultMark') : null,
    cal.kind === 'EVENTS' ? t(isPrivateCalendar(cal) ? 'calendar.privateMark' : 'calendar.workMark') : null,
    cal.kind === 'WORKWEEK' && cal.workdays
      ? WEEKDAYS_IN_ORDER.filter((d) => cal.workdays?.includes(d)).map((d) => weekdays[WEEKDAY_CODES.indexOf(d)]).join('・')
      : null,
    cal.kind === 'DAYS_OFF' ? t(cal.counts_as_day_off ? 'calendar.layerCounted' : 'calendar.layerNotCounted') : null,
  ].filter(Boolean).join('・');

  const editButton = (cal: Calendar) => (
    <Button size="small" onClick={() => setDraft(draftOf(cal))} aria-label={t('calendar.calendarEditOf', { name: cal.name })}>
      {t('calendar.edit')}
    </Button>
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: 720, mx: 'auto', width: '100%' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <Button component={RouterLink} to="/calendar" startIcon={<ArrowBackIcon />} data-testid="calendar-settings-back">
          {t('calendar.settingsBack')}
        </Button>
        {/* 広い画面は上の帯（Layout）が題を出す。狭い画面の帯には題が無いのでここに出す */}
        <Box component="h1" sx={{ display: { xs: 'block', md: 'none' }, m: 0, fontSize: 18, fontWeight: 700, color: c.textPrimary }}>
          {t('calendar.settingsTitle')}
        </Box>
      </Box>
      {calendarsQuery.isError && <Alert severity="error">{t('common.loadError')}</Alert>}

      {/* 予定のカレンダー */}
      <Box sx={card} data-testid="calendar-settings-events">
        {sectionHead('calendar.settingsEvents', 'calendar.settingsEventsHint', (
          <Button
            size="small"
            startIcon={<AddIcon />}
            onClick={() => setDraft({ id: null, name: '', colorKey: 'PEACOCK', isPrivate: false })}
            data-testid="calendar-add"
          >
            {t('calendar.calendarAdd')}
          </Button>
        ))}
        <Box component="ul" sx={listSx}>
          {eventCalendars.map((cal) => row(cal.id, eventColor(cal.color_key), cal.name, calendarMarks(cal), editButton(cal)))}
        </Box>
      </Box>

      {/* 休みの層 */}
      {layers.length > 0 && (
        <Box sx={card} data-testid="calendar-settings-layers">
          {sectionHead('calendar.settingsLayers', 'calendar.settingsLayersHint')}
          <Box component="ul" sx={listSx}>
            {layers.map((cal) => row(cal.id, eventColor(cal.color_key), cal.name, calendarMarks(cal), editButton(cal)))}
          </Box>
        </Box>
      )}

      {/* 表示の組み合わせ */}
      <Box sx={card} data-testid="calendar-settings-presets">
        {sectionHead('calendar.settingsPresets', 'calendar.settingsPresetsHint', (
          <Button
            size="small"
            startIcon={<AddIcon />}
            onClick={() => setPresetDraft({ id: null, name: '', calendarIds: visibleCalendarIds(calendars) })}
            data-testid="preset-add"
          >
            {t('calendar.presetAdd')}
          </Button>
        ))}
        <Box component="ul" sx={listSx}>
          {(presets ?? []).length === 0 && (
            <Box component="li" sx={{ px: '16px', py: '12px', fontSize: 13, color: c.textSecondary, borderTop: `1px solid ${c.border}` }}>
              {t('calendar.presetEmpty')}
            </Box>
          )}
          {(presets ?? []).map((preset) => row(
            preset.id,
            null,
            preset.name,
            preset.calendar_ids.map(nameOf).filter(Boolean).join('・') || t('calendar.presetNone'),
            <Box sx={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
              <Button
                size="small"
                onClick={() => setPresetDraft({ id: preset.id, name: preset.name, calendarIds: [...preset.calendar_ids] })}
                aria-label={t('calendar.presetEditOf', { name: preset.name })}
              >
                {t('calendar.edit')}
              </Button>
              <Button size="small" color="error" onClick={() => setPresetDeleting(preset)}>
                {t('calendar.delete')}
              </Button>
            </Box>,
          ))}
        </Box>
      </Box>

      {/* カレンダーを作る・直す */}
      <Dialog open={draft != null} onClose={() => setDraft(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t(draft?.id == null ? 'calendar.calendarAdd' : 'calendar.calendarEdit')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '16px', pt: '8px !important' }}>
          <TextField
            autoFocus
            label={t('calendar.calendarName')}
            value={draft?.name ?? ''}
            onChange={(e) => setDraft((d) => (d ? { ...d, name: e.target.value } : d))}
            slotProps={{ htmlInput: { maxLength: 200 } }}
          />
          <Box>
            <Box sx={{ fontSize: 12, color: 'text.secondary', mb: '6px' }}>{t('calendar.color')}</Box>
            <Box role="radiogroup" aria-label={t('calendar.color')} sx={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {EVENT_COLOR_KEYS.map((key) => {
                const selected = key === draft?.colorKey;
                const label = t(`calendar.color${key}` as TranslationKey);
                return (
                  <Box
                    key={key}
                    component="button"
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    aria-label={label}
                    title={label}
                    onClick={() => setDraft((d) => (d ? { ...d, colorKey: key } : d))}
                    sx={{
                      width: 32, height: 32, borderRadius: '50%', cursor: 'pointer', bgcolor: eventColor(key),
                      border: selected ? '3px solid' : '1px solid', borderColor: selected ? 'text.primary' : 'divider',
                    }}
                  />
                );
              })}
            </Box>
            <Box sx={{ fontSize: 12, color: 'text.secondary', mt: '6px' }}>
              {t(editing && editing.kind !== 'EVENTS' ? 'calendar.layerColorHint' : 'calendar.calendarColorHint')}
            </Box>
          </Box>
          {draft?.isPrivate != null && (
            <Box>
              <FormControlLabel
                control={(
                  <Switch
                    checked={draft.isPrivate}
                    disabled={editing?.is_default ?? false}
                    onChange={(e) => setDraft((d) => (d ? { ...d, isPrivate: e.target.checked } : d))}
                    data-testid="calendar-private"
                  />
                )}
                label={t('calendar.privateCalendar')}
              />
              <Box sx={{ fontSize: 12, color: 'text.secondary' }}>
                {t(editing?.is_default ? 'calendar.privateDefaultHint' : 'calendar.privateCalendarHint')}
              </Box>
            </Box>
          )}
          {editing?.kind === 'WORKWEEK' && draft?.workdays && (
            <Box>
              <Box sx={{ fontSize: 12, color: 'text.secondary', mb: '6px' }}>{t('calendar.layerWorkdays')}</Box>
              <ToggleButtonGroup
                size="small"
                value={draft.workdays}
                onChange={(_, value: WeekdayCode[]) => setDraft((d) => (d ? { ...d, workdays: value } : d))}
                aria-label={t('calendar.layerWorkdays')}
                sx={{ flexWrap: 'wrap' }}
              >
                {WEEKDAYS_IN_ORDER.map((code) => (
                  <ToggleButton key={code} value={code} sx={{ minWidth: 40 }}>
                    {weekdays[WEEKDAY_CODES.indexOf(code)]}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
              <Box sx={{ fontSize: 12, color: 'text.secondary', mt: '6px' }}>{t('calendar.layerWorkdaysHint')}</Box>
            </Box>
          )}
          {editing?.kind === 'DAYS_OFF' && draft?.countsAsDayOff != null && (
            <>
              <FormControlLabel
                control={(
                  <Switch
                    checked={draft.countsAsDayOff}
                    onChange={(e) => setDraft((d) => (d ? { ...d, countsAsDayOff: e.target.checked } : d))}
                  />
                )}
                label={t('calendar.layerCounts')}
              />
              <Box sx={{ fontSize: 12, color: 'text.secondary', mt: '-8px' }}>{t('calendar.layerCountsHint')}</Box>
              <DayOffLayerDays layer={editing} initialYear={thisYear} onError={(detail) => setError(t('calendar.saveFailed', { detail }))} />
            </>
          )}
        </DialogContent>
        <DialogActions>
          {editing && !editing.is_default && editing.kind === 'EVENTS' && (
            <Button color="error" onClick={() => setDeleting(editing)} sx={{ mr: 'auto' }}>
              {t('calendar.delete')}
            </Button>
          )}
          <Button onClick={() => setDraft(null)}>{t('calendar.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!draft || draft.name.trim() === '' || saveCalendar.isPending}
            onClick={() => draft && saveCalendar.mutate(draft)}
          >
            {t('calendar.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={deleting != null} onClose={() => setDeleting(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('calendar.calendarDelete')}</DialogTitle>
        <DialogContent>
          {t('calendar.calendarDeleteConfirm', { name: deleting?.name ?? '', target: defaultCalendar?.name ?? '' })}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleting(null)}>{t('calendar.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={removeCalendar.isPending}
            onClick={() => deleting && removeCalendar.mutate(deleting)}
          >
            {t('calendar.delete')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 表示の組み合わせを作る・直す（名前と、入れるカレンダー） */}
      <Dialog open={presetDraft != null} onClose={() => setPresetDraft(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t(presetDraft?.id == null ? 'calendar.presetAdd' : 'calendar.presetEdit')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '12px', pt: '8px !important' }}>
          <TextField
            autoFocus
            label={t('calendar.presetName')}
            value={presetDraft?.name ?? ''}
            onChange={(e) => setPresetDraft((d) => (d ? { ...d, name: e.target.value } : d))}
            slotProps={{ htmlInput: { maxLength: 200 } }}
          />
          <Box>
            <Box sx={{ fontSize: 12, color: 'text.secondary', mb: '2px' }}>{t('calendar.presetCalendars')}</Box>
            <Box sx={{ display: 'flex', flexDirection: 'column' }} data-testid="preset-calendars">
              {calendars.map((cal) => {
                const color = eventColor(cal.color_key);
                const checked = presetDraft?.calendarIds.includes(cal.id) ?? false;
                return (
                  <FormControlLabel
                    key={cal.id}
                    label={cal.name}
                    control={(
                      <Checkbox
                        checked={checked}
                        onChange={() => setPresetDraft((d) => (d
                          ? { ...d, calendarIds: checked ? d.calendarIds.filter((id) => id !== cal.id) : [...d.calendarIds, cal.id] }
                          : d))}
                        sx={{ color, '&.Mui-checked': { color } }}
                      />
                    )}
                  />
                );
              })}
            </Box>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPresetDraft(null)}>{t('calendar.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!presetDraft || presetDraft.name.trim() === '' || savePreset.isPending}
            onClick={() => presetDraft && savePreset.mutate(presetDraft)}
          >
            {t('calendar.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={presetDeleting != null} onClose={() => setPresetDeleting(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('calendar.presetDelete')}</DialogTitle>
        <DialogContent>{t('calendar.presetDeleteConfirm', { name: presetDeleting?.name ?? '' })}</DialogContent>
        <DialogActions>
          <Button onClick={() => setPresetDeleting(null)}>{t('calendar.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={removePreset.isPending}
            onClick={() => presetDeleting && removePreset.mutate(presetDeleting)}
          >
            {t('calendar.delete')}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={error != null} autoHideDuration={6000} onClose={() => setError(null)}>
        <Alert severity="error" onClose={() => setError(null)} sx={{ width: '100%' }}>{error}</Alert>
      </Snackbar>
    </Box>
  );
};

export default CalendarSettingsPage;
