import React, { useEffect, useState } from 'react';
import { Box, Button, CircularProgress } from '@mui/material';
import { ds } from '../theme';
import { translate } from '../i18n';
import type { ApplyUpdate, WatchForUpdate } from '../pwa/appUpdate';

/**
 * 「新しい版があります」の知らせ（task #192・ADR-0028。雛形の ADR-0035 と同じ形）。
 *
 * 新しい版が待機したときだけ画面の下に出し、押されたら再読み込みする。トーストは使わない
 * ——見ていない間に出て消えると、古い版のまま使い続けることになる。押すまで残す。
 *
 * 見張り方（`pwa/appUpdate.ts`）は引数で受け取る（Service Worker を登録する副作用をこの部品から切り離す）。
 * ログインの外（ログイン画面）でも出すので、文言は利用者設定に頼らない `translate` で引く。
 */
const AppUpdatePrompt: React.FC<{ watch: WatchForUpdate }> = ({ watch }) => {
  const [apply, setApply] = useState<ApplyUpdate | null>(null);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    // useState は関数を「遅延初期化」と解釈するので、関数を入れるときは関数を返す関数を渡す
    watch((applyUpdate) => setApply(() => applyUpdate));
  }, [watch]);

  if (!apply) return null;

  return (
    <Box
      role="status"
      sx={{
        position: 'fixed', left: '50%', transform: 'translateX(-50%)', zIndex: 1400,
        bottom: 'calc(16px + env(safe-area-inset-bottom))', width: 'max-content', maxWidth: 'calc(100vw - 32px)',
        display: 'flex', alignItems: 'center', gap: '12px', px: '16px', py: '10px', borderRadius: '10px',
        bgcolor: ds.text, color: '#fff', boxShadow: '0 6px 24px rgba(0,0,0,0.24)', fontSize: 14,
      }}
    >
      <Box component="span">{translate('update.available')}</Box>
      <Button
        variant="contained"
        size="small"
        disabled={applying}
        onClick={() => {
          setApplying(true);
          apply();
        }}
        startIcon={applying ? <CircularProgress size={14} sx={{ color: 'inherit' }} /> : undefined}
        sx={{ minHeight: 36, flexShrink: 0, whiteSpace: 'nowrap' }}
      >
        {translate('update.reload')}
      </Button>
    </Box>
  );
};

export default AppUpdatePrompt;
