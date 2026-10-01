// カテゴリ別・マイルストーン別の積み上げ（task #162、ADR-0017）。期間ごとに横棒 1 本、表も添える。
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert, Box, CircularProgress, MenuItem, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TextField,
} from '@mui/material';
import { ACTUALS_KEY, getBreakdown } from '../../api/actuals';
import {
  formatSeconds, groupFill, rangeParams, stackSegments, totalOf,
} from '../../actuals/actualsView';
import type { RangeValue } from '../../actuals/actualsView';
import { useI18n } from '../../i18n';
import { categoryColor, ds } from '../../theme';
import type { BreakdownGroup, BreakdownGroupBy, TimeSource } from '../../types/actuals';
import RangeControls from './RangeControls';

const BreakdownPanel: React.FC = () => {
  const { t } = useI18n();
  const [range, setRange] = useState<RangeValue>({ unit: 'closing', from: '', to: '' });
  const [groupBy, setGroupBy] = useState<BreakdownGroupBy>('category');
  const [source, setSource] = useState<TimeSource>('confirmed');
  const { data, isLoading, error } = useQuery({
    queryKey: [...ACTUALS_KEY, 'breakdown', range, groupBy, source],
    queryFn: () => getBreakdown(range.unit, groupBy, source, rangeParams(range)),
  });

  const groups = data?.groups ?? [];
  // マイルストーンの色は並び順で決める（絞り込みで並びが変わっても、同じ並びの中では同じ色）
  const milestoneOrder = new Map(groups.filter((g) => g.key.startsWith('milestone:')).map((g, i) => [g.key, i]));
  const fill = (g: BreakdownGroup) => groupFill(g, milestoneOrder.get(g.key) ?? 0, categoryColor);
  const groupName = (g: BreakdownGroup): string => {
    if (g.key === 'unassigned') return t('actuals.groupUnassigned');
    if (g.key === 'none') return groupBy === 'category' ? t('actuals.groupNone') : t('actuals.groupNoMilestone');
    return g.name ?? '';
  };
  const names = new Map(groups.map((g) => [g.key, groupName(g)]));
  const fills = new Map(groups.map((g) => [g.key, fill(g)]));
  const maxTotal = Math.max(0, ...(data?.periods ?? []).map((p) => totalOf(p.seconds_by_group)));

  return (
    <Box>
      <RangeControls value={range} onChange={setRange}>
        <TextField select size="small" value={groupBy} onChange={(e) => setGroupBy(e.target.value as BreakdownGroupBy)} sx={{ minWidth: 150 }}>
          <MenuItem value="category">{t('actuals.groupByCategory')}</MenuItem>
          <MenuItem value="milestone">{t('actuals.groupByMilestone')}</MenuItem>
        </TextField>
        <TextField select size="small" value={source} onChange={(e) => setSource(e.target.value as TimeSource)} sx={{ minWidth: 120 }}>
          <MenuItem value="confirmed">{t('actuals.sourceConfirmed')}</MenuItem>
          <MenuItem value="tracked">{t('actuals.sourceTracked')}</MenuItem>
          <MenuItem value="planned">{t('actuals.sourcePlanned')}</MenuItem>
        </TextField>
      </RangeControls>

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress /></Box>}
      {error && <Alert severity="error">{t('common.loadError')}</Alert>}
      {data && groups.length === 0 && (
        <Box sx={{ p: '32px', textAlign: 'center', fontSize: 13, color: ds.textMuted }}>{t('actuals.breakdownEmpty')}</Box>
      )}
      {data && groups.length > 0 && (
        <>
          {/* 凡例（積み上げの順と同じ） */}
          <Box sx={{ display: 'flex', gap: '14px', flexWrap: 'wrap', mb: '12px', fontSize: 12, color: ds.textSub }}>
            {groups.map((g) => (
              <Box key={g.key} sx={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Box sx={{ width: 12, height: 12, borderRadius: '3px', background: fill(g) }} />
                {names.get(g.key)}
              </Box>
            ))}
          </Box>

          <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', p: '14px', mb: '14px' }}>
            {data.periods.map((p) => {
              const total = totalOf(p.seconds_by_group);
              return (
                <Box key={p.first_day} sx={{ display: 'flex', alignItems: 'center', gap: '12px', py: '6px' }}>
                  <Box sx={{ width: 170, flexShrink: 0, fontSize: 12, color: ds.textSub, whiteSpace: 'nowrap' }}>
                    {p.first_day}〜{p.last_day}
                  </Box>
                  <Box sx={{ flex: 1, display: 'flex', gap: '2px', height: 16, minWidth: 0 }}>
                    {stackSegments(groups, p.seconds_by_group, maxTotal).map((s, i, all) => {
                      const label = `${names.get(s.key)} ${formatSeconds(s.seconds)}`;
                      return (
                        <Box
                          key={s.key}
                          title={label}
                          aria-label={label}
                          sx={{
                            width: `${s.share * 100}%`, background: fills.get(s.key),
                            borderRadius: i === all.length - 1 ? '0 4px 4px 0' : 0,
                            '&:hover': { outline: `2px solid ${ds.text}`, outlineOffset: '1px' },
                          }}
                        />
                      );
                    })}
                  </Box>
                  <Box sx={{ width: 64, flexShrink: 0, textAlign: 'right', fontSize: 12, color: ds.text }}>
                    {formatSeconds(total)}
                  </Box>
                </Box>
              );
            })}
          </Box>

          {/* 同じ数字を表でも（色だけに頼らない） */}
          <TableContainer sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('actuals.colPeriod')}</TableCell>
                  {groups.map((g) => <TableCell key={g.key} align="right">{names.get(g.key)}</TableCell>)}
                  <TableCell align="right">{t('actuals.total')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.periods.map((p) => (
                  <TableRow key={p.first_day}>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{p.first_day}〜{p.last_day}</TableCell>
                    {groups.map((g) => (
                      <TableCell key={g.key} align="right">
                        {p.seconds_by_group[g.key] ? formatSeconds(p.seconds_by_group[g.key]) : '—'}
                      </TableCell>
                    ))}
                    <TableCell align="right">{formatSeconds(totalOf(p.seconds_by_group))}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}
    </Box>
  );
};

export default BreakdownPanel;
