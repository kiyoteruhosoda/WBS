import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Button, Checkbox, Chip, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, TextField,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import AddIcon from '@mui/icons-material/Add';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useI18n } from '../../i18n';
import type { TranslationKey } from '../../i18n/translations';
import type { Calendar, CalendarViewPreset, EventColorKey } from '../../types';
import {
  applyCalendarViewPreset, createCalendar, createCalendarViewPreset, deleteCalendar, deleteCalendarViewPreset,
  getCalendarViewPresets, setVisibleCalendars, updateCalendar, updateCalendarViewPreset,
} from '../../api/calendars';
import { CALENDARS_QUERY, CALENDAR_VIEW_PRESETS_QUERY, OCCURRENCES_QUERY } from '../../calendar/calendarQueries';
import {
  allVisible, presetIsActive, toggledVisibleIds, visibleCalendarIds, withVisibleIds,
} from '../../calendar/calendarSelection';
import { EVENT_COLOR_KEYS } from '../../calendar/eventForm';
import { eventColor } from '../../calendar/calendarColors';
import { errorDetailOf } from '../../calendar/calendarRequests';

// カレンダーの一覧と表示の選択（task #191、ADR-0027）。Google カレンダーと同じく、チェックしたカレンダーの
// 予定だけを出す。選んだ状態はサーバーに覚える（端末をまたいで同じ）。上に「表示の組み合わせ」を並べ、
// 押せば 1 回で切り替わる。広い画面は横の列、狭い画面はカレンダーの上で折りたたむ。

interface Props {
  calendars: readonly Calendar[];
  /** 失敗を知らせる（画面の下の知らせ） */
  onError: (detail: string) => void;
}

type CalendarDraft = { id: number | null; name: string; colorKey: EventColorKey };

