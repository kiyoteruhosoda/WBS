import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Button, TextField, Select, MenuItem, FormControl,
  CircularProgress, Alert, Table, TableBody, TableCell, TableHead, TableRow,
  IconButton, Paper, Tab, Tabs, InputLabel,
} from '@mui/material';
import ReactMarkdown from 'react-markdown';
import { getTask, createTask, updateTask, getTaskDependencies, addDependency, removeDependency } from '../api/tasks';
import { getWorklogs, createWorklog, deleteWorklog } from '../api/worklogs';
import { getCategories } from '../api/categories';
import { getMilestones } from '../api/milestones';
import type { Task, TaskStatus, DependencyType } from '../types';
import { formatDate, priorityBand, priorityBandValue, todayDate } from '../utils/format';
import type { PriorityBand } from '../utils/format';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { PlusIcon, TrashIcon } from '../components/icons';

const STATUSES: TaskStatus[] = ['TODO', 'DOING', 'WAITING', 'DONE', 'CANCELLED'];
const DEP_TYPES: DependencyType[] = ['FS', 'SS', 'FF', 'SF'];
const BANDS: PriorityBand[] = ['high', 'mid', 'low'];

interface FormData {
  title: string;
  category_id: string;
  priority: number;
  urgency: number;
  status: TaskStatus;
  start_date: string;
  due_date: string;
  estimated_hours: string;
  actual_hours: string;
  parent_task_id: string;
  milestone_id: string;
  memo: string;
}

const defaultForm: FormData = {
  title: '', category_id: '', priority: 3, urgency: 3, status: 'TODO',
  start_date: '', due_date: '', estimated_hours: '', actual_hours: '',
  parent_task_id: '', milestone_id: '', memo: '',
};

const toForm = (t: Task): FormData => ({
  title: t.title, category_id: String(t.category_id ?? ''), priority: t.priority,
  urgency: t.urgency, status: t.status, start_date: t.start_date ?? '',
  due_date: t.due_date ?? '', estimated_hours: String(t.estimated_hours ?? ''),
  actual_hours: String(t.actual_hours ?? 0), parent_task_id: String(t.parent_task_id ?? ''),
  milestone_id: String(t.milestone_id ?? ''), memo: t.memo ?? '',
});

// ユーザー設定タイムゾーンでの「今日」を YYYY-MM-DD にする（実績差分の記録日）
const todayYmd = (): string => {
  const d = todayDate();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const FieldLabel: React.FC<{ children: React.ReactNode; required?: boolean }> = ({ children, required }) => {
  const { t } = useI18n();
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px', mb: '6px' }}>
      <Box sx={{ fontSize: 13, fontWeight: 700, color: ds.text }}>{children}</Box>
      {required && (
        <Box sx={{
          bgcolor: ds.danger, color: '#fff', fontSize: 10, fontWeight: 700,
          px: '6px', py: '1px', borderRadius: '3px', lineHeight: 1.6,
        }}>
          {t('taskEdit.required')}
        </Box>
      )}
    </Box>
  );
};

// 優先度・緊急度のラジオpill（高/中/低）
const PillRadio: React.FC<{ value: PriorityBand; onChange: (v: PriorityBand) => void }> = ({ value, onChange }) => {
  const { t } = useI18n();
  return (
  <Box sx={{ display: 'flex', gap: '10px' }}>
    {BANDS.map((band) => {
      const selected = band === value;
      return (
        <Box
          key={band}
          component="button"
          type="button"
          onClick={() => onChange(band)}
          sx={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
            py: '10px', borderRadius: '8px', cursor: 'pointer', font: 'inherit',
            fontSize: 14, fontWeight: selected ? 700 : 500,
            bgcolor: selected ? ds.primaryPale : ds.paper,
            border: selected ? `1.5px solid ${ds.primary}` : `1px solid ${ds.border}`,
            color: selected ? ds.primary : ds.textSub,
          }}
        >
          <Box sx={{
            width: 14, height: 14, borderRadius: '50%', boxSizing: 'border-box',
            border: selected ? `4px solid ${ds.primary}` : `1.5px solid ${ds.textMuted}`,
            bgcolor: '#fff',
          }} />
          {t(`priority.${band}`)}
        </Box>
      );
    })}
  </Box>
  );
};

