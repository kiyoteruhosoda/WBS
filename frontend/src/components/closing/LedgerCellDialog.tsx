// 工数表のセルを押したときの、その日・その行の打刻の一覧（task #389、ADR-0047）。押すと 1 本を直す窓が開く。
// 細かい操作（分ける・つなぐ・まとめて割り当て）は時間の表で行う（「時間の表で見る」）。
import React from 'react';
import { Box, Button, ButtonBase, Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
import { useI18n } from '../../i18n';
import type { EntrySegment } from '../../closing/closingBoard';
import { formatEntrySegmentRange } from '../../closing/closingBoard';
import type { TimeEntry } from '../../types';
import { formatExactDuration } from '../../utils/format';
import { ds } from '../../theme';

interface Props {
  title: string;
  segments: readonly EntrySegment[];
  readOnly: boolean;
  onClose: () => void;
  onOpenEntry: (entry: TimeEntry) => void;
  onShowInGrid: () => void;
}

const LedgerCellDialog: React.FC<Props> = ({ title, segments, readOnly, onClose, onOpenEntry, onShowInGrid }) => {
  const { t } = useI18n();
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" data-testid="closing-ledger-cell-dialog">
      <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{title}</DialogTitle>
      <DialogContent sx={{ px: { xs: '12px', sm: '24px' } }}>
        {segments.length === 0 && <Box sx={{ fontSize: 13, color: ds.textMuted }}>{t('closing.ledgerCellEmpty')}</Box>}
        {segments.map((segment) => {
          const entry = segment.entry;
          const seconds = Math.round((segment.endMinute - segment.startMinute) * 60);
          return (
            <ButtonBase
              key={segment.key}
              disabled={readOnly}
              onClick={() => onOpenEntry(entry)}
              sx={{
                width: '100%', minHeight: 48, px: '10px', gap: '10px', justifyContent: 'flex-start', textAlign: 'left',
                borderBottom: `1px solid ${ds.hairline}`, '&:hover': { bgcolor: ds.primaryPale },
              }}
            >
              <Box sx={{ fontSize: 13, color: ds.textSub, fontVariantNumeric: 'tabular-nums', flexShrink: 0, minWidth: 104 }}>
                {formatEntrySegmentRange(segment)}
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Box sx={{ fontSize: 14, color: entry.task_id == null ? ds.dangerText : ds.text, overflowWrap: 'anywhere' }}>
                  {entry.task_title ?? t('closing.unassigned')}
                </Box>
                {entry.memo && <Box sx={{ fontSize: 12, color: ds.textMuted, overflowWrap: 'anywhere' }}>{entry.memo}</Box>}
              </Box>
              {entry.source === 'auto' && (
                <Box component="span" title={t(entry.auto_mode === 'override' ? 'timeEntry.autoOverrideHint' : 'timeEntry.autoHint')} sx={{
                  fontSize: 11, lineHeight: '18px', px: '6px', borderRadius: '9px', flexShrink: 0, color: ds.textSub, border: `1px solid ${ds.border}`,
                }}>
                  {t('timeEntry.auto')}
                </Box>
              )}
              <Box sx={{ fontSize: 13, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>{formatExactDuration(seconds)}</Box>
            </ButtonBase>
          );
        })}
      </DialogContent>
      <DialogActions sx={{ px: '24px', pb: '18px' }}>
        <Button onClick={onShowInGrid} data-testid="closing-ledger-show-in-grid">{t('closing.ledgerShowInGrid')}</Button>
        <Button variant="contained" onClick={onClose}>{t('closing.ledgerClose')}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default LedgerCellDialog;
