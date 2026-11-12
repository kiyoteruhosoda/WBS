// A row for choosing the period unit and range (first/last day) (task #162). An empty range uses the server default (6 periods ending with the current one).
import React from 'react';
import { Box, MenuItem, TextField } from '@mui/material';
import { useI18n } from '../../i18n';
import type { RangeValue } from '../../actuals/actualsView';
import type { ReportUnit } from '../../types/actuals';

interface Props {
  value: RangeValue;
  onChange: (value: RangeValue) => void;
  children?: React.ReactNode;
}

const RangeControls: React.FC<Props> = ({ value, onChange, children }) => {
  const { t } = useI18n();
  return (
    <Box sx={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center', mb: '14px' }}>
      <TextField
        select
        size="small"
        label={t('actuals.colPeriod')}
        value={value.unit}
        onChange={(e) => onChange({ ...value, unit: e.target.value as ReportUnit })}
        sx={{ minWidth: 150 }}
      >
        <MenuItem value="closing">{t('actuals.unitClosing')}</MenuItem>
        <MenuItem value="week">{t('actuals.unitWeek')}</MenuItem>
        <MenuItem value="month">{t('actuals.unitMonth')}</MenuItem>
      </TextField>
      <TextField
        size="small"
        type="date"
        label={t('actuals.from')}
        value={value.from}
        onChange={(e) => onChange({ ...value, from: e.target.value })}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField
        size="small"
        type="date"
        label={t('actuals.to')}
        value={value.to}
        onChange={(e) => onChange({ ...value, to: e.target.value })}
        slotProps={{ inputLabel: { shrink: true } }}
      />
      {children}
    </Box>
  );
};

export default RangeControls;