const TaskEdit: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const isNew = id === undefined || id === 'new';
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { t } = useI18n();
  const [form, setForm] = useState<FormData>(defaultForm);
  const [tab, setTab] = useState(0);
  const [showTitleError, setShowTitleError] = useState(false);
  const [memoPreview, setMemoPreview] = useState(false);
  const [wlDate, setWlDate] = useState('');
  const [wlHours, setWlHours] = useState('');
  const [wlMemo, setWlMemo] = useState('');
  const [depPredId, setDepPredId] = useState('');
  const [depType, setDepType] = useState<DependencyType>('FS');

  const { data: task, isLoading: taskLoading } = useQuery({
    queryKey: ['task', id], queryFn: () => getTask(Number(id)), enabled: !isNew,
  });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  const { data: milestones } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });
  const { data: worklogs } = useQuery({
    queryKey: ['worklogs', id], queryFn: () => getWorklogs(Number(id)), enabled: !isNew,
  });
  const { data: deps } = useQuery({
    queryKey: ['deps', id], queryFn: () => getTaskDependencies(Number(id)), enabled: !isNew,
  });

  useEffect(() => { if (task) setForm(toForm(task)); }, [task]);

  const save = useMutation({
    mutationFn: async (data: Partial<Task>) => {
      const saved = isNew ? await createTask(data) : await updateTask(Number(id), data);
      // 実績時間の変更分を作業ログとして記録する（残り時間は見積−実績で自動計算される）
      if (!isNew && task) {
        const newActual = form.actual_hours === '' ? task.actual_hours : Number(form.actual_hours);
        const delta = Math.round((newActual - task.actual_hours) * 100) / 100;
        if (delta !== 0) {
          await createWorklog({ task_id: Number(id), work_date: todayYmd(), hours: delta, memo: null });
        }
      }
      return saved;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['dashboard-today'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      qc.invalidateQueries({ queryKey: ['worklogs', id] });
      navigate('/tasks');
    },
  });

  const addWl = useMutation({
    mutationFn: () => createWorklog({ task_id: Number(id), work_date: wlDate, hours: Number(wlHours), memo: wlMemo || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['worklogs', id] }); setWlDate(''); setWlHours(''); setWlMemo(''); },
  });

  const delWl = useMutation({
    mutationFn: (wlId: number) => deleteWorklog(wlId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['worklogs', id] }),
  });

  const addDep = useMutation({
    mutationFn: () => addDependency(Number(id), { predecessor_task_id: Number(depPredId), dependency_type: depType }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['deps', id] }); setDepPredId(''); },
  });

  const delDep = useMutation({
    mutationFn: (predId: number) => removeDependency(Number(id), predId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['deps', id] }),
  });

  const handleSubmit = () => {
    if (!form.title.trim()) {
      setShowTitleError(true);
      return;
    }
    save.mutate({
      title: form.title, category_id: form.category_id ? Number(form.category_id) : null,
      priority: form.priority, urgency: form.urgency, status: form.status,
      start_date: form.start_date || null, due_date: form.due_date || null,
      estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
      parent_task_id: form.parent_task_id ? Number(form.parent_task_id) : null,
      milestone_id: form.milestone_id ? Number(form.milestone_id) : null,
      memo: form.memo || null,
    });
  };

  if (!isNew && taskLoading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  }

  const titleError = showTitleError && !form.title.trim();

  // 残り時間は入力せず「見積 − 実績」で表示する
  const estNum = Number(form.estimated_hours);
  const actNum = form.actual_hours === '' ? 0 : Number(form.actual_hours);
  const remainingDisplay =
    form.estimated_hours === '' || isNaN(estNum)
      ? '—'
      : String(Math.max(Math.round((estNum - (isNaN(actNum) ? 0 : actNum)) * 100) / 100, 0));

  return (
    <Box sx={{ maxWidth: 640, mx: 'auto' }}>
      {!isNew && (
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: '14px', minHeight: 40 }}>
          <Tab label={t('taskEdit.tabBasic')} sx={{ minHeight: 40 }} />
          <Tab label={t('taskEdit.tabWorklog')} sx={{ minHeight: 40 }} />
          <Tab label={t('taskEdit.tabDependencies')} sx={{ minHeight: 40 }} />
        </Tabs>
      )}
      {save.isError && <Alert severity="error" sx={{ mb: '14px' }}>{t('taskEdit.saveError')}</Alert>}

      {tab === 0 && (
        <Box sx={{
          bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px',
          p: { xs: '18px', sm: '26px 28px' },
          display: 'flex', flexDirection: 'column', gap: '18px',
        }}>
          <Box>
            <FieldLabel required>{t('taskEdit.taskName')}</FieldLabel>
            <TextField
              fullWidth size="small" placeholder={t('taskEdit.taskNamePlaceholder')}
              value={form.title}
              error={titleError}
              helperText={titleError ? t('taskEdit.taskNameRequired') : undefined}
              onChange={e => setForm({ ...form, title: e.target.value })}
            />
          </Box>

          <Box>
            <FieldLabel>{t('taskEdit.memoLabel')}</FieldLabel>
            {memoPreview ? (
              <Paper variant="outlined" sx={{ p: '12px', minHeight: 96, fontSize: 14 }}>
                <ReactMarkdown>{form.memo}</ReactMarkdown>
              </Paper>
            ) : (
              <TextField
                fullWidth multiline rows={4} placeholder={t('taskEdit.memoPlaceholder')}
                value={form.memo}
                onChange={e => setForm({ ...form, memo: e.target.value })}
              />
            )}
            <Button size="small" onClick={() => setMemoPreview(!memoPreview)} sx={{ mt: '4px', px: '8px', py: '2px' }}>
              {memoPreview ? t('taskEdit.backToEdit') : t('taskEdit.preview')}
            </Button>
          </Box>

          <Box sx={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            <Box sx={{ flex: '1 1 200px' }}>
              <FieldLabel>{t('taskEdit.category')}</FieldLabel>
              <Select
                fullWidth size="small" displayEmpty
                value={form.category_id}
                onChange={e => setForm({ ...form, category_id: String(e.target.value) })}
              >
                <MenuItem value="">{t('taskEdit.none')}</MenuItem>
                {categories?.map(c => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
              </Select>
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <FieldLabel>{t('taskEdit.status')}</FieldLabel>
              <Select
                fullWidth size="small"
                value={form.status}
                onChange={e => setForm({ ...form, status: e.target.value as TaskStatus })}
              >
                {STATUSES.map(s => <MenuItem key={s} value={s}>{t(`status.${s}`)}</MenuItem>)}
              </Select>
            </Box>
          </Box>

          <Box>
            <FieldLabel>{t('taskEdit.priority')}</FieldLabel>
            <PillRadio
              value={priorityBand(form.priority)}
              onChange={(band) => setForm({ ...form, priority: priorityBandValue[band] })}
            />
          </Box>

          <Box>
            <FieldLabel>{t('taskEdit.urgency')}</FieldLabel>
            <PillRadio
              value={priorityBand(form.urgency)}
              onChange={(band) => setForm({ ...form, urgency: priorityBandValue[band] })}
            />
          </Box>

          <Box sx={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            <Box sx={{ flex: '1 1 200px' }}>
              <FieldLabel>{t('taskEdit.startDate')}</FieldLabel>
              <TextField
                fullWidth size="small" type="date"
                value={form.start_date}
                onChange={e => setForm({ ...form, start_date: e.target.value })}
              />
            </Box>
            <Box sx={{ flex: '1 1 200px' }}>
              <FieldLabel>{t('taskEdit.dueDate')}</FieldLabel>
              <TextField
                fullWidth size="small" type="date"
                value={form.due_date}
                onChange={e => setForm({ ...form, due_date: e.target.value })}
              />
            </Box>
          </Box>

          <Box sx={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            <Box sx={{ flex: '1 1 160px' }}>
              <FieldLabel>{t('taskEdit.estimatedHours')}</FieldLabel>
              <TextField
                fullWidth size="small" type="number"
                slotProps={{ htmlInput: { min: 0, step: 0.5 } }}
                value={form.estimated_hours}
                onChange={e => setForm({ ...form, estimated_hours: e.target.value })}
              />
            </Box>
            {!isNew && (
              <>
                <Box sx={{ flex: '1 1 160px' }}>
                  <FieldLabel>{t('taskEdit.actualHours')}</FieldLabel>
                  <TextField
                    fullWidth size="small" type="number"
                    slotProps={{ htmlInput: { min: 0, step: 0.5 } }}
                    value={form.actual_hours}
                    helperText={t('taskEdit.actualHoursHelp')}
                    onChange={e => setForm({ ...form, actual_hours: e.target.value })}
                  />
                </Box>
                <Box sx={{ flex: '1 1 160px' }}>
                  <FieldLabel>{t('taskEdit.remainingHours')}</FieldLabel>
                  <TextField
                    fullWidth size="small" disabled
                    value={remainingDisplay}
                    helperText={t('taskEdit.remainingAuto')}
                  />
                </Box>
              </>
            )}
          </Box>

          <Box>
            <FieldLabel>{t('taskEdit.milestone')}</FieldLabel>
            <Select
              fullWidth size="small" displayEmpty
              value={form.milestone_id}
              onChange={e => setForm({ ...form, milestone_id: String(e.target.value) })}
            >
              <MenuItem value="">{t('taskEdit.none')}</MenuItem>
              {milestones?.map(m => <MenuItem key={m.id} value={String(m.id)}>{m.name}</MenuItem>)}
            </Select>
          </Box>

          <Box sx={{
            display: 'flex', justifyContent: 'flex-end', gap: '12px',
            pt: '14px', borderTop: `1px solid ${ds.borderPale}`,
          }}>
            <Button
              onClick={() => navigate(-1)}
              sx={{
                bgcolor: ds.paper, border: `1px solid ${ds.borderInput}`, color: '#414141',
                px: '24px', '&:hover': { bgcolor: ds.hairline, border: `1px solid ${ds.borderInput}` },
              }}
            >
              {t('taskEdit.cancel')}
            </Button>
            <Button variant="contained" onClick={handleSubmit} disabled={save.isPending} sx={{ px: '28px' }}>
              {t('taskEdit.save')}
            </Button>
          </Box>
        </Box>
      )}

      {tab === 1 && !isNew && (
        <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', p: '18px' }}>
          <Box sx={{ fontSize: 15, fontWeight: 700, color: ds.text, mb: '12px' }}>{t('taskEdit.tabWorklog')}</Box>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('taskEdit.date')}</TableCell>
                <TableCell>{t('taskEdit.hoursUnit')}</TableCell>
                <TableCell>{t('taskEdit.memo')}</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {worklogs?.map(wl => (
                <TableRow key={wl.id}>
                  <TableCell>{formatDate(wl.work_date)}</TableCell>
                  <TableCell>{wl.hours}</TableCell>
                  <TableCell>{wl.memo ?? '—'}</TableCell>
                  <TableCell align="right">
                    <IconButton size="small" onClick={() => delWl.mutate(wl.id)} sx={{ color: ds.textMuted }}>
                      <TrashIcon size={16} />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
              {(worklogs?.length ?? 0) === 0 && (
                <TableRow>
                  <TableCell colSpan={4} sx={{ textAlign: 'center', color: ds.textMuted, py: '20px' }}>
                    {t('taskEdit.noWorklogs')}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <Box sx={{ display: 'flex', gap: '10px', mt: '16px', flexWrap: 'wrap' }}>
            <TextField size="small" type="date" label={t('taskEdit.date')} slotProps={{ inputLabel: { shrink: true } }} value={wlDate} onChange={e => setWlDate(e.target.value)} />
            <TextField size="small" type="number" label={t('taskEdit.hours')} sx={{ width: 100 }} value={wlHours} onChange={e => setWlHours(e.target.value)} />
            <TextField size="small" label={t('taskEdit.memo')} value={wlMemo} onChange={e => setWlMemo(e.target.value)} sx={{ flex: 1, minWidth: 160 }} />
            <Button variant="outlined" startIcon={<PlusIcon size={14} />} onClick={() => addWl.mutate()} disabled={!wlDate || !wlHours}>
              {t('taskEdit.add')}
            </Button>
          </Box>
        </Box>
      )}

      {tab === 2 && !isNew && (
        <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', p: '18px' }}>
          <Box sx={{ fontSize: 15, fontWeight: 700, color: ds.text, mb: '12px' }}>{t('taskEdit.tabDependencies')}</Box>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('taskEdit.predecessorId')}</TableCell>
                <TableCell>{t('taskEdit.depType')}</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {deps?.map(dep => (
                <TableRow key={dep.predecessor_task_id}>
                  <TableCell>{dep.predecessor_task_id}</TableCell>
                  <TableCell>{dep.dependency_type}</TableCell>
                  <TableCell align="right">
                    <IconButton size="small" onClick={() => delDep.mutate(dep.predecessor_task_id)} sx={{ color: ds.textMuted }}>
                      <TrashIcon size={16} />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
              {(deps?.length ?? 0) === 0 && (
                <TableRow>
                  <TableCell colSpan={3} sx={{ textAlign: 'center', color: ds.textMuted, py: '20px' }}>
                    {t('taskEdit.noDeps')}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <Box sx={{ display: 'flex', gap: '10px', mt: '16px' }}>
            <TextField size="small" type="number" label={t('taskEdit.predecessorId')} sx={{ width: 140 }} value={depPredId} onChange={e => setDepPredId(e.target.value)} />
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <InputLabel>{t('taskEdit.type')}</InputLabel>
              <Select value={depType} label={t('taskEdit.type')} onChange={e => setDepType(e.target.value as DependencyType)}>
                {DEP_TYPES.map(dt => <MenuItem key={dt} value={dt}>{dt}</MenuItem>)}
              </Select>
            </FormControl>
            <Button variant="outlined" startIcon={<PlusIcon size={14} />} onClick={() => addDep.mutate()} disabled={!depPredId}>
              {t('taskEdit.add')}
            </Button>
          </Box>
        </Box>
      )}
    </Box>
  );
};

export default TaskEdit;
