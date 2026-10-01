import React, { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField } from '@mui/material';
import { useI18n } from '../../i18n';
import type { TimeEntry } from '../../types';
import type { EntryRange } from '../../closing/closingRequests';
import { entryEndMs, entryStartMs } from '../../closing/closingBoard';
import { fromLocalInputValue, toLocalInputValue } from '../../closing/entryGestures';

interface Props {
  entry: TimeEntry;
  timeZone: string;
  nowMs: number;
  onCancel: () => void;
  onSave: (range: EntryRange, memo: string | null) => void;
  onDelete: () => void;
}

/**
 * 打刻 1 本を分単位で直す（ドラッグで合わせにくいとき）。触らなかった時刻は秒まで元のまま送る。
 * 走っている打刻は終わりを決められない（止めるのは上部の打刻ボタン）。
 */
const EntryEditDialog: React.FC<Props> = ({ entry, timeZone, nowMs, onCancel, onSave, onDelete }) => {
  const { t } = useI18n();
  const original = { startMs: entryStartMs(entry), endMs: entryEndMs(entry, nowMs) };
  const initialStart = toLocalInputValue(original.startMs, timeZone);
  const initialEnd = toLocalInputValue(original.endMs, timeZone);
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(initialEnd);
  const [memo, setMemo] = useState(entry.memo ?? '');

  const startMs = start === initialStart ? original.startMs : fromLocalInputValue(start, timeZone);
  const endMs = end === initialEnd ? original.endMs : fromLocalInputValue(end, timeZone);
  const invalid = startMs == null || endMs == null || endMs <= startMs;

  return (
    <Dialog open onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>{t('closing.editTitle')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {entry.is_running && <Alert severity="info">{t('closing.editRunning')}</Alert>}
          <TextField
            label={t('closing.editStart')} type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)}
            disabled={entry.is_running} slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label={t('closing.editEnd')} type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)}
            disabled={entry.is_running} slotProps={{ inputLabel: { shrink: true } }}
            error={!entry.is_running && invalid} helperText={!entry.is_running && invalid ? t('closing.editInvalid') : t('closing.editTimeZone', { zone: timeZone })}
          />
          <TextField
            label={t('closing.editMemo')} value={memo} onChange={(e) => setMemo(e.target.value)} multiline minRows={2}
            slotProps={{ htmlInput: { maxLength: 2000 } }}
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ justifyContent: 'space-between' }}>
        <Button color="error" onClick={onDelete}>{t('closing.delete')}</Button>
        <span>
          <Button onClick={onCancel}>{t('calendar.cancel')}</Button>
          <Button
            variant="contained"
            disabled={entry.is_running || invalid}
            onClick={() => startMs != null && endMs != null && onSave({ startMs, endMs }, memo.trim() ? memo : null)}
          >
            {t('closing.save')}
          </Button>
        </span>
      </DialogActions>
    </Dialog>
  );
};

export default EntryEditDialog;
