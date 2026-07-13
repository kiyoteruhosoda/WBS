import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Box, Button, CircularProgress, Alert, Typography, Table, TableBody,
  TableCell, TableHead, TableRow, TableSortLabel, Select, MenuItem,
  FormControl, InputLabel, TablePagination, Paper, TableContainer, Chip,
  OutlinedInput,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { getTasks } from '../api/tasks';
import { getCategories } from '../api/categories';
import { getMilestones } from '../api/milestones';
import { formatDate, statusLabel } from '../utils/format';
import type { TaskStatus } from '../types';
import StatusChip from '../components/StatusChip';

const STATUSES: TaskStatus[] = ['TODO', 'DOING', 'WAITING', 'DONE', 'CANCELLED'];

const TaskList: React.FC = () => {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<TaskStatus[]>([]);
  const [categoryId, setCategoryId] = useState<string>('');
  const [milestoneId, setMilestoneId] = useState<string>('');
  const [sort, setSort] = useState('priority_score');
  const [page, setPage] = useState(0);
  const [perPage] = useState(50);

  const { data, isLoading, error } = useQuery({
    queryKey: ['tasks', statusFilter, categoryId, milestoneId, sort, page, perPage],
    queryFn: () => getTasks({
      status: statusFilter.join(',') || undefined,
      category_id: categoryId ? Number(categoryId) : undefined,
      milestone_id: milestoneId ? Number(milestoneId) : undefined,
      sort,
      page: page + 1,
      per_page: perPage,
    }),
  });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  const { data: milestones } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });

  const handleSort = (col: string) => setSort(sort === col ? `-${col}` : col);

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5">タスク一覧</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/tasks/new')}>新規タスク</Button>
      </Box>
      <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>ステータス</InputLabel>
          <Select multiple value={statusFilter as unknown as string[]}
            onChange={(e) => setStatusFilter(e.target.value as unknown as TaskStatus[])}
            input={<OutlinedInput label="ステータス" />}
            renderValue={(sel) => (sel as unknown as TaskStatus[]).map(s => statusLabel[s]).join(', ')}>
            {STATUSES.map(s => <MenuItem key={s} value={s}>{statusLabel[s]}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>カテゴリ</InputLabel>
          <Select value={categoryId} label="カテゴリ" onChange={e => setCategoryId(e.target.value)}>
            <MenuItem value="">すべて</MenuItem>
            {categories?.map(c => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>マイルストーン</InputLabel>
          <Select value={milestoneId} label="マイルストーン" onChange={e => setMilestoneId(e.target.value)}>
            <MenuItem value="">すべて</MenuItem>
            {milestones?.map(m => <MenuItem key={m.id} value={String(m.id)}>{m.name}</MenuItem>)}
          </Select>
        </FormControl>
      </Box>
      {isLoading && <CircularProgress />}
      {error && <Alert severity="error">読み込みエラー</Alert>}
      {data && (
        <Paper>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell><TableSortLabel active={sort.replace('-','') === 'title'} onClick={() => handleSort('title')}>タイトル</TableSortLabel></TableCell>
                  <TableCell>カテゴリ</TableCell>
                  <TableCell><TableSortLabel active={sort.replace('-','') === 'due_date'} onClick={() => handleSort('due_date')}>期日</TableSortLabel></TableCell>
                  <TableCell>進捗</TableCell>
                  <TableCell>ステータス</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.items.map(task => {
                  const cat = categories?.find(c => c.id === task.category_id);
                  return (
                    <TableRow key={task.id} hover sx={{ cursor: 'pointer' }} onClick={() => navigate(`/tasks/${task.id}`)}>
                      <TableCell>{task.title}</TableCell>
                      <TableCell>{cat ? <Chip label={cat.name} size="small" sx={{ bgcolor: cat.color ?? undefined }} /> : '—'}</TableCell>
                      <TableCell>{formatDate(task.due_date)}</TableCell>
                      <TableCell>{task.progress_percent}%</TableCell>
                      <TableCell><StatusChip status={task.status} /></TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={data.total}
            page={page}
            onPageChange={(_, p) => setPage(p)}
            rowsPerPage={perPage}
            rowsPerPageOptions={[50]}
            labelRowsPerPage="表示件数"
          />
        </Paper>
      )}
    </Box>
  );
};

export default TaskList;
