import React from 'react';
import { Box, Button, Paper, Typography } from '@mui/material';
import { ds } from '../theme';
import { translate } from '../i18n';

/**
 * 打刻アプリのログインの戻り先（`/app/oauth2redirect`。ADR-0019）。
 *
 * ふだんは Android（Chrome の Auth Tab / App Links）がアプリへ直接渡すので、この画面は出ない。
 * 出るのは PC で開いた・アプリが入っていない・結び付けの確認（assetlinks.json）が済んでいないときと、
 * アプリの中のタブが自動の移動ではアプリを開かなかったとき。後者のために、認可コードが付いていれば
 * **同じ URL をもう一度開くボタン**を出す（タップで開き直せば Chrome がアプリへ渡す）。
 * ⚠ **ここではログインを続けない**（認可コードはアプリしか引き換えられない）。ログインの外に置く
 * （未ログインの PC で開いてもログイン画面へ飛ばさない）。
 */
const AppReturnPage: React.FC = () => {
  const query = new URLSearchParams(window.location.search);
  const handingBack = query.has('code') && query.has('state');

  return (
    <Box sx={{ minHeight: '100svh', display: 'grid', placeItems: 'center', bgcolor: ds.canvas, p: 2 }}>
      <Paper
        elevation={0}
        sx={{
          width: '100%', maxWidth: 380, p: '32px', borderRadius: '12px',
          border: `1px solid ${ds.border}`, textAlign: 'center',
        }}
      >
        <Typography component="h1" sx={{ fontSize: 18, fontWeight: 700, color: ds.text, mb: '12px' }}>
          {translate('appReturn.title')}
        </Typography>
        {handingBack && (
          <>
            <Typography sx={{ fontSize: 14, color: ds.textMuted, mb: '16px' }}>
              {translate('appReturn.tapToReturn')}
            </Typography>
            <Button variant="contained" fullWidth href={window.location.href} sx={{ py: '10px', mb: '16px' }}>
              {translate('appReturn.returnToApp')}
            </Button>
          </>
        )}
        <Typography sx={{ fontSize: 14, color: ds.textMuted, mb: '16px' }}>
          {translate('appReturn.body')}
        </Typography>
        <Button variant="text" href="/">
          {translate('appReturn.openWeb')}
        </Button>
      </Paper>
    </Box>
  );
};

export default AppReturnPage;
