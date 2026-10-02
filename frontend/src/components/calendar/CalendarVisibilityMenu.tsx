import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Button, ButtonBase, Checkbox, Chip, Drawer, Popover, Tooltip, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import FilterListIcon from '@mui/icons-material/FilterList';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import { Link as RouterLink } from 'react-router-dom';
import { useI18n } from '../../i18n';
import type { TranslationKey } from '../../i18n/translations';
import type { Calendar, CalendarViewPreset } from '../../types';
import { applyCalendarViewPreset, getCalendarViewPresets, setVisibleCalendars } from '../../api/calendars';
import { CALENDARS_QUERY, CALENDAR_VIEW_PRESETS_QUERY } from '../../calendar/calendarQueries';
import {
  allVisible, isDayOffLayer, isImportedCalendar, isPrivateCalendar, isWorkOnly, presetIsActive, toggledVisibleIds,
  withVisibleIds, workOnlyCalendarIds,
} from '../../calendar/calendarSelection';
import { eventColor } from '../../calendar/calendarColors';
import { errorDetailOf } from '../../calendar/calendarRequests';

// カレンダーの画面の「表示の切り替え」（ADR-0034・ADR-0035）。チェック・表示の組み合わせ・すべて/休みだけ/仕事だけ。
// 触る頻度が低い（組み合わせを一度決めたらほぼ触らない）ので常時は出さず、カレンダーの見出しの端の小さなボタンから
// 開く（広い画面はポップオーバー、狭い画面は下から出るシート）。ボタンは全部を表示しているときは印だけ、
// 絞っているときだけ組み合わせの名前か「3/5」を出す。管理（/calendar/settings）への入口はこの中のいちばん下。
// 選んだ状態はサーバーに覚える（ADR-0027。端末をまたいで同じ）。

export const CALENDAR_SETTINGS_PATH = '/calendar/settings';

interface Props {
  calendars: readonly Calendar[];
  /** 失敗を知らせる（画面の下の知らせ） */
  onError: (detail: string) => void;
}

const CalendarVisibilityMenu: React.FC<Props> = ({ calendars, onError }) => {
  const { t } = useI18n();
  const theme = useTheme();
  const c = theme.palette.calendar;
  const narrow = useMediaQuery(theme.breakpoints.down('md'));
  const qc = useQueryClient();
  // 開いているときのボタン（ポップオーバーの付け先。狭い画面のシートでも開いている印に使う）
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = anchor != null;
  const close = () => setAnchor(null);

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

  // 予定のカレンダー・取り込んだカレンダー（ADR-0037）・休みの 4 層（ADR-0029）を分けて並べる
  const sections: { key: string; title: TranslationKey; calendars: Calendar[] }[] = [
    { key: 'events', title: 'calendar.sectionEvents' as TranslationKey, calendars: calendars.filter((cal) => cal.kind === 'EVENTS') },
    { key: 'imported', title: 'calendar.sectionImported' as TranslationKey, calendars: calendars.filter(isImportedCalendar) },
    { key: 'days-off', title: 'calendar.sectionDaysOff' as TranslationKey, calendars: calendars.filter(isDayOffLayer) },
  ].filter((section) => section.calendars.length > 0);
  const layersOnlyActive = calendars.some(isDayOffLayer)
    && calendars.every((cal) => cal.is_visible === isDayOffLayer(cal));
  const hasPrivate = calendars.some(isPrivateCalendar);
  const visibleCount = calendars.filter((cal) => cal.is_visible).length;
  const activePreset = (presets ?? []).find((preset) => presetIsActive(preset, calendars));
  // 絞っているときだけボタンに出す（全部を表示しているときは何も出さない）
  const filtered = calendars.length > 0 && !allVisible(calendars);
  const summary = filtered
    ? (activePreset && !narrow ? activePreset.name : t('calendar.visibilityCount', { visible: visibleCount, total: calendars.length }))
    : null;
  const buttonLabel = activePreset
    ? t('calendar.calendarsTitlePreset', { name: activePreset.name, visible: visibleCount, total: calendars.length })
    : t('calendar.calendarsTitle', { visible: visibleCount, total: calendars.length });

  const settingsLink = (
    <Box sx={{ borderTop: `1px solid ${c.border}`, p: '4px 8px' }}>
      <Button
        component={RouterLink}
        to={CALENDAR_SETTINGS_PATH}
        size="small"
        startIcon={<SettingsOutlinedIcon sx={{ fontSize: 18 }} />}
        data-testid="calendar-settings-link"
        sx={{ color: c.textSecondary, px: '8px', py: '6px', fontSize: 13, fontWeight: 400 }}
      >
        {t('calendar.settingsOpen')}
      </Button>
    </Box>
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
          onClick={() => show(calendars.filter(isDayOffLayer).map((cal) => cal.id))}
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

  const content = (
    <Box data-testid="calendar-visibility-panel" sx={{ display: 'flex', flexDirection: 'column', minHeight: 0, bgcolor: c.surface }}>
      <Box sx={{ px: '12px', pt: '10px', fontSize: 13, fontWeight: 600, color: c.textPrimary }}>{buttonLabel}</Box>
      <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>{list}</Box>
      {settingsLink}
    </Box>
  );

  return (
    <>
      <Tooltip title={buttonLabel}>
        <ButtonBase
          onClick={(e) => setAnchor(e.currentTarget)}
          aria-label={buttonLabel}
          aria-haspopup="dialog"
          aria-expanded={open}
          data-testid="calendar-visibility-button"
          data-filtered={filtered || undefined}
          sx={{
            height: 30, minWidth: 32, px: summary ? '8px' : '6px', gap: '4px', borderRadius: '6px', flexShrink: 0,
            fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap',
            // 絞っているときだけ色を持つ（全部なら周りの印と同じ灰色）
            color: filtered ? c.blue : c.textSecondary,
            bgcolor: filtered ? c.surfaceVariant : 'transparent',
            border: `1px solid ${filtered ? c.blue : 'transparent'}`,
            '&:hover': { bgcolor: c.surfaceVariant },
            '&.Mui-focusVisible': { outline: `2px solid ${c.blue}`, outlineOffset: 1 },
          }}
        >
          <FilterListIcon sx={{ fontSize: 18 }} />
          {summary && (
            <Box component="span" sx={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>{summary}</Box>
          )}
        </ButtonBase>
      </Tooltip>
      {narrow ? (
        <Drawer
          anchor="bottom"
          open={open}
          onClose={close}
          slotProps={{ paper: { sx: { borderTopLeftRadius: '12px', borderTopRightRadius: '12px', maxHeight: '75svh' } } }}
        >
          <Box sx={{ width: 36, height: 4, borderRadius: '2px', bgcolor: c.border, mx: 'auto', mt: '8px', flexShrink: 0 }} />
          {content}
        </Drawer>
      ) : (
        <Popover
          open={open}
          anchorEl={anchor}
          onClose={close}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
          transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          slotProps={{ paper: { sx: { width: 280, maxHeight: 'min(560px, 80vh)', display: 'flex', flexDirection: 'column', mt: '4px' } } }}
        >
          {content}
        </Popover>
      )}
    </>
  );
};

export default CalendarVisibilityMenu;
