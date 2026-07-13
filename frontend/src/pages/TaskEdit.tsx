import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Button, TextField, Select, MenuItem, FormControl, InputLabel,
  Typography, CircularProgress, Alert, Grid, Slider,
  Table, TableBody, TableCell, TableHead, TableRow, IconButton,
  Paper, Tab, Tabs,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import ReactMarkdown from 'react-markdown';
import { getTask, createTask, updateTask, getTaskDependencies, addDependency, removeDependency } from '../api/tasks';
import { getWorklogs, createWorklog, deleteWorklog } from '../api/worklogs';
import { getCategories } from '../api/categories';
import { getMilestones } from '../api/milestones';
import type { Task, TaskStatus, DependencyType } from '../types';
import { formatDate } from '../utils/format';

const STATUSES: TaskStatus[] = ['TODO', 'DOING', 'WAITING', 'DONE', 'CANCELLED'];
const STATUS_LABELS: Record<TaskStatus, string> = { TODO: '未着手', DOING: '進行中', WAITING: '待機中', DONE: '完了', CANCELLED: 'キャンセル' };
const DEP_TYPES: DependencyType[] = ['FS', 'SS', 'FF', 'SF'];

interface FormData {
  title: string;
  category_id: string;
  priority: number;
  urgency: number;
  status: TaskStatus;
  start_date: string;
  due_date: string;
  estimated_hours: string;
  remaining_hours: string;
  parent_task_id: string;
  milestone_id: string;
  memo: string;
}

const defaultForm: FormData = {
  title: '', category_id: '', priority: 3, urgency: 3, status: 'TODO',
  start_date: '', due_date: '', estimated_hours: '', remaining_hours: '',
  parent_task_id: '', milestone_id: '', memo: '',
};

const toForm = (t: Task): FormData => ({
  title: t.title, category_id: String(t.category_id ?? ''), priority: t.priority,
  urgency: t.urgency, status: t.status, start_date: t.start_date ?? '',
  due_date: t.due_date ?? '', estimated_hours: String(t.estimated_hours ?? ''),
  remaining_hours: String(t.remaining_hours ?? ''), parent_task_id: String(t.parent_task_id ?? ''),
  milestone_id: String(t.milestone_id ?? ''), memo: t.memo ?? '',
});

