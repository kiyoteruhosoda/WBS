import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Button, ButtonBase, Checkbox, Chip, Collapse, IconButton, Tooltip, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import { Link as RouterLink } from 'react-router-dom';
import { useI18n } from '../../i18n';
import type { TranslationKey } from '../../i18n/translations';
import type { Calendar, CalendarViewPreset } from '../../types';
import { applyCalendarViewPreset, getCalendarViewPresets, setVisibleCalendars } from '../../api/calendars';
import { CALENDARS_QUERY, CALENDAR_VIEW_PRESETS_QUERY } from '../../calendar/calendarQueries';
import {
  allVisible, isPrivateCalendar, isWorkOnly, presetIsActive, toggledVisibleIds, withVisibleIds, workOnlyCalendarIds,
} from '../../calendar/calendarSelection';
import { eventColor } from '../../calendar/calendarColors';
import { errorDetailOf } from '../../calendar/calendarRequests';

// カレンダーの画面の「表示の切り替え」だけ（ADR-0034）。チェック・表示の組み合わせ・すべて/休みだけ/仕事だけ。
// カレンダーの追加・名前と色・仕事/プライベート・休みの層の日付・組み合わせの保存は「カレンダーの設定」
// （/calendar/settings）へ分けた。選んだ状態はサーバーに覚える（ADR-0027。端末をまたいで同じ）。
// 広い画面は横の列、狭い画面はカレンダーの上で折りたたむ。

export const CALENDAR_SETTINGS_PATH = '/calendar/settings';

interface Props {
  calendars: readonly Calendar[];
  /** 失敗を知らせる（画面の下の知らせ） */
  onError: (detail: string) => void;
}

