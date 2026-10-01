import React, { useMemo, useState } from 'react';
import {
  Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, List, ListItemButton, ListItemText, ListSubheader, TextField,
} from '@mui/material';
import { useI18n } from '../../i18n';
import type { TaskCandidate } from '../../closing/closingBoard';
import { ds } from '../../theme';

interface Props {
  open: boolean;
  entryCount: number;
  candidates: readonly TaskCandidate[];
  onCancel: () => void;
  /** null は未割当へ戻す */
  onChoose: (taskId: number | null) => void;
}

/** 選んだ打刻にまとめてタスクを振る。同じ時間の予定のタスクを先頭に出す。 */
const AssignTaskDialog: React.FC<Props> = ({ open, entryCount, candidates, onCancel, onChoose }) => {
  const { t } = useI18n();
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? candidates.filter((c) => c.title.toLowerCase().includes(q)) : candidates;
  }, [candidates, query]);
  const scheduled = filtered.filter((c) => c.fromSchedule);
  const others = filtered.filter((c) => !c.fromSchedule);

  const item = (c: TaskCandidate) => (
    <ListItemButton key={c.taskId} onClick={() => onChoose(c.taskId)} data-testid={`assign-task-${c.taskId}`}>
      <ListItemText primary={c.title} slotProps={{ primary: { sx: { fontSize: 14 } } }} />
    </ListItemButton>
  );

  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>{t('closing.assignTitle', { count: entryCount })}</DialogTitle>
      <DialogContent dividers sx={{ p: 0 }}>
        <Box sx={{ p: '12px 16px' }}>
          <TextField
            autoFocus size="small" fullWidth value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder={t('closing.assignSearch')}
          />
        </Box>
        <List dense sx={{ maxHeight: 380, overflowY: 'auto', pt: 0 }}>
          {scheduled.length > 0 && <ListSubheader sx={{ lineHeight: '32px' }}>{t('closing.assignFromSchedule')}</ListSubheader>}
          {scheduled.map(item)}
          {others.length > 0 && <ListSubheader sx={{ lineHeight: '32px' }}>{t('closing.assignOthers')}</ListSubheader>}
          {others.map(item)}
          {filtered.length === 0 && <Box sx={{ px: '16px', py: '8px', fontSize: 13, color: ds.textMuted }}>{t('closing.assignNone')}</Box>}
        </List>
      </DialogContent>
      <DialogActions sx={{ justifyContent: 'space-between' }}>
        <Button color="inherit" onClick={() => onChoose(null)}>{t('closing.assignClear')}</Button>
        <Button onClick={onCancel}>{t('calendar.cancel')}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default AssignTaskDialog;
