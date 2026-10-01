import React from 'react';
import { Box } from '@mui/material';
import CheckBoxIcon from '@mui/icons-material/CheckBox';
import CheckBoxOutlineBlankIcon from '@mui/icons-material/CheckBoxOutlineBlank';
import { useI18n } from '../../i18n';

interface Props {
  done: boolean;
  /** 押して済みを切り替える。省くと印だけ（月表示のチップなど） */
  onToggle?: () => void;
  size?: number;
  color: string;
  sx?: object;
}

/**
 * タスクの分類の回の印（ADR-0025）。チェックの形で、済みなら塗りつぶし。
 * 押せるときはボタンで、押してもブロックの選択・編集にはしない（呼び手がドラッグとの区別を見る）。
 */
const DoneMark: React.FC<Props> = ({ done, onToggle, size = 12, color, sx }) => {
  const { t } = useI18n();
  const Icon = done ? CheckBoxIcon : CheckBoxOutlineBlankIcon;
  const label = t(done ? 'calendar.markUndone' : 'calendar.markDone');
  if (!onToggle) {
    return <Icon titleAccess={t(done ? 'calendar.done' : 'calendar.eventTypeTASK')} sx={{ fontSize: size, color, flexShrink: 0, ...sx }} />;
  }
  return (
    <Box
      component="button"
      type="button"
      role="checkbox"
      aria-checked={done}
      aria-label={label}
      title={label}
      data-testid="done-mark"
      onClick={(e: React.MouseEvent) => { e.stopPropagation(); onToggle(); }}
      onDoubleClick={(e: React.MouseEvent) => e.stopPropagation()}
      sx={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        p: 0, m: 0, border: 'none', bgcolor: 'transparent', cursor: 'pointer', color, lineHeight: 0, ...sx,
      }}
    >
      <Icon sx={{ fontSize: size }} />
    </Box>
  );
};

export default DoneMark;
