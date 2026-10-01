// 期間ごと（締めの期間・週・月）の予定と打刻の差・タスク外の割合・確定実績（task #162、ADR-0017）。
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert, Box, CircularProgress, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import { ACTUALS_KEY, getPeriodReport } from '../../api/actuals';
import {
  formatRatio, formatSeconds, formatSignedSeconds, rangeParams,
} from '../../actuals/actualsView';
import type { RangeValue } from '../../actuals/actualsView';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';
import type { PeriodComparison } from '../../types/actuals';
import RangeControls from './RangeControls';

const PLANNED_COLOR = '#2a78d6';
const TRACKED_COLOR = '#eb6834';
// タスク外は同じ色の斜線（色だけで分けない）
const offTaskFill = (color: string) => `repeating-linear-gradient(135deg, ${color} 0 3px, ${ds.paper} 3px 6px)`;

const PairBar: React.FC<{ task: number; offTask: number; max: number; color: string; label: string }> = ({
  task, offTask, max, color, label,
}) => {
  const pct = (v: number) => (max > 0 ? `${(v / max) * 100}%` : '0%');
  return (
    <Box title={label} aria-label={label} sx={{ display: 'flex', height: 8, gap: '2px', width: '100%' }}>
      {task > 0 && <Box sx={{ width: pct(task), bgcolor: color, borderRadius: '0 2px 2px 0' }} />}
      {offTask > 0 && <Box sx={{ width: pct(offTask), background: offTaskFill(color), borderRadius: '0 4px 4px 0' }} />}
    </Box>
  );
};

const PeriodsPanel: React.FC = () => {
  const { t } = useI18n();
  const [range, setRange] = useState<RangeValue>({ unit: 'closing', from: '', to: '' });
  const { data, isLoading, error } = useQuery({
    queryKey: [...ACTUALS_KEY, 'periods', range],
    queryFn: () => getPeriodReport(range.unit, rangeParams(range)),
  });
  const max = Math.max(0, ...(data?.periods ?? []).flatMap((p) => [p.planned_seconds, p.tracked_seconds]));

  const barLabel = (p: PeriodComparison, which: 'planned' | 'tracked') => {
    const total = which === 'planned' ? p.planned_seconds : p.tracked_seconds;
    const off = which === 'planned' ? p.planned_off_task_seconds : p.tracked_off_task_seconds;
    const name = which === 'planned' ? t('actuals.legendPlanned') : t('actuals.legendTracked');
    return `${name} ${formatSeconds(total)}（${t('actuals.groupUnassigned')} ${formatSeconds(off)}）`;
  };

  return (
    <Box>
      <RangeControls value={range} onChange={setRange}>
        <Box sx={{ display: 'flex', gap: '14px', fontSize: 12, color: ds.textSub, flexWrap: 'wrap' }}>
          {[{ c: PLANNED_COLOR, k: 'actuals.legendPlanned' as const }, { c: TRACKED_COLOR, k: 'actuals.legendTracked' as const }].map((l) => (
            <Box key={l.k} sx={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Box sx={{ width: 12, height: 8, bgcolor: l.c, borderRadius: '2px' }} />
              {t(l.k)}
            </Box>
          ))}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Box sx={{ width: 12, height: 8, background: offTaskFill(ds.textMuted), borderRadius: '2px' }} />
            {t('actuals.groupUnassigned')}
          </Box>
        </Box>
      </RangeControls>
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
                <TableCell align="right">{t('actuals.colPlanned')}</TableCell>
                <TableCell align="right">{t('actuals.colTracked')}</TableCell>
                <TableCell align="right">{t('actuals.colDifference')}</TableCell>
                <TableCell align="right">{t('actuals.colPlannedOff')}</TableCell>
                <TableCell align="right">{t('actuals.colTrackedOff')}</TableCell>
                <TableCell align="right">{t('actuals.colConfirmed')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.periods.map((p) => (
                <TableRow key={p.first_day} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    {p.first_day}〜{p.last_day}
                    {p.closed !== null && (
                      <Box component="span" sx={{ ml: '8px', fontSize: 11, color: p.closed ? ds.success : ds.textMuted }}>
                        {p.closed ? t('actuals.closed') : t('actuals.open')}
                      </Box>
                    )}
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <PairBar task={p.planned_task_seconds} offTask={p.planned_off_task_seconds} max={max} color={PLANNED_COLOR} label={barLabel(p, 'planned')} />
                      <PairBar task={p.tracked_task_seconds} offTask={p.tracked_off_task_seconds} max={max} color={TRACKED_COLOR} label={barLabel(p, 'tracked')} />
                    </Box>
                  </TableCell>
                  <TableCell align="right">{formatSeconds(p.planned_seconds)}</TableCell>
                  <TableCell align="right">{formatSeconds(p.tracked_seconds)}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>{formatSignedSeconds(p.difference_seconds)}</TableCell>
                  <TableCell align="right">{formatRatio(p.planned_off_task_ratio)}</TableCell>
                  <TableCell align="right">{formatRatio(p.tracked_off_task_ratio)}</TableCell>
                  <TableCell align="right">{formatSeconds(p.confirmed_seconds)}</TableCell>
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
