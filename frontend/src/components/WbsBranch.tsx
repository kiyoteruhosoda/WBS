import React from 'react';
import { Box } from '@mui/material';
import type { SxProps, Theme } from '@mui/material';
import type { TreeGuide } from '../projects/wbsCode';
import { codeFont, ds } from '../theme';

// 枝の罫線（task #639・ADR-0061）。親の下に縦の線、子へ短い横の線。字ではない飾りなので読み上げない
const RAIL = `1px solid ${ds.primary}`;
const RAIL_OPACITY = 0.55;

type Offset = number | { xs: number; sm: number };

interface BranchProps {
  guide: TreeGuide;
  /** 深さ k の縦の線の左端（行の左端から） */
  railX: (k: number) => Offset;
  /** 横の線の長さ */
  tick: Offset;
}

/** 行（position: relative）の中に、深さに応じた枝の罫線を重ねる。深さ 0 は何も出さない。 */
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

/** WBS 番号（1.3.2）。等幅で、主色の字 */
export const WbsCode: React.FC<{ code: string | undefined }> = ({ code }) => (code ? (
  <Box component="span" data-testid="wbs-code" sx={{
    fontFamily: codeFont, fontWeight: 600, fontSize: 11, letterSpacing: '-0.02em', color: ds.primary,
    whiteSpace: 'nowrap', flexShrink: 0,
  }}>
    {code}
  </Box>
) : null);
