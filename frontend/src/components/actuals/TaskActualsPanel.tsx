// タスクごとの見積・予定済み・実績・残と、残を見直す促し（task #162、ADR-0017）。
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Alert, Box, Button, Checkbox, CircularProgress, FormControlLabel, Snackbar, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, TextField,
} from '@mui/material';
import { ACTUALS_KEY, getTaskActuals } from '../../api/actuals';
import { patchTask } from '../../api/tasks';
import { formatHours } from '../../calendar/taskScheduling';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';
import type { TaskActualsRow } from '../../types/actuals';
import { WarningTriangleIcon } from '../icons';

interface Props {
  reviewOnly: boolean;
  onReviewOnlyChange: (value: boolean) => void;
}

const RemainingEditor: React.FC<{ row: TaskActualsRow; onSaved: (ok: boolean) => void }> = ({ row, onSaved }) => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [value, setValue] = useState<string>(
    row.task.remaining_hours_entered != null ? String(row.task.remaining_hours_entered) : '',
  );
  const save = useMutation({
    // 空にすると手の値を消して既定（見積 − 実績）へ戻す（ADR-0010）
    mutationFn: () => patchTask(row.task.id, { remaining_hours: value.trim() === '' ? null : Number(value) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ACTUALS_KEY });
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['today'] });
      onSaved(true);
    },
    onError: () => onSaved(false),
  });
  const invalid = value.trim() !== '' && (!Number.isFinite(Number(value)) || Number(value) < 0);
  return (
    <Box
      component="form"
      onSubmit={(e: React.FormEvent) => { e.preventDefault(); if (!invalid) save.mutate(); }}
      sx={{ display: 'flex', gap: '6px', alignItems: 'center' }}
    >
      <TextField
        size="small"
        type="number"
        value={value}
        error={invalid}
        onChange={(e) => setValue(e.target.value)}
        // 空の箱だけだと何を入れる欄か分からないので、見える名前（残（h））を付ける。空で保存すると既定へ戻る
        label={t('actuals.remainingInput')}
        slotProps={{ htmlInput: { min: 0, step: 0.25 } }}
        sx={{ width: 90 }}
      />
      <Button type="submit" size="small" variant="outlined" disabled={invalid || save.isPending}>
        {t('actuals.remainingSave')}
      </Button>
    </Box>
  );
};

const TaskActualsPanel: React.FC<Props> = ({ reviewOnly, onReviewOnlyChange }) => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [notice, setNotice] = useState<{ ok: boolean } | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: [...ACTUALS_KEY, 'tasks', reviewOnly],
    queryFn: () => getTaskActuals(reviewOnly),
  });

  const latest = data?.latest_closed_period;
  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap', mb: '10px' }}>
        <FormControlLabel
          control={<Checkbox checked={reviewOnly} onChange={(e) => onReviewOnlyChange(e.target.checked)} />}
          label={t('actuals.reviewOnly')}
        />
        <Box sx={{ fontSize: 13, color: ds.textSub }}>
          {latest ? t('actuals.latestClosed', { from: latest.first_day, to: latest.last_day }) : t('actuals.noClosed')}
        </Box>
      </Box>
      {reviewOnly && <Alert severity="info" sx={{ mb: '12px' }}>{t('actuals.reviewIntro')}</Alert>}

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress /></Box>}
      {error && <Alert severity="error">{t('common.loadError')}</Alert>}
      {data && data.rows.length === 0 && (
        <Box sx={{ p: '32px', textAlign: 'center', fontSize: 13, color: ds.textMuted }}>
          {reviewOnly ? t('actuals.reviewEmpty') : t('actuals.tasksEmpty')}
        </Box>
      )}
      {data && data.rows.length > 0 && (
        <TableContainer sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px' }}>
          <Table size="small">
            <TableHead>
              {/* 見出しは折り返さない（狭い画面で「予定済み」が 1 文字ずつ縦に並び、行が 3 倍の高さになる） */}
              <TableRow sx={{ '& th': { whiteSpace: 'nowrap' } }}>
                <TableCell>{t('actuals.colTask')}</TableCell>
                <TableCell align="right">{t('actuals.colEstimate')}</TableCell>
                <TableCell align="right" title={t('actuals.scheduledHelp')}>{t('actuals.colScheduled')}</TableCell>
                <TableCell align="right">{t('actuals.colActual')}</TableCell>
                <TableCell align="right">{t('actuals.colRemaining')}</TableCell>
                <TableCell align="right">{t('actuals.colProgress')}</TableCell>
                <TableCell align="right">{t('actuals.colLatestClosed')}</TableCell>
                <TableCell>{t('actuals.colActualSpan')}</TableCell>
                <TableCell>{t('actuals.colReview')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.rows.map((row) => {
                const task = row.task;
                // 子を持つタスクは子の積み上げ（ADR-0010）。残を入れさせない
                const actual = task.has_subtasks ? task.rollup_actual_hours : task.actual_hours;
                const remaining = task.has_subtasks ? task.rollup_remaining_hours : task.remaining_hours;
                return (
                  <TableRow key={task.id} hover sx={row.review_reasons.length > 0 ? { bgcolor: ds.warnPale } : undefined}>
                    <TableCell
                      onClick={() => navigate(`/tasks/${task.id}`)}
                      sx={{ cursor: 'pointer', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', '&:hover': { color: ds.primary } }}
                    >
                      {task.title}
                    </TableCell>
                    <TableCell align="right">{formatHours(task.estimated_hours)}</TableCell>
                    <TableCell align="right">{formatHours(task.scheduled_hours)}</TableCell>
                    <TableCell align="right">{formatHours(actual)}</TableCell>
                    <TableCell align="right">{formatHours(remaining)}</TableCell>
                    <TableCell align="right">{task.progress_percent === null ? '—' : `${task.progress_percent}%`}</TableCell>
                    <TableCell align="right">{row.latest_closed_hours > 0 ? formatHours(row.latest_closed_hours) : '—'}</TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap', color: ds.textSub }}>
                      {row.actual_first_date ? `${row.actual_first_date}〜${row.actual_last_date}` : '—'}
                    </TableCell>
                    <TableCell>
                      {row.review_reasons.length > 0 && (
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          {row.review_reasons.map((r) => (
                            <Box key={r} sx={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 12, color: ds.warnText }}>
                              <WarningTriangleIcon size={14} />
                              {t(`actuals.reason.${r}`)}
                            </Box>
                          ))}
                          <RemainingEditor row={row} onSaved={(ok) => setNotice({ ok })} />
                        </Box>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <Snackbar
        open={notice !== null}
        autoHideDuration={3000}
        onClose={() => setNotice(null)}
        message={notice?.ok ? t('actuals.remainingSaved') : t('actuals.remainingSaveError')}
      />
    </Box>
  );
};

export default TaskActualsPanel;
