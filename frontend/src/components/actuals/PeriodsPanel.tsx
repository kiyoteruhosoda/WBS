// 期間ごと（半月・週・月）の確定実績（task #162、ADR-0017。予定と打刻は task #543・ADR-0070 で外した）。
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert, Box, CircularProgress, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import { ACTUALS_KEY, getPeriodReport } from '../../api/actuals';
import { scopeParams } from '../../projects/projectScope';
import { useProjectScope } from '../../projects/useProjectScope';
import { rangeParams } from '../../actuals/actualsView';
import { dateRangeParts, formatSecondsAsHours } from '../../utils/format';
import type { RangeValue } from '../../actuals/actualsView';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';
import RangeControls from './RangeControls';

const PeriodsPanel: React.FC = () => {
  const { t } = useI18n();
  const [range, setRange] = useState<RangeValue>({ unit: 'closing', from: '', to: '' });
  const { scope } = useProjectScope();
  const { data, isLoading, error } = useQuery({
    queryKey: [...ACTUALS_KEY, 'periods', range, scope],
    queryFn: () => getPeriodReport(range.unit, rangeParams(range), scopeParams(scope)),
  });
  const max = Math.max(0, ...(data?.periods ?? []).map((p) => p.confirmed_seconds));
  const pct = (v: number) => (max > 0 ? `${(v / max) * 100}%` : '0%');

  return (
    <Box>
      <RangeControls value={range} onChange={setRange} />
      <Box sx={{ fontSize: 12, color: ds.textMuted, mb: '10px' }}>{t('actuals.periodsHelp')}</Box>

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress /></Box>}
      {error && <Alert severity="error">{t('common.loadError')}</Alert>}
      {data && (
        <TableContainer sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('actuals.colPeriod')}</TableCell>
                <TableCell sx={{ minWidth: 160 }} />
                <TableCell align="right">{t('actuals.colConfirmed')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.periods.map((p) => (
                <TableRow key={p.first_day} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    {t('common.dateRange', dateRangeParts(p.first_day, p.last_day))}
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', height: 8, width: '100%' }}>
                      {p.confirmed_seconds > 0 && (
                        <Box sx={{ width: pct(p.confirmed_seconds), bgcolor: ds.primary, borderRadius: '0 2px 2px 0' }} />
                      )}
                    </Box>
                  </TableCell>
                  <TableCell align="right">{formatSecondsAsHours(p.confirmed_seconds)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
};

export default PeriodsPanel;
