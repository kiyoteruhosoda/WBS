import React from 'react';
import { Box } from '@mui/material';
import { ds } from '../theme';

interface Props {
  value: number; // 0-100
  color?: string;
  height?: number;
  showLabel?: boolean;
}

const ProgressBar: React.FC<Props> = ({ value, color = ds.primary, height = 10, showLabel = false }) => {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: '10px', width: '100%' }}>
      <Box sx={{ flex: 1, height, borderRadius: height / 2, bgcolor: ds.track, overflow: 'hidden' }}>
        <Box sx={{ width: `${pct}%`, height: '100%', borderRadius: height / 2, bgcolor: color }} />
      </Box>
      {showLabel && (
        <Box sx={{ fontSize: 14, fontWeight: 700, color: ds.text, minWidth: 38, textAlign: 'right' }}>
          {pct}%
        </Box>
      )}
    </Box>
  );
};

export default ProgressBar;
