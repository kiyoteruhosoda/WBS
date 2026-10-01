import React from 'react';
import { Box } from '@mui/material';
import { useI18n } from '../../i18n';
import type { TotalsTable as TotalsTableModel } from '../../closing/closingBoard';
import { formatQuarterHours } from '../../closing/closingBoard';
import { formatExactDuration } from '../../utils/format';
import { dayOfWeek } from '../../calendar/zonedTime';
import { ds } from '../../theme';

interface Props {
  table: TotalsTableModel;
}

const cell = { px: '8px', py: '6px', fontSize: 12, borderBottom: `1px solid ${ds.borderFaint}`, whiteSpace: 'nowrap' } as const;

/**
 * 日ごと・タスクごとの合計（確定で作る work_logs と同じ割り方）。表示は 15 分単位（#163）、
 * 正確な長さは吹き出しで出す。
 */
const TotalsTable: React.FC<Props> = ({ table }) => {
  const { t, weekdays } = useI18n();
  const value = (seconds: number | undefined) => (
    <Box component="span" title={seconds ? formatExactDuration(seconds) : undefined}>{formatQuarterHours(seconds ?? 0)}</Box>
  );
  return (
    <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '8px', overflow: 'hidden' }}>
      <Box sx={{ px: '14px', py: '10px', fontSize: 14, fontWeight: 700, borderBottom: `1px solid ${ds.borderFaint}` }}>
        {t('closing.totalsTitle')}
        <Box component="span" sx={{ ml: '8px', fontSize: 12, fontWeight: 400, color: ds.textMuted }}>{t('closing.totalsNote')}</Box>
      </Box>
      <Box sx={{ overflowX: 'auto' }}>
        <Box component="table" sx={{ borderCollapse: 'collapse', minWidth: '100%' }}>
          <thead>
            <tr>
              <Box component="th" sx={{ ...cell, textAlign: 'left', position: 'sticky', left: 0, bgcolor: ds.paper, minWidth: 160 }}>
                {t('closing.totalsTask')}
              </Box>
              {table.dates.map((d) => (
                <Box component="th" key={d} sx={{ ...cell, textAlign: 'right', fontWeight: 500, color: dayOfWeek(d) === 0 ? ds.dangerText : ds.textSub }}>
                  {`${Number(d.slice(8, 10))}(${weekdays[dayOfWeek(d)]})`}
                </Box>
              ))}
              <Box component="th" sx={{ ...cell, textAlign: 'right' }}>{t('closing.totalsSum')}</Box>
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row) => (
              <tr key={row.taskId ?? 'none'}>
                <Box component="td" sx={{
                  ...cell, position: 'sticky', left: 0, bgcolor: ds.paper, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis',
                  color: row.taskId == null ? ds.dangerText : ds.text, fontWeight: row.taskId == null ? 700 : 400,
                }}>
                  {row.title ?? t('closing.unassigned')}
                </Box>
                {table.dates.map((d) => (
                  <Box component="td" key={d} sx={{ ...cell, textAlign: 'right' }}>{value(row.byDate[d])}</Box>
                ))}
                <Box component="td" sx={{ ...cell, textAlign: 'right', fontWeight: 700 }}>{value(row.total)}</Box>
              </tr>
            ))}
            <tr>
              <Box component="td" sx={{ ...cell, position: 'sticky', left: 0, bgcolor: ds.paper, fontWeight: 700 }}>{t('closing.totalsDay')}</Box>
              {table.dates.map((d) => (
                <Box component="td" key={d} sx={{ ...cell, textAlign: 'right', fontWeight: 700 }}>{value(table.dayTotals[d])}</Box>
              ))}
              <Box component="td" sx={{ ...cell, textAlign: 'right', fontWeight: 700 }}>{value(table.grandTotal)}</Box>
            </tr>
          </tbody>
        </Box>
      </Box>
    </Box>
  );
};

export default TotalsTable;
