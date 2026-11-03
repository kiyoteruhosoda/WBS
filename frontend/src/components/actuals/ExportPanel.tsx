// CSV の書き出し（期間 × 日 × タスク × 確定実績。task #162、ADR-0017）。既定は直前の半月。
import React, { useState } from 'react';
import { Box, Button, TextField } from '@mui/material';
import { exportCsvUrl } from '../../api/actuals';
import { scopeParams } from '../../projects/projectScope';
import { useProjectScope } from '../../projects/useProjectScope';
import { previousClosingPeriod } from '../../actuals/actualsView';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';
import { todayDate } from '../../utils/format';

const ExportPanel: React.FC = () => {
  const { t } = useI18n();
  const [range, setRange] = useState(() => previousClosingPeriod(todayDate()));
  const { scope } = useProjectScope();
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
        <Button
          component="a"
          variant="contained"
          disabled={!valid}
          href={valid ? exportCsvUrl(range.from, range.to, scopeParams(scope)) : undefined}
          download
        >
          {t('actuals.exportDownload')}
        </Button>
      </Box>
    </Box>
  );
};

export default ExportPanel;
