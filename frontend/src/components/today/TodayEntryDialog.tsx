import React, { useState } from 'react';
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Stack, TextField,
  useMediaQuery, useTheme,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import { useI18n } from '../../i18n';
import type { Task, TimeEntry } from '../../types';
import type { EntryForm } from '../../today/entryForm';
import { parseTimeOfDay, problemOf, stepInstant, timeFieldOf, withTimeOfDay } from '../../today/entryForm';
import { useTimeInputStyle } from '../../preferences/timeInputStyle';
import { useProjectScope } from '../../projects/useProjectScope';
import TaskPickerField from '../TaskPickerField';
import { formatClockDuration } from '../../utils/format';
import { ds } from '../../theme';

interface Props {
  /** 直す打刻（null は足す） */
  entry: TimeEntry | null;
  initial: EntryForm;
  today: string;
  timeZone: string;
  nowMs: number;
  tasks: readonly Task[];
  /** 1 押しで選べるタスク（今日の打刻に出てきた順） */
  quickTasks: readonly { id: number; title: string }[];
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onSave: (form: EntryForm) => void;
  onDelete: () => void;
}

const timeInputStyle = { fontSize: 20, textAlign: 'center', padding: '10px 8px' } as const;

/**
 * 24 時間の時刻の欄（ADR-0039）。数字のキーボードで `930` と打てば 09:30。確定は欄を離れたときか Enter
 * （読めなければ元へ戻す）。端末の時刻の欄は言語・時計の設定で午前／午後になるので、既定はこちら。
 */
const TwentyFourHourField: React.FC<{
  label: string;
  value: string;
  disabled?: boolean;
  onCommit: (value: string) => void;
}> = ({ label, value, disabled, onCommit }) => {
  // 打っている途中だけ持つ（null の間は value をそのまま見せる。± で変わった値も追える）
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    if (draft == null) return;
    const parsed = parseTimeOfDay(draft);
    if (parsed != null && parsed !== value) onCommit(parsed);
    setDraft(null);
  };
  return (
    <TextField
      value={draft ?? value} disabled={disabled} placeholder="HH:MM"
      onFocus={(e) => e.target.select()}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }}
      error={draft != null && draft.trim() !== '' && parseTimeOfDay(draft) == null}
      slotProps={{ htmlInput: { 'aria-label': label, inputMode: 'numeric', maxLength: 5, autoComplete: 'off', style: timeInputStyle } }}
      sx={{ flex: 1, minWidth: 0 }}
    />
  );
};

/** 時刻の 1 行: [−] HH:MM [+]（日をまたいだ時刻には日付を添える）。 */
const TimeRow: React.FC<{
  label: string;
  instantMs: number;
  today: string;
  timeZone: string;
  disabled?: boolean;
  trailing?: React.ReactNode;
  onChange: (instantMs: number) => void;
}> = ({ label, instantMs, today, timeZone, disabled, trailing, onChange }) => {
  const { t } = useI18n();
  const { style } = useTimeInputStyle();
  const field = timeFieldOf(instantMs, timeZone);
  const setTime = (value: string) => {
    const next = withTimeOfDay(instantMs, value, timeZone);
    if (next != null) onChange(next);
  };
  const stepButton = { width: 48, height: 48, border: `1px solid ${ds.border}`, borderRadius: '10px', flexShrink: 0 } as const;
  return (
    <Box>
      <Box sx={{ fontSize: 12, color: ds.textSub, mb: '4px' }}>
        {label}
        {field.date !== today && (
          <Box component="span" sx={{ ml: '6px', color: ds.textMuted }}>
            {t('today.entry.otherDay', { date: field.date.slice(5).replace('-', '/') })}
          </Box>
        )}
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <IconButton
          aria-label={t('today.entry.earlier', { label })} disabled={disabled} sx={stepButton}
          onClick={() => onChange(stepInstant(instantMs, -1, timeZone))}
        >
          <RemoveIcon />
        </IconButton>
        {style === '24h' ? (
          <TwentyFourHourField label={label} value={field.value} disabled={disabled} onCommit={setTime} />
        ) : (
          <TextField
            type="time" value={field.value} disabled={disabled}
            onChange={(e) => setTime(e.target.value)}
            slotProps={{ htmlInput: { 'aria-label': label, step: 60, style: timeInputStyle } }}
            sx={{ flex: 1, minWidth: 0 }}
          />
        )}
        <IconButton
          aria-label={t('today.entry.later', { label })} disabled={disabled} sx={stepButton}
          onClick={() => onChange(stepInstant(instantMs, 1, timeZone))}
        >
          <AddIcon />
        </IconButton>
        {trailing}
      </Box>
    </Box>
  );
};

