import React, { useEffect, useRef, useState } from 'react';
import { Box, Button, CircularProgress } from '@mui/material';
import { ds } from '../theme';
import { translate } from '../i18n';
import type { ApplyUpdate, WatchForUpdate } from '../pwa/appUpdate';
import { followUpdateBarHeight } from '../pwa/updateBarHeight';

/**
 * The "new version available" notice (task #192, ADR-0028; same shape as the template's ADR-0035).
 *
 * Shown only when a new version is waiting, as a **full-width bar at the very top of the screen**; clicking it reloads
 * (placement per ADR-0072). The bar appears on every screen (the login screen has no header, so it sits above
 * the header rather than inside it) and stays at the top when scrolling. So the header and left menu sit right below it,
 * the bar's height is passed via the CSS variable `--update-bar-height` (`pwa/updateBarHeight.ts`).
 * No toasts or floating notices at the bottom -- they vanish or blend into the content and people keep using the old version.
 *
 * The watcher (`pwa/appUpdate.ts`) is passed in as an argument (keeps the Service Worker registration side effect out of this component).
 * It is also shown outside login (on the login screen), so its text comes from `translate`, which doesn't depend on user settings.
 */
const AppUpdatePrompt: React.FC<{ watch: WatchForUpdate }> = ({ watch }) => {
  const [apply, setApply] = useState<ApplyUpdate | null>(null);
  const [applying, setApplying] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // useState treats a function as a lazy initializer, so to store a function pass a function that returns it
    watch((applyUpdate) => setApply(() => applyUpdate));
  }, [watch]);

  // Pass the bar height to where the header and left menu stick. Remove it when the bar goes away.
  useEffect(() => {
    const bar = barRef.current;
    if (!apply || bar === null) return undefined;
    return followUpdateBarHeight(bar, document.documentElement);
  }, [apply]);

  if (!apply) return null;

  return (
    <Box
      ref={barRef}
      role="status"
      className="update-bar"
      sx={{
        // Stays at the top when scrolling. It takes up space instead of overlapping, so it doesn't hide the header or the top of the content.
        // z-index is above the header (10) and below the narrow-screen menu (MUI Drawer is 1200).
        position: 'sticky', top: 0, zIndex: 1100,
        display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center',
        columnGap: '12px', rowGap: '6px', py: '8px',
        pl: 'max(16px, env(safe-area-inset-left))', pr: 'max(16px, env(safe-area-inset-right))',
        bgcolor: ds.primary, color: '#fff', fontSize: 14, fontWeight: 600, textAlign: 'center',
      }}
    >
      <Box component="span">{translate('update.available')}</Box>
      <Button
        className="update-bar-button"
        variant="contained"
        size="small"
        disabled={applying}
        onClick={() => {
          setApplying(true);
          apply();
        }}
        startIcon={applying ? <CircularProgress size={14} sx={{ color: 'inherit' }} /> : undefined}
        // The same color as the bar would blend in, so invert the colors to make it clearly clickable
        sx={{
          minHeight: 36, flexShrink: 0, whiteSpace: 'nowrap', bgcolor: '#fff', color: ds.primary,
          '&:hover': { bgcolor: ds.primaryPale },
          '&.Mui-disabled': { bgcolor: ds.primaryPale, color: ds.primary },
        }}
      >
        {translate('update.reload')}
      </Button>
    </Box>
  );
};

export default AppUpdatePrompt;