const CalendarVisibilityPanel: React.FC<Props> = ({ calendars, onError }) => {
  const { t } = useI18n();
  const theme = useTheme();
  const c = theme.palette.calendar;
  const narrow = useMediaQuery(theme.breakpoints.down('md'));
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: presets } = useQuery({ queryKey: [CALENDAR_VIEW_PRESETS_QUERY], queryFn: getCalendarViewPresets });

  const failed = (error: unknown) => {
    void qc.invalidateQueries({ queryKey: [CALENDARS_QUERY] });
    onError(errorDetailOf(error) ?? '');
  };
  const putCalendars = (list: Calendar[]) => qc.setQueryData<Calendar[]>([CALENDARS_QUERY], list);

  // 応答を待たずに見せ、サーバーに覚えさせる（失敗したら取り直して戻る）
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

  // 予定のカレンダーと休みの 4 層（ADR-0029）を分けて並べる
  const sections: { key: string; title: TranslationKey; calendars: Calendar[] }[] = [
    { key: 'events', title: 'calendar.sectionEvents' as TranslationKey, calendars: calendars.filter((cal) => cal.kind === 'EVENTS') },
    { key: 'days-off', title: 'calendar.sectionDaysOff' as TranslationKey, calendars: calendars.filter((cal) => cal.kind !== 'EVENTS') },
  ].filter((section) => section.calendars.length > 0);
  const layersOnlyActive = calendars.some((cal) => cal.kind !== 'EVENTS')
    && calendars.every((cal) => cal.is_visible === (cal.kind !== 'EVENTS'));
  const hasPrivate = calendars.some(isPrivateCalendar);
  const visibleCount = calendars.filter((cal) => cal.is_visible).length;
  const activePreset = (presets ?? []).find((preset) => presetIsActive(preset, calendars));
  const title = activePreset
    ? t('calendar.calendarsTitlePreset', { name: activePreset.name, visible: visibleCount, total: calendars.length })
    : t('calendar.calendarsTitle', { visible: visibleCount, total: calendars.length });

  const settingsLink = (
    <Tooltip title={t('calendar.settingsOpen')}>
      <IconButton
        component={RouterLink}
        to={CALENDAR_SETTINGS_PATH}
        aria-label={t('calendar.settingsOpen')}
        data-testid="calendar-settings-link"
        sx={{ width: 40, height: 40, color: c.textSecondary, flexShrink: 0 }}
      >
        <SettingsOutlinedIcon sx={{ fontSize: 20 }} />
      </IconButton>
    </Tooltip>
  );

  const list = (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px', p: '8px 12px' }}>
      {(presets ?? []).length > 0 && (
        <>
          <Box sx={{ fontSize: 11, color: c.textSecondary }}>{t('calendar.presets')}</Box>
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
          </Box>
        </>
      )}
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
        <Button
          size="small"
          variant="outlined"
          disabled={layersOnlyActive}
          onClick={() => show(calendars.filter((cal) => cal.kind !== 'EVENTS').map((cal) => cal.id))}
          data-testid="calendar-show-days-off"
        >
          {t('calendar.calendarShowDaysOff')}
        </Button>
        {hasPrivate && (
          <Button
            size="small"
            variant="outlined"
            disabled={isWorkOnly(calendars)}
            onClick={() => show(workOnlyCalendarIds(calendars))}
            data-testid="calendar-show-work"
          >
            {t('calendar.calendarShowWork')}
          </Button>
        )}
      </Box>
      {sections.map((section) => (
        <Box key={section.key}>
          <Box sx={{ fontSize: 11, color: c.textSecondary, mt: '4px' }}>{t(section.title)}</Box>
          <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, display: 'flex', flexDirection: 'column' }}>
            {section.calendars.map((cal) => {
              const color = eventColor(cal.color_key);
              return (
                <Box component="li" key={cal.id} data-calendar-id={cal.id}>
                  {/* 行のどこを押しても切り替わる（チェックの 40px だけでなく名前も） */}
                  <Box
                    component="label"
                    sx={{ display: 'flex', alignItems: 'center', minHeight: 40, gap: '2px', cursor: 'pointer' }}
                  >
                    <Checkbox
                      checked={cal.is_visible}
                      onChange={() => show(toggledVisibleIds(calendars, cal.id))}
                      sx={{ p: '8px', color, '&.Mui-checked': { color } }}
                    />
                    <Box sx={{
                      flex: 1, minWidth: 0, fontSize: 13, color: c.textPrimary,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {cal.name}
                      {isPrivateCalendar(cal) && (
                        <Box component="span" sx={{ ml: '6px', fontSize: 11, color: c.textSecondary }}>
                          {t('calendar.privateMark')}
                        </Box>
                      )}
                      {cal.kind === 'DAYS_OFF' && !cal.counts_as_day_off && (
                        <Box component="span" sx={{ ml: '6px', fontSize: 11, color: c.textSecondary }}>
                          {t('calendar.layerNotCounted')}
                        </Box>
                      )}
                    </Box>
                  </Box>
                </Box>
              );
            })}
          </Box>
        </Box>
      ))}
    </Box>
  );

  return (
    <Box
      data-testid="calendar-visibility-panel"
      sx={{
        display: 'flex', flexDirection: 'column', minHeight: 0, height: narrow ? 'auto' : '100%',
        bgcolor: c.surface, border: `1px solid ${c.border}`, borderRadius: '10px', overflow: 'hidden',
      }}
    >
      {narrow ? (
        <>
          <Box sx={{ display: 'flex', alignItems: 'center', pr: '4px' }}>
            <ButtonBase
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              sx={{
                flex: 1, minWidth: 0, minHeight: 44, px: '12px', justifyContent: 'space-between', gap: '8px',
                fontSize: 14, fontWeight: 600, color: c.textPrimary, textAlign: 'left',
              }}
            >
              <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</Box>
              {open ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </ButtonBase>
            {settingsLink}
          </Box>
          <Collapse in={open}>
            <Box sx={{ maxHeight: 320, overflowY: 'auto', borderTop: `1px solid ${c.border}` }}>{list}</Box>
          </Collapse>
        </>
      ) : (
        <>
          <Box sx={{
            display: 'flex', alignItems: 'center', gap: '4px', pl: '12px', pr: '4px', minHeight: 40,
            borderBottom: `1px solid ${c.border}`,
          }}>
            <Box sx={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: c.textPrimary }}>{title}</Box>
            {settingsLink}
          </Box>
          <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>{list}</Box>
        </>
      )}
    </Box>
  );
};

export default CalendarVisibilityPanel;
