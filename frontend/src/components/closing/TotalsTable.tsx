import React, { useState } from 'react';
import { Box, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { useI18n } from '../../i18n';
import type { TotalsRow, TotalsTable as TotalsTableModel } from '../../closing/closingBoard';
import { formatQuarterHours } from '../../closing/closingBoard';
import { formatExactDuration } from '../../utils/format';
import { dayOfWeek } from '../../calendar/zonedTime';
import { ds } from '../../theme';

interface Props {
  byTask: TotalsTableModel;
  byProject: TotalsTableModel;
}

type Grouping = 'task' | 'project';
/** どちらで見るかを端末に覚える（端末ごとの好み。失われても困らない） */
const GROUPING_KEY = 'wbs.closingTotalsBy';

const readGrouping = (): Grouping => {
  try {
    return window.localStorage.getItem(GROUPING_KEY) === 'project' ? 'project' : 'task';
  } catch {
    return 'task';
  }
};

const cell = { px: '8px', py: '6px', fontSize: 12, borderBottom: `1px solid ${ds.borderFaint}`, whiteSpace: 'nowrap' } as const;

/**
 * 日ごとの合計（確定で作る work_logs と同じ割り方）。タスク別とプロジェクト別（task #189。子の分を親へ積む）を
 * 切り替える。表示は 15 分単位（#163）、正確な長さは吹き出しで出す。
 */
const TotalsTable: React.FC<Props> = ({ byTask, byProject }) => {
  const { t, weekdays } = useI18n();
  const [grouping, setGrouping] = useState<Grouping>(readGrouping);
  const choose = (next: Grouping) => {
    setGrouping(next);
    try {
      window.localStorage.setItem(GROUPING_KEY, next);
    } catch {
      // 覚えられないだけで、表は切り替わる
    }
  };
  const table = grouping === 'project' ? byProject : byTask;
  const labelOf = (row: TotalsRow): string => {
    switch (row.kind) {
      case 'direct': return t('closing.totalsDirect', { name: row.title ?? '' });
      case 'unclassified': return t('closing.totalsUnclassified');
      case 'outside': return t('closing.totalsOutside');
      case 'unassigned': return t('closing.unassigned');
      default: return row.title ?? t('closing.unassigned');
    }
  };
  const isUnassigned = (row: TotalsRow) => row.kind === 'unassigned' || (row.kind === 'task' && row.taskId == null);
  const isMuted = (row: TotalsRow) => row.kind === 'unclassified' || row.kind === 'outside';
  const value = (seconds: number | undefined) => (
    <Box component="span" title={seconds ? formatExactDuration(seconds) : undefined}>{formatQuarterHours(seconds ?? 0)}</Box>
  );
  return (
    <Box data-testid="closing-totals" sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '8px', overflow: 'hidden' }}>
      <Box sx={{
        px: '14px', py: '8px', borderBottom: `1px solid ${ds.borderFaint}`,
        display: 'flex', flexWrap: 'wrap', alignItems: 'center', columnGap: '10px', rowGap: '6px',
      }}>
        <Box sx={{ fontSize: 14, fontWeight: 700 }}>{t('closing.totalsTitle')}</Box>
        <ToggleButtonGroup
          exclusive size="small" value={grouping}
          onChange={(_, v: Grouping | null) => { if (v) choose(v); }}
          aria-label={t('closing.totalsTitle')}
        >
          <ToggleButton value="task" sx={{ px: '12px', py: '3px', fontSize: 12 }} data-testid="closing-totals-by-task">
            {t('closing.totalsByTask')}
          </ToggleButton>
          <ToggleButton value="project" sx={{ px: '12px', py: '3px', fontSize: 12 }} data-testid="closing-totals-by-project">
            {t('closing.totalsByProject')}
          </ToggleButton>
        </ToggleButtonGroup>
        <Box sx={{ fontSize: 12, color: ds.textMuted }}>{t('closing.totalsNote')}</Box>
      </Box>
      <Box sx={{ overflowX: 'auto' }}>
        <Box component="table" sx={{ borderCollapse: 'collapse', minWidth: '100%' }}>
          <thead>
            <tr>
              <Box component="th" sx={{ ...cell, textAlign: 'left', position: 'sticky', left: 0, bgcolor: ds.paper, minWidth: 160 }}>
                {grouping === 'project' ? t('closing.totalsProject') : t('closing.totalsTask')}
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
              <tr key={row.key}>
                <Box component="td" title={labelOf(row)} sx={{
                  ...cell, position: 'sticky', left: 0, bgcolor: ds.paper, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis',
                  color: isUnassigned(row) ? ds.dangerText : isMuted(row) ? ds.textSub : ds.text,
                  fontWeight: isUnassigned(row) ? 700 : 400,
                }}>
                  {(row.kind === 'project' || row.kind === 'direct') && (
                    <Box component="span" sx={{
                      display: 'inline-block', width: 8, height: 8, borderRadius: '50%', mr: '6px', verticalAlign: 'middle',
                      bgcolor: row.color ?? ds.todoGray,
                    }} />
                  )}
                  {labelOf(row)}
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
