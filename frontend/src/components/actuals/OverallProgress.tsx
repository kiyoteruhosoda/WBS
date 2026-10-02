import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box } from '@mui/material';
import { useI18n } from '../../i18n';
import { getDashboardKpi } from '../../api/dashboard';
import { ds } from '../../theme';

/**
 * 全体の進捗（完了の割合・今週完了・期限超過）。前は「今日」の右の列のいちばん下のカードだったが、
 * 今日の作業には使わないので実績の画面の 1 行に寄せた（ADR-0036）。プロジェクトの範囲に依らず全部のタスク。
 */
const OverallProgress: React.FC = () => {
  const { t } = useI18n();
  const { data: kpi } = useQuery({ queryKey: ['kpi'], queryFn: getDashboardKpi });
  if (!kpi) return null;
  const total = kpi.total_tasks;
  const done = total - kpi.incomplete_tasks;
  const donePct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <Box
      sx={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', fontSize: 13, color: ds.textSub }}
      data-testid="overall-progress"
    >
      <Box
        role="img"
        aria-label={`${t('dashboard.overall')} ${donePct}%`}
        sx={{
          width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
          background: `radial-gradient(${ds.paper} 55%, transparent 56%), conic-gradient(${ds.success} ${donePct}%, ${ds.track} 0)`,
        }}
      />
      <Box component="span" sx={{ fontWeight: 700, color: ds.text }}>{t('dashboard.overall')} {donePct}%</Box>
      <Box component="span">{t('dashboard.completedOfTotal', { done, total })}</Box>
      <Box component="span">
        {t('dashboard.thisWeekDone')} <Box component="span" sx={{ fontWeight: 700, color: ds.primary }}>{kpi.this_week_completed}</Box>
      </Box>
      <Box component="span">
        {t('dashboard.overdueCount')}{' '}
        <Box component="span" sx={{ fontWeight: 700, color: kpi.overdue_tasks > 0 ? ds.dangerText : ds.text }}>{kpi.overdue_tasks}</Box>
      </Box>
    </Box>
  );
};

export default OverallProgress;