/**
 * 「今日」の画面から打刻を 1 本足す・直す（task #287、ADR-0038）。スマホでは全画面で、片手で直せるように
 * タスクは 1 押しの候補、時刻は時刻だけの欄と 15 分の ± にしてある。計測中の打刻は終わりを決めない（止めるのは打刻のボタン）。
 */
const TodayEntryDialog: React.FC<Props> = ({
  entry, initial, today, timeZone, nowMs, tasks, quickTasks, busy, error, onCancel, onSave, onDelete,
}) => {
  const { t } = useI18n();
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down('sm'));
  const { scope, projects } = useProjectScope();
  const [form, setForm] = useState<EntryForm>(initial);
  // 消すのは 2 度押し（揺れる電車で押し違えても消えない）
  const [confirmDelete, setConfirmDelete] = useState(false);
  const running = form.endMs == null;
  const problem = problemOf(form, nowMs);
  const seconds = Math.max(0, Math.floor(((form.endMs ?? nowMs) - form.startMs) / 1000));

  return (
    <Dialog open onClose={onCancel} maxWidth="xs" fullWidth fullScreen={narrow} data-testid="today-entry-dialog">
      <DialogTitle sx={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '8px' }}>
        {t(entry ? 'today.entry.editTitle' : 'today.entry.addTitle')}
        <Box component="span" sx={{ fontSize: 16, fontVariantNumeric: 'tabular-nums', color: ds.textSub }}>
          {formatClockDuration(seconds)}
        </Box>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Box>
            <TaskPickerField
              label={t('today.entry.task')} tasks={tasks} projects={projects} scope={scope}
              value={form.taskId} onChange={(taskId) => setForm({ ...form, taskId })}
            />
            {quickTasks.length > 0 && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '6px', mt: '8px' }}>
                {quickTasks.map((task) => (
                  <Chip
                    key={task.id} label={task.title} clickable
                    color={form.taskId === task.id ? 'primary' : 'default'}
                    variant={form.taskId === task.id ? 'filled' : 'outlined'}
                    onClick={() => setForm({ ...form, taskId: task.id })}
                    sx={{ maxWidth: '100%', height: 36 }}
                  />
                ))}
              </Box>
            )}
          </Box>
          <TimeRow
            label={t('today.entry.start')} instantMs={form.startMs} today={today} timeZone={timeZone}
            onChange={(startMs) => setForm({ ...form, startMs })}
          />
          {running ? (
            <Alert severity="info">{t('today.entry.running')}</Alert>
          ) : (
            <TimeRow
              label={t('today.entry.end')} instantMs={form.endMs as number} today={today} timeZone={timeZone}
              onChange={(endMs) => setForm({ ...form, endMs })}
              trailing={(
                <Button
                  variant="outlined" onClick={() => setForm({ ...form, endMs: Math.floor(nowMs / 60_000) * 60_000 })}
                  sx={{ minWidth: 0, height: 48, px: '10px', flexShrink: 0 }}
                >
                  {t('today.entry.now')}
                </Button>
              )}
            />
          )}
          {problem && <Alert severity="warning">{t(problem === 'future' ? 'closing.error.future' : 'closing.editInvalid')}</Alert>}
          <TextField
            label={t('closing.editMemo')} value={form.memo} onChange={(e) => setForm({ ...form, memo: e.target.value })}
            multiline minRows={1} slotProps={{ htmlInput: { maxLength: 2000 } }}
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ justifyContent: 'space-between', px: '24px', pb: '16px' }}>
        {entry ? (
          <Button
            color="error" variant={confirmDelete ? 'contained' : 'text'} disabled={busy}
            onClick={() => (confirmDelete ? onDelete() : setConfirmDelete(true))}
          >
            {t(confirmDelete ? 'today.entry.deleteConfirm' : 'closing.delete')}
          </Button>
        ) : <span />}
        <span>
          <Button onClick={onCancel}>{t('calendar.cancel')}</Button>
          <Button variant="contained" disabled={busy || problem != null} onClick={() => onSave(form)} sx={{ ml: '8px', minHeight: 44 }}>
            {t('closing.save')}
          </Button>
        </span>
      </DialogActions>
    </Dialog>
  );
};

export default TodayEntryDialog;
