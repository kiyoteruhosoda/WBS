import React, { useEffect, useRef, useState } from 'react';
import { Box, Button, CircularProgress } from '@mui/material';
import { ds } from '../theme';
import { translate } from '../i18n';
import type { ApplyUpdate, WatchForUpdate } from '../pwa/appUpdate';
import { followUpdateBarHeight } from '../pwa/updateBarHeight';

/**
 * 「新しい版があります」の知らせ（task #192・ADR-0028。雛形の ADR-0035 と同じ形）。
 *
 * 新しい版が待機したときだけ**画面のいちばん上に横幅いっぱいの帯**で出し、押されたら再読み込みする
 * （出す場所は ADR-0072）。帯はどの画面にも出し（ログイン画面にはヘッダーが無いので、ヘッダーの中ではなく
 * その上に置く）、下へ送っても上に残す。ヘッダーと左のメニューが帯の真下に付くよう、帯の高さを
 * CSS 変数 `--update-bar-height` で渡す（`pwa/updateBarHeight.ts`）。
 * トーストや画面の下に浮かぶ知らせは使わない ——消えたり本文に紛れたりして、古い版のまま使い続けることになる。
 *
 * 見張り方（`pwa/appUpdate.ts`）は引数で受け取る（Service Worker を登録する副作用をこの部品から切り離す）。
 * ログインの外（ログイン画面）でも出すので、文言は利用者設定に頼らない `translate` で引く。
 */
const AppUpdatePrompt: React.FC<{ watch: WatchForUpdate }> = ({ watch }) => {
  const [apply, setApply] = useState<ApplyUpdate | null>(null);
  const [applying, setApplying] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // useState は関数を「遅延初期化」と解釈するので、関数を入れるときは関数を返す関数を渡す
    watch((applyUpdate) => setApply(() => applyUpdate));
  }, [watch]);

  // 帯の高さをヘッダーと左のメニューの貼り付く位置へ渡す。帯が消えたら外す。
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
        // 下へ送っても上に残す。重ねずに場所を取るので、ヘッダーや本文の先頭を隠さない。
        // z-index はヘッダー（10）より上、狭い画面のメニュー（MUI の Drawer は 1200）より下。
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
        // 帯と同じ色だと沈むので、色を反転させて押せる所だと分かるようにする
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
