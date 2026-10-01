import React from 'react';
import { Badge, Box, List, ListItemButton, ListItemText } from '@mui/material';
import { useI18n } from '../../i18n';
import type { TranslationKey } from '../../i18n/translations';
import type { FindingItem, FindingKind } from '../../closing/closingBoard';
import { formatEntryRange, zonedMinuteOf } from '../../closing/closingBoard';
import { formatDate, formatExactDuration } from '../../utils/format';
import { ds } from '../../theme';

const KIND_LABEL: Record<FindingKind, TranslationKey> = {
  unassigned: 'closing.findingUnassigned',
  longRunning: 'closing.findingLongRunning',
  overlap: 'closing.findingOverlap',
  missed: 'closing.findingMissed',
};

const KIND_COLOR: Record<FindingKind, string> = {
  unassigned: ds.dangerText,
  longRunning: ds.dangerText,
  overlap: ds.warnText,
  missed: ds.textSub,
};

interface Props {
  items: readonly FindingItem[];
  timeZone: string;
  onJump: (item: FindingItem) => void;
}

/** 気付かせる物（止め忘れ・重なり・未割当・打刻の無い予定）。押すとその打刻・回へ飛ぶ。 */
const FindingsPanel: React.FC<Props> = ({ items, timeZone, onJump }) => {
  const { t } = useI18n();
  const md = (ms: number) => formatDate(zonedMinuteOf(ms, timeZone).date);
  return (
    <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '8px', overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '12px', px: '14px', py: '10px', borderBottom: `1px solid ${ds.borderFaint}` }}>
        <Badge badgeContent={items.length} color={items.some((i) => i.kind === 'unassigned') ? 'error' : 'warning'} max={999}>
          <Box sx={{ fontSize: 14, fontWeight: 700, pr: '8px' }}>{t('closing.findingsTitle')}</Box>
        </Badge>
      </Box>
      {items.length === 0 ? (
        <Box sx={{ px: '14px', py: '12px', fontSize: 13, color: ds.textMuted }}>{t('closing.findingsNone')}</Box>
      ) : (
        <List dense disablePadding sx={{ maxHeight: 320, overflowY: 'auto' }}>
          {items.map((item) => (
            <ListItemButton key={item.key} onClick={() => onJump(item)} data-testid={`finding-${item.key}`}>
              <ListItemText
                primary={(
                  <Box component="span" sx={{ display: 'flex', gap: '8px', alignItems: 'baseline' }}>
                    <Box component="span" sx={{ fontSize: 12, fontWeight: 700, color: KIND_COLOR[item.kind], flexShrink: 0 }}>
                      {t(KIND_LABEL[item.kind])}
                    </Box>
                    <Box component="span" sx={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.title ?? t('closing.unassigned')}
                    </Box>
                  </Box>
                )}
                secondary={`${md(item.startMs)} ${formatEntryRange(item, timeZone)}${
                  item.overlapSeconds != null ? `（${t('closing.overlapLength', { length: formatExactDuration(item.overlapSeconds) })}）` : ''}`}
                slotProps={{ secondary: { sx: { fontSize: 12 } } }}
              />
            </ListItemButton>
          ))}
        </List>
      )}
    </Box>
  );
};

export default FindingsPanel;