const TaskEdit: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const isNew = id === 'new';
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form, setForm] = useState<FormData>(defaultForm);
  const [tab, setTab] = useState(0);
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
    mutationFn: (data: Partial<Task>) => isNew ? createTask(data) : updateTask(Number(id), data),
    onSuccess: (t) => { qc.invalidateQueries({ queryKey: ['tasks'] }); navigate(`/tasks/${t.id}`); },
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
    mutationFn: () => addDependency(Number(id), { predecessor_id: Number(depPredId), dependency_type: depType }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['deps', id] }); setDepPredId(''); },
  });

  const delDep = useMutation({
    mutationFn: (predId: number) => removeDependency(Number(id), predId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['deps', id] }),
  });

  const handleSubmit = () => {
    save.mutate({
      title: form.title, category_id: form.category_id ? Number(form.category_id) : null,
      priority: form.priority, urgency: form.urgency, status: form.status,
      start_date: form.start_date || null, due_date: form.due_date || null,
      estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
      remaining_hours: form.remaining_hours ? Number(form.remaining_hours) : null,
      parent_task_id: form.parent_task_id ? Number(form.parent_task_id) : null,
      milestone_id: form.milestone_id ? Number(form.milestone_id) : null,
      memo: form.memo || null,
    });
  };

  if (!isNew && taskLoading) return <CircularProgress />;

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>{isNew ? '新規タスク' : 'タスク編集'}</Typography>
      {save.isError && <Alert severity="error" sx={{ mb: 2 }}>保存に失敗しました</Alert>}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="基本情報" />
        {!isNew && <Tab label="作業ログ" />}
        {!isNew && <Tab label="依存関係" />}
      </Tabs>

      {tab === 0 && (
        <Grid container spacing={2}>
          <Grid size={12}>
            <TextField fullWidth label="タイトル *" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <FormControl fullWidth>
              <InputLabel>カテゴリ</InputLabel>
              <Select value={form.category_id} label="カテゴリ" onChange={e => setForm({ ...form, category_id: String(e.target.value) })}>
                <MenuItem value="">なし</MenuItem>
                {categories?.map(c => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <FormControl fullWidth>
              <InputLabel>ステータス</InputLabel>
              <Select value={form.status} label="ステータス" onChange={e => setForm({ ...form, status: e.target.value as TaskStatus })}>
                {STATUSES.map(s => <MenuItem key={s} value={s}>{STATUS_LABELS[s]}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <Typography gutterBottom>優先度: {form.priority}</Typography>
            <Slider value={form.priority} min={1} max={5} step={1} marks onChange={(_, v) => setForm({ ...form, priority: v as number })} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <Typography gutterBottom>緊急度: {form.urgency}</Typography>
            <Slider value={form.urgency} min={1} max={5} step={1} marks onChange={(_, v) => setForm({ ...form, urgency: v as number })} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField fullWidth type="date" label="開始日" slotProps={{ inputLabel: { shrink: true } }} value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField fullWidth type="date" label="期日" slotProps={{ inputLabel: { shrink: true } }} value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField fullWidth type="number" label="見積時間(h)" value={form.estimated_hours} onChange={e => setForm({ ...form, estimated_hours: e.target.value })} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField fullWidth type="number" label="残り時間(h)" value={form.remaining_hours} onChange={e => setForm({ ...form, remaining_hours: e.target.value })} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <FormControl fullWidth>
              <InputLabel>マイルストーン</InputLabel>
              <Select value={form.milestone_id} label="マイルストーン" onChange={e => setForm({ ...form, milestone_id: String(e.target.value) })}>
                <MenuItem value="">なし</MenuItem>
                {milestones?.map(m => <MenuItem key={m.id} value={String(m.id)}>{m.name}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid size={12}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Typography variant="subtitle2">メモ (Markdown)</Typography>
              <Button size="small" onClick={() => setMemoPreview(!memoPreview)}>{memoPreview ? '編集' : 'プレビュー'}</Button>
            </Box>
            {memoPreview
              ? <Paper variant="outlined" sx={{ p: 2, minHeight: 120 }}><ReactMarkdown>{form.memo}</ReactMarkdown></Paper>
              : <TextField fullWidth multiline rows={5} value={form.memo} onChange={e => setForm({ ...form, memo: e.target.value })} />
            }
          </Grid>
          <Grid size={12}>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Button variant="contained" onClick={handleSubmit} disabled={save.isPending || !form.title}>保存</Button>
              <Button onClick={() => navigate(-1)}>キャンセル</Button>
            </Box>
          </Grid>
        </Grid>
      )}

      {tab === 1 && !isNew && (
        <Box>
          <Typography variant="h6" sx={{ mb: 2 }}>作業ログ</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>日付</TableCell>
                <TableCell>時間(h)</TableCell>
                <TableCell>メモ</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {worklogs?.map(wl => (
                <TableRow key={wl.id}>
                  <TableCell>{formatDate(wl.work_date)}</TableCell>
                  <TableCell>{wl.hours}</TableCell>
                  <TableCell>{wl.memo ?? '—'}</TableCell>
                  <TableCell><IconButton size="small" onClick={() => delWl.mutate(wl.id)}><DeleteIcon fontSize="small" /></IconButton></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Box sx={{ display: 'flex', gap: 1, mt: 2, flexWrap: 'wrap' }}>
            <TextField size="small" type="date" label="日付" slotProps={{ inputLabel: { shrink: true } }} value={wlDate} onChange={e => setWlDate(e.target.value)} />
            <TextField size="small" type="number" label="時間" sx={{ width: 100 }} value={wlHours} onChange={e => setWlHours(e.target.value)} />
            <TextField size="small" label="メモ" value={wlMemo} onChange={e => setWlMemo(e.target.value)} />
            <Button variant="outlined" startIcon={<AddIcon />} onClick={() => addWl.mutate()} disabled={!wlDate || !wlHours}>追加</Button>
          </Box>
        </Box>
      )}

      {tab === 2 && !isNew && (
        <Box>
          <Typography variant="h6" sx={{ mb: 2 }}>依存関係</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>先行タスクID</TableCell>
                <TableCell>依存タイプ</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {deps?.map(dep => (
                <TableRow key={dep.predecessor_id}>
                  <TableCell>{dep.predecessor_id}</TableCell>
                  <TableCell>{dep.dependency_type}</TableCell>
                  <TableCell><IconButton size="small" onClick={() => delDep.mutate(dep.predecessor_id)}><DeleteIcon fontSize="small" /></IconButton></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
            <TextField size="small" type="number" label="先行タスクID" sx={{ width: 140 }} value={depPredId} onChange={e => setDepPredId(e.target.value)} />
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <InputLabel>タイプ</InputLabel>
              <Select value={depType} label="タイプ" onChange={e => setDepType(e.target.value as DependencyType)}>
                {DEP_TYPES.map(t => <MenuItem key={t} value={t}>{t}</MenuItem>)}
              </Select>
            </FormControl>
            <Button variant="outlined" startIcon={<AddIcon />} onClick={() => addDep.mutate()} disabled={!depPredId}>追加</Button>
          </Box>
        </Box>
      )}
    </Box>
  );
};

export default TaskEdit;
