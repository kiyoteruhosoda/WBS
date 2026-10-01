// CSV の書き出し（期間 × 日 × タスク × 時間。task #162、ADR-0017）。既定は締めの直前の期間。
import React, { useState } from 'react';
import { Box, Button, MenuItem, TextField } from '@mui/material';
import { exportCsvUrl } from '../../api/actuals';
import { previousClosingPeriod } from '../../actuals/actualsView';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';
import type { TimeSource } from '../../types/actuals';
import { todayDate } from '../../utils/format';

const ExportPanel: React.FC = () => {
  const { t } = useI18n();
  const [range, setRange] = useState(() => previousClosingPeriod(todayDate()));
  const [source, setSource] = useState<TimeSource>('confirmed');
  const valid = range.from !== '' && range.to !== '' && range.from <= range.to;

  return (
    <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', p: '18px' }}>
      <Box sx={{ fontSize: 13, color: ds.textSub, mb: '14px' }}>{t('actuals.exportHelp')}</Box>
      <Box sx={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField
          size="small" type="date" label={t('actuals.from')} value={range.from}
          onChange={(e) => setRange({ ...range, from: e.target.value })}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          size="small" type="date" label={t('actuals.to')} value={range.to}
          onChange={(e) => setRange({ ...range, to: e.target.value })}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField select size="small" value={source} onChange={(e) => setSource(e.target.value as TimeSource)} sx={{ minWidth: 120 }}>
          <MenuItem value="confirmed">{t('actuals.sourceConfirmed')}</MenuItem>
          <MenuItem value="tracked">{t('actuals.sourceTracked')}</MenuItem>
          <MenuItem value="planned">{t('actuals.sourcePlanned')}</MenuItem>
        </TextField>
        <Button
          component="a"
          variant="contained"
          disabled={!valid}
          href={valid ? exportCsvUrl(range.from, range.to, source) : undefined}
          download
        >
          {t('actuals.exportDownload')}
        </Button>
      </Box>
    </Box>
  );
};

export default ExportPanel;