const CalendarListPanel: React.FC<Props> = ({ calendars, onError }) => {
  const { t } = useI18n();
  const theme = useTheme();
  const c = theme.palette.calendar;
  const narrow = useMediaQuery(theme.breakpoints.down('md'));
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<CalendarDraft | null>(null);
  const [deleting, setDeleting] = useState<Calendar | null>(null);
  const [presetName, setPresetName] = useState<string | null>(null);
  const [presetDeleting, setPresetDeleting] = useState<CalendarViewPreset | null>(null);

  const { data: presets } = useQuery({ queryKey: [CALENDAR_VIEW_PRESETS_QUERY], queryFn: getCalendarViewPresets });

  const failed = (error: unknown) => {
    void qc.invalidateQueries({ queryKey: [CALENDARS_QUERY] });
    onError(errorDetailOf(error) ?? '');
  };
  const putCalendars = (list: Calendar[]) => qc.setQueryData<Calendar[]>([CALENDARS_QUERY], list);

  // 表示の選択: 応答を待たずに見せ、サーバーに覚えさせる（失敗したら取り直して戻る）
  const visibility = useMutation({
    mutationFn: (ids: number[]) => setVisibleCalendars(ids),
    onMutate: (ids) => putCalendars(withVisibleIds(calendars, ids)),
    onSuccess: putCalendars,
    onError: failed,
  });
  const show = (ids: number[]) => visibility.mutate(ids);

  const applyPreset = useMutation({
    mutationFn: (preset: CalendarViewPreset) => applyCalendarViewPreset(preset.id),
    onMutate: (preset) => putCalendars(withVisibleIds(calendars, preset.calendar_ids)),
    onSuccess: putCalendars,
    onError: failed,
  });

  const savePreset = useMutation({
    mutationFn: (name: string) => createCalendarViewPreset(name, visibleCalendarIds(calendars)),
    onSuccess: () => {
      setPresetName(null);
      void qc.invalidateQueries({ queryKey: [CALENDAR_VIEW_PRESETS_QUERY] });
    },
    onError: failed,
  });

  const overwritePreset = useMutation({
    mutationFn: (preset: CalendarViewPreset) =>
      updateCalendarViewPreset(preset.id, preset.name, visibleCalendarIds(calendars)),
    onSuccess: () => {
      setPresetName(null);
      void qc.invalidateQueries({ queryKey: [CALENDAR_VIEW_PRESETS_QUERY] });
    },
    onError: failed,
  });

  const removePreset = useMutation({
    mutationFn: (preset: CalendarViewPreset) => deleteCalendarViewPreset(preset.id),
    onSuccess: () => {
      setPresetDeleting(null);
      void qc.invalidateQueries({ queryKey: [CALENDAR_VIEW_PRESETS_QUERY] });
    },
    onError: failed,
  });

  const saveCalendar = useMutation({
    mutationFn: (d: CalendarDraft) => (d.id == null
      ? createCalendar({ name: d.name.trim(), color_key: d.colorKey })
      : updateCalendar(d.id, { name: d.name.trim(), color_key: d.colorKey })),
    onSuccess: () => {
      setDraft(null);
      void qc.invalidateQueries({ queryKey: [CALENDARS_QUERY] });
      // 回の一覧はカレンダーの色を載せている
      void qc.invalidateQueries({ queryKey: [OCCURRENCES_QUERY] });
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

  const defaultCalendar = calendars.find((cal) => cal.is_default);
  const visibleCount = calendars.filter((cal) => cal.is_visible).length;
  const activePreset = (presets ?? []).find((preset) => presetIsActive(preset, calendars));
  const title = activePreset
    ? t('calendar.calendarsTitlePreset', { name: activePreset.name, visible: visibleCount, total: calendars.length })
    : t('calendar.calendarsTitle', { visible: visibleCount, total: calendars.length });

  const presetRow = (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }} data-testid="calendar-presets">
      {(presets ?? []).map((preset) => {
        const active = presetIsActive(preset, calendars);
        return (
          <Chip
            key={preset.id}
            size="small"
            label={preset.name}
            color={active ? 'primary' : 'default'}
            variant={active ? 'filled' : 'outlined'}
            aria-pressed={active}
            onClick={() => applyPreset.mutate(preset)}
          />
        );
      })}
      <Button size="small" startIcon={<AddIcon />} onClick={() => setPresetName('')} sx={{ minWidth: 0 }}>
        {t('calendar.presetSave')}
      </Button>
    </Box>
  );

  const list = (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px', p: '8px 12px' }}>
      <Box sx={{ fontSize: 11, color: c.textSecondary }}>{t('calendar.presets')}</Box>
      {presetRow}
      <Box sx={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
        <Button
          size="small"
          variant="outlined"
          disabled={allVisible(calendars)}
          onClick={() => show(calendars.map((cal) => cal.id))}
          data-testid="calendar-show-all"
        >
          {t('calendar.calendarShowAll')}
        </Button>
      </Box>
      <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, display: 'flex', flexDirection: 'column' }}>
        {calendars.map((cal) => {
          const color = eventColor(cal.color_key);
          return (
            <Box
              component="li"
              key={cal.id}
              data-calendar-id={cal.id}
              sx={{ display: 'flex', alignItems: 'center', minHeight: 40, gap: '2px' }}
            >
              <Checkbox
                checked={cal.is_visible}
                onChange={() => show(toggledVisibleIds(calendars, cal.id))}
                slotProps={{ input: { 'aria-label': cal.name } }}
                sx={{ p: '8px', color, '&.Mui-checked': { color } }}
              />
              <Box
                component="label"
                onClick={() => show(toggledVisibleIds(calendars, cal.id))}
                sx={{
                  flex: 1, minWidth: 0, fontSize: 13, color: c.textPrimary, cursor: 'pointer',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
              >
                {cal.name}
                {cal.is_default && (
                  <Box component="span" sx={{ ml: '6px', fontSize: 11, color: c.textSecondary }}>
                    {t('calendar.calendarDefaultMark')}
                  </Box>
                )}
              </Box>
              <IconButton
                size="small"
                aria-label={t('calendar.calendarEditOf', { name: cal.name })}
                onClick={() => setDraft({ id: cal.id, name: cal.name, colorKey: cal.color_key })}
              >
                <EditOutlinedIcon sx={{ fontSize: 18 }} />
              </IconButton>
            </Box>
          );
        })}
      </Box>
      <Button
        size="small"
        startIcon={<AddIcon />}
        onClick={() => setDraft({ id: null, name: '', colorKey: 'PEACOCK' })}
        sx={{ alignSelf: 'flex-start' }}
        data-testid="calendar-add"
      >
        {t('calendar.calendarAdd')}
      </Button>
    </Box>
  );

  const editing = draft?.id != null ? calendars.find((cal) => cal.id === draft.id) ?? null : null;

  return (
    <Box
      data-testid="calendar-list-panel"
      sx={{
        display: 'flex', flexDirection: 'column', minHeight: 0, height: narrow ? 'auto' : '100%',
        bgcolor: c.surface, border: `1px solid ${c.border}`, borderRadius: '10px', overflow: 'hidden',
      }}
    >
      {narrow ? (
        <>
          <Button
            onClick={() => setOpen((v) => !v)}
            endIcon={open ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            aria-expanded={open}
            sx={{ justifyContent: 'space-between', px: '12px', color: c.textPrimary }}
          >
            {title}
          </Button>
          <Collapse in={open}>
            <Box sx={{ maxHeight: 320, overflowY: 'auto' }}>{list}</Box>
          </Collapse>
        </>
      ) : (
        <>
          <Box sx={{ px: '12px', py: '8px', fontSize: 13, fontWeight: 600, color: c.textPrimary, borderBottom: `1px solid ${c.border}` }}>
            {title}
          </Box>
          <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>{list}</Box>
        </>
      )}

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
            <Box sx={{ fontSize: 12, color: 'text.secondary', mt: '6px' }}>{t('calendar.calendarColorHint')}</Box>
          </Box>
        </DialogContent>
        <DialogActions>
          {editing && !editing.is_default && (
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

      {/* 表示の組み合わせを保存する・消す */}
      <Dialog open={presetName != null} onClose={() => setPresetName(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('calendar.presetDialogTitle')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '12px', pt: '8px !important' }}>
          <Box sx={{ fontSize: 13, color: 'text.secondary' }}>
            {t('calendar.presetSaveHint', {
              names: calendars.filter((cal) => cal.is_visible).map((cal) => cal.name).join('・') || t('calendar.presetNone'),
            })}
          </Box>
          <TextField
            autoFocus
            label={t('calendar.presetName')}
            value={presetName ?? ''}
            onChange={(e) => setPresetName(e.target.value)}
            slotProps={{ htmlInput: { maxLength: 200 } }}
          />
          {(presets ?? []).length > 0 && (
            <Box>
              <Box sx={{ fontSize: 12, color: 'text.secondary', mb: '4px' }}>{t('calendar.presetExisting')}</Box>
              {(presets ?? []).map((preset) => (
                <Box key={preset.id} sx={{ display: 'flex', alignItems: 'center', gap: '4px', minHeight: 40 }}>
                  <Box sx={{ flex: 1, minWidth: 0, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {preset.name}
                  </Box>
                  <Button size="small" disabled={overwritePreset.isPending} onClick={() => overwritePreset.mutate(preset)}>
                    {t('calendar.presetOverwrite')}
                  </Button>
                  <Button size="small" color="error" onClick={() => setPresetDeleting(preset)}>
                    {t('calendar.delete')}
                  </Button>
                </Box>
              ))}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPresetName(null)}>{t('calendar.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!presetName || presetName.trim() === '' || savePreset.isPending}
            onClick={() => presetName && savePreset.mutate(presetName.trim())}
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
    </Box>
  );
};

export default CalendarListPanel;
