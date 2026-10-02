import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Button, IconButton, TextField } from '@mui/material';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined';
import { useI18n } from '../../i18n';
import type { Calendar } from '../../types';
import { addLayerDay, getLayerDays, importLayerJapaneseHolidays, removeLayerDay } from '../../api/calendars';
import { DAY_OFF_MARKS_QUERY, OCCURRENCES_QUERY } from '../../calendar/calendarQueries';
import { errorDetailOf } from '../../calendar/calendarRequests';
import { formatDate } from '../../utils/format';

// 休みの日の一覧の層（会社の公休・私の休み・日本の祝日）の日を年ごとに並べ、足す・消す（ADR-0029）。
// 日本の祝日の層は「この年の祝日を入れる」（暦から出す。外へは取りに行かない）。
// 書いたら休みの塗りと、営業日シフトで動く回を読み直させる。

interface Props {
  layer: Calendar;
  /** 最初に開く年 */
  initialYear: number;
  onError: (detail: string) => void;
}

const LAYER_DAYS_QUERY = 'calendar-layer-days';

const DayOffLayerDays: React.FC<Props> = ({ layer, initialYear, onError }) => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [year, setYear] = useState(initialYear);
  const [date, setDate] = useState('');
  const [name, setName] = useState('');
  const range = { from: `${year}-01-01`, to: `${year}-12-31` };
  const key = [LAYER_DAYS_QUERY, layer.id, year];
  const { data: days } = useQuery({ queryKey: key, queryFn: () => getLayerDays(layer.id, range) });

  const written = (list: unknown) => {
    qc.setQueryData(key, list);
    for (const queryKey of [[DAY_OFF_MARKS_QUERY], [OCCURRENCES_QUERY]]) void qc.invalidateQueries({ queryKey });
  };
  const failed = (error: unknown) => onError(errorDetailOf(error) ?? '');

  const add = useMutation({
    mutationFn: () => addLayerDay(layer.id, { date, name: name.trim() || null }),
    onSuccess: (list) => {
      if (date.slice(0, 4) === String(year)) written(list);
      else for (const queryKey of [[DAY_OFF_MARKS_QUERY], [OCCURRENCES_QUERY]]) void qc.invalidateQueries({ queryKey });
      setDate('');
      setName('');
    },
    onError: failed,
  });
  const remove = useMutation({ mutationFn: (day: string) => removeLayerDay(layer.id, day), onSuccess: written, onError: failed });
  const importYear = useMutation({
    mutationFn: () => importLayerJapaneseHolidays(layer.id, year),
    onSuccess: written,
    onError: failed,
  });

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }} data-testid="layer-days">
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <IconButton size="small" aria-label={t('calendar.layerPrevYear')} onClick={() => setYear((y) => y - 1)}>
          <ChevronLeftIcon />
        </IconButton>
        <Box sx={{ fontSize: 14, fontWeight: 600, minWidth: 64, textAlign: 'center' }}>{t('calendar.layerYear', { year })}</Box>
        <IconButton size="small" aria-label={t('calendar.layerNextYear')} onClick={() => setYear((y) => y + 1)}>
          <ChevronRightIcon />
        </IconButton>
        {layer.day_off_reason === 'NATIONAL_HOLIDAY' && (
          <Button size="small" sx={{ ml: 'auto' }} disabled={importYear.isPending} onClick={() => importYear.mutate()}>
            {t('calendar.layerImportJapan', { year })}
          </Button>
        )}
      </Box>
      <Box sx={{ maxHeight: 200, overflowY: 'auto', border: 1, borderColor: 'divider', borderRadius: '6px' }}>
        {(days ?? []).length === 0 && (
          <Box sx={{ fontSize: 13, color: 'text.secondary', p: '8px' }}>{t('calendar.layerNoDays')}</Box>
        )}
        {(days ?? []).map((d) => (
          <Box key={d.date} sx={{ display: 'flex', alignItems: 'center', gap: '8px', px: '8px', minHeight: 36 }}>
            <Box sx={{ fontSize: 13, minWidth: 96 }}>{formatDate(d.date)}</Box>
            <Box sx={{ fontSize: 13, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {d.name ?? ''}
            </Box>
            <IconButton
              size="small"
              aria-label={t('calendar.layerRemoveDay', { date: formatDate(d.date) })}
              disabled={remove.isPending}
              onClick={() => remove.mutate(d.date)}
            >
              <DeleteOutlineIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </Box>
        ))}
      </Box>
      <Box sx={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField
          type="date"
          size="small"
          label={t('calendar.layerDayDate')}
          value={date}
          onChange={(e) => setDate(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ flex: '1 1 140px' }}
        />
        <TextField
          size="small"
          label={t('calendar.layerDayName')}
          value={name}
          onChange={(e) => setName(e.target.value)}
          slotProps={{ htmlInput: { maxLength: 200 } }}
          sx={{ flex: '1 1 140px' }}
        />
        <Button size="small" variant="outlined" disabled={!date || add.isPending} onClick={() => add.mutate()}>
          {t('calendar.layerAddDay')}
        </Button>
      </Box>
    </Box>
  );
};

export default DayOffLayerDays;
