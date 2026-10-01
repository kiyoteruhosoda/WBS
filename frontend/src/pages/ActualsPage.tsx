// 実績の見える化: 予定 vs 実績・計画 vs 実績（task #162、ADR-0017）。
// /actuals はタスクごとの表。/actuals/review は「残を見直す」ものだけ（締めの直後の行き先）。
import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Box, Tab, Tabs } from '@mui/material';
import { useI18n } from '../i18n';
import TaskActualsPanel from '../components/actuals/TaskActualsPanel';
import PeriodsPanel from '../components/actuals/PeriodsPanel';
import BreakdownPanel from '../components/actuals/BreakdownPanel';
import ExportPanel from '../components/actuals/ExportPanel';

type View = 'tasks' | 'review' | 'periods' | 'breakdown' | 'export';
const VIEWS: View[] = ['tasks', 'review', 'periods', 'breakdown', 'export'];

const ActualsPage: React.FC = () => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { view: param } = useParams<{ view?: string }>();
  const view: View = VIEWS.includes(param as View) ? (param as View) : 'tasks';
  // 「残を見直す」はタスクの表を見直しが要るものに絞った形
  const tab = view === 'review' ? 'tasks' : view;
  const go = (next: View) => navigate(next === 'tasks' ? '/actuals' : `/actuals/${next}`);

  return (
    <Box>
      <Tabs value={tab} onChange={(_, v: View) => go(v)} sx={{ mb: '14px', minHeight: 40 }}>
        <Tab value="tasks" label={t('actuals.tabTasks')} />
        <Tab value="periods" label={t('actuals.tabPeriods')} />
        <Tab value="breakdown" label={t('actuals.tabBreakdown')} />
        <Tab value="export" label={t('actuals.tabExport')} />
      </Tabs>
      {tab === 'tasks' && (
        <TaskActualsPanel
          reviewOnly={view === 'review'}
          onReviewOnlyChange={(on) => go(on ? 'review' : 'tasks')}
        />
      )}
      {tab === 'periods' && <PeriodsPanel />}
      {tab === 'breakdown' && <BreakdownPanel />}
      {tab === 'export' && <ExportPanel />}
    </Box>
  );
};

export default ActualsPage;
