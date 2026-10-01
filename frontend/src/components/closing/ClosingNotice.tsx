import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button } from '@mui/material';
import { useLocation, useNavigate } from 'react-router-dom';
import { useI18n } from '../../i18n';
import { PENDING_CLOSINGS_KEY, getPendingClosings } from '../../api/closing';
import { PERIOD_PARAM } from '../../closing/closingPeriods';
import { dateRangeParts } from '../../utils/format';

/**
 * 全画面の上部の「未確定の期間があります」（#163: 外への通知はしない。ADR-0012）。
 * いちばん古い未確定の期間を出し、押すと締めの画面でその期間を開く。締めの画面の上では出さない。
 */
const ClosingNotice: React.FC = () => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const { data } = useQuery({ queryKey: PENDING_CLOSINGS_KEY, queryFn: getPendingClosings, staleTime: 5 * 60_000 });
  if (!data?.has_pending || location.pathname.startsWith('/closing')) return null;
  const oldest = data.pending[0];
  const label = dateRangeParts(oldest.first_day, oldest.last_day);
  const open = () => navigate(`/closing?${PERIOD_PARAM}=${oldest.first_day}`);
  return (
    <Alert
      severity="warning"
      data-testid="closing-notice"
      // 押す口（締めへ）は文と同じ高さに置き、狭い画面でも 1 文字ずつ折り返さない
      sx={{ mb: '16px', cursor: 'pointer', alignItems: 'center', '& .MuiAlert-action': { pt: 0, alignItems: 'center' } }}
      onClick={open}
      action={(
        <Button color="inherit" size="small" sx={{ whiteSpace: 'nowrap', flexShrink: 0 }} onClick={(e) => { e.stopPropagation(); open(); }}>
          {t('closing.noticeOpen')}
        </Button>
      )}
    >
      {t('closing.notice', { count: data.pending.length, from: label.from, to: label.to })}
    </Alert>
  );
};

export default ClosingNotice;
