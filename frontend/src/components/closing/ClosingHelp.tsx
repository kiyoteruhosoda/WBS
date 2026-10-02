import React, { useState } from 'react';
import { Box, IconButton, Popover, Tooltip } from '@mui/material';
import HelpOutlineIcon from '@mui/icons-material/HelpOutlineOutlined';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';

/** 説明を一度見た（閉じた）ことを端末に覚える鍵。 */
const SEEN_KEY = 'wbs.closing.helpSeen';

const readSeen = (): boolean => {
  try {
    return window.localStorage.getItem(SEEN_KEY) === '1';
  } catch {
    // 読めない（プライベートの窓など）ときは毎回出さない。? からいつでも開ける
    return true;
  }
};

const writeSeen = () => {
  try {
    window.localStorage.setItem(SEEN_KEY, '1');
  } catch {
    // 覚えられなくても、閉じたことは今の画面では効いている
  }
};

/**
 * 締めの格子の操作の説明（ADR-0036）。前は操作の行の右に常に出ていたが、読むのは最初だけなので
 * ? のボタンにしまった。この端末で初めて締めを開いたときだけ、自分で開いて見せる（閉じたら次からは出さない）。
 * ツールチップではなく押して開く形にしたのは、指ではツールチップが出ないため。
 */
const ClosingHelp: React.FC = () => {
  const { t } = useI18n();
  // 開く位置のボタン（描いたあとに決まるので state で持つ。決まるまでは開かない）
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(() => !readSeen());

  const close = () => {
    setOpen(false);
    writeSeen();
  };

  return (
    <>
      <Tooltip title={t('closing.help')}>
        <IconButton
          ref={setAnchor}
          aria-label={t('closing.help')}
          aria-expanded={open}
          onClick={() => setOpen(true)}
          sx={{ width: 36, height: 36, color: ds.textSub }}
          data-testid="closing-help"
        >
          <HelpOutlineIcon sx={{ fontSize: 20 }} />
        </IconButton>
      </Tooltip>
      <Popover
        open={open && anchor != null}
        anchorEl={anchor}
        onClose={close}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Box sx={{ p: '12px 14px', maxWidth: 320, fontSize: 13, lineHeight: 1.7, color: ds.text }} data-testid="closing-help-text">
          <Box sx={{ fontWeight: 700, mb: '4px' }}>{t('closing.help')}</Box>
          {t('closing.dragHint')}
        </Box>
      </Popover>
    </>
  );
};

export default ClosingHelp;
