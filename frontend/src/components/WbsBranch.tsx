import React from 'react';
import { Box } from '@mui/material';
import type { SxProps, Theme } from '@mui/material';
import type { TreeGuide } from '../projects/wbsCode';
import { codeFont, ds } from '../theme';

// Branch lines (task #639, ADR-0061). A vertical line under the parent and a short horizontal line to the child. Decorative, not text, so hidden from screen readers
const RAIL = `1px solid ${ds.primary}`;
const RAIL_OPACITY = 0.55;

type Offset = number | { xs: number; sm: number };

interface BranchProps {
  guide: TreeGuide;
  /** Left edge of the vertical line at depth k (from the row's left edge) */
  railX: (k: number) => Offset;
  /** Length of the horizontal line */
  tick: Offset;
}

/** Overlays branch lines for the depth inside a row (position: relative). Depth 0 renders nothing. */
export const WbsBranch: React.FC<BranchProps> = ({ guide, railX, tick }) => {
  if (guide.level === 0) return null;
  const line = (sx: Record<string, unknown>, key: string) => (
    <Box key={key} aria-hidden sx={{ position: 'absolute', opacity: RAIL_OPACITY, pointerEvents: 'none', ...sx } as SxProps<Theme>} />
  );
  return (
    <>
      {guide.rails.map((on, i) => (on ? line({ left: railX(i + 1), top: 0, bottom: 0, borderLeft: RAIL }, `r${i}`) : null))}
      {line({ left: railX(guide.level), top: 0, bottom: guide.last ? '50%' : 0, borderLeft: RAIL }, 'own')}
      {line({ left: railX(guide.level), top: '50%', width: tick, borderTop: RAIL }, 'tick')}
    </>
  );
};

/** WBS number (1.3.2). Monospace, in the primary color */
export const WbsCode: React.FC<{ code: string | undefined }> = ({ code }) => (code ? (
  <Box component="span" data-testid="wbs-code" sx={{
    fontFamily: codeFont, fontWeight: 600, fontSize: 11, letterSpacing: '-0.02em', color: ds.primary,
    whiteSpace: 'nowrap', flexShrink: 0,
  }}>
    {code}
  </Box>
) : null);
