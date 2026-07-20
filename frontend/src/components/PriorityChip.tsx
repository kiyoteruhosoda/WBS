import React from 'react';
import { Box } from '@mui/material';
import { priorityBand } from '../utils/format';
import type { PriorityBand } from '../utils/format';
import { useI18n } from '../i18n';
import { ds } from '../theme';

const styles: Record<PriorityBand, { color: string; bg: string }> = {
  high: { color: ds.priorityHighText, bg: ds.priorityHighBg },
  mid: { color: ds.warnText, bg: ds.warnPale },
  low: { color: ds.priorityLowText, bg: ds.priorityLowBg },
};

const PriorityChip: React.FC<{ priority: number }> = ({ priority }) => {
  const { t } = useI18n();
  const band = priorityBand(priority);
  const st = styles[band];
  return (
    <Box component="span" sx={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      minWidth: 20, px: '6px', py: '2px', borderRadius: '6px',
      fontSize: 11, fontWeight: 700, lineHeight: 1.6,
      color: st.color, bgcolor: st.bg, whiteSpace: 'nowrap',
    }}>
      {t(`priority.${band}`)}
    </Box>
  );
};

export default PriorityChip;
