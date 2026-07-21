import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Box, CircularProgress, Alert, Table, TableBody, TableCell, TableHead,
  TableRow, TableSortLabel, Select, MenuItem, FormControl, InputLabel,
  TableContainer, OutlinedInput, InputAdornment, TextField,
} from '@mui/material';
import { getTasks } from '../api/tasks';
import { getCategories } from '../api/categories';
import { getMilestones } from '../api/milestones';
import { formatDate, isOverdue, isDueToday } from '../utils/format';
import type { Task, TaskStatus } from '../types';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import StatusChip from '../components/StatusChip';
import PriorityChip from '../components/PriorityChip';
import ProgressBar from '../components/ProgressBar';
import CategoryDot from '../components/CategoryDot';
import { SearchIcon } from '../components/icons';

const STATUSES: TaskStatus[] = ['TODO', 'DOING', 'WAITING', 'DONE', 'CANCELLED'];

type SortKey = 'priority_score' | 'title' | 'due_date';

const compare = (a: Task, b: Task, key: SortKey): number => {
  if (key === 'title') return a.title.localeCompare(b.title, 'ja');
  if (key === 'due_date') {
    if (!a.due_date && !b.due_date) return 0;
    if (!a.due_date) return 1;
    if (!b.due_date) return -1;
    return a.due_date.localeCompare(b.due_date);
  }
  return b.priority_score - a.priority_score;
};

const TaskList: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [statusFilter, setStatusFilter] = useState<TaskStatus[]>([]);
  const [categoryId, setCategoryId] = useState<string>('');
  const [milestoneId, setMilestoneId] = useState<string>('');
  const [keyword, setKeyword] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('priority_score');
  const [sortDesc, setSortDesc] = useState(false);

  const { data, isLoading, error } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  const { data: milestones } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDesc(!sortDesc);
    else { setSortKey(key); setSortDesc(false); }
  };

  const items = useMemo(() => {
    let list = data ?? [];
    if (statusFilter.length > 0) list = list.filter((t) => statusFilter.includes(t.status));
    if (categoryId) list = list.filter((t) => t.category_id === Number(categoryId));
    if (milestoneId) list = list.filter((t) => t.milestone_id === Number(milestoneId));
    if (keyword.trim()) {
      const kw = keyword.trim().toLowerCase();
      list = list.filter((t) => t.title.toLowerCase().includes(kw));
    }
    const sorted = [...list].sort((a, b) => compare(a, b, sortKey));
    return sortDesc ? sorted.reverse() : sorted;
  }, [data, statusFilter, categoryId, milestoneId, keyword, sortKey, sortDesc]);

  return (
    <Box>
      {/* フィルタツールバー */}
      <Box sx={{ display: 'flex', gap: '12px', mb: '14px', flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField
          size="small"
          placeholder={t('taskList.searchPlaceholder')}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          sx={{ minWidth: 220 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon size={16} stroke={ds.textMuted} />
                </InputAdornment>
              ),
            },
          }}
        />
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>{t('taskList.status')}</InputLabel>
          <Select multiple value={statusFilter as unknown as string[]}
            onChange={(e) => setStatusFilter(e.target.value as unknown as TaskStatus[])}
            input={<OutlinedInput label={t('taskList.status')} />}
            renderValue={(sel) => (sel as unknown as TaskStatus[]).map(s => t(`status.${s}`)).join(', ')}>
            {STATUSES.map(s => <MenuItem key={s} value={s}>{t(`status.${s}`)}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>{t('taskList.category')}</InputLabel>
          <Select value={categoryId} label={t('taskList.category')} onChange={e => setCategoryId(e.target.value)}>
            <MenuItem value="">{t('taskList.all')}</MenuItem>
            {categories?.map(c => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>{t('taskList.milestone')}</InputLabel>
          <Select value={milestoneId} label={t('taskList.milestone')} onChange={e => setMilestoneId(e.target.value)}>
            <MenuItem value="">{t('taskList.all')}</MenuItem>
            {milestones?.map(m => <MenuItem key={m.id} value={String(m.id)}>{m.name}</MenuItem>)}
          </Select>
        </FormControl>
        <Box sx={{ fontSize: 13, color: ds.textSub, ml: 'auto' }}>{t('taskList.count', { count: items.length })}</Box>
      </Box>

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>}
      {error && <Alert severity="error">{t('common.loadError')}</Alert>}
      {data && (
        <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', overflow: 'hidden' }}>
          <TableContainer>
            <Table size="small" sx={{ '& td': { py: '10px' } }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ minWidth: 220 }}>
                    <TableSortLabel
                      active={sortKey === 'title'}
                      direction={sortKey === 'title' && sortDesc ? 'desc' : 'asc'}
                      onClick={() => handleSort('title')}
                    >
                      {t('taskList.taskName')}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell>
                    <TableSortLabel
                      active={sortKey === 'priority_score'}
                      direction={sortKey === 'priority_score' && sortDesc ? 'desc' : 'asc'}
                      onClick={() => handleSort('priority_score')}
                    >
                      {t('taskList.priority')}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell>
                    <TableSortLabel
                      active={sortKey === 'due_date'}
                      direction={sortKey === 'due_date' && sortDesc ? 'desc' : 'asc'}
                      onClick={() => handleSort('due_date')}
                    >
                      {t('taskList.due')}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ minWidth: 140 }}>{t('taskList.progress')}</TableCell>
                  <TableCell>{t('taskList.status')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map(task => {
                  const overdue = isOverdue(task);
                  const dueToday = isDueToday(task) && task.status !== 'DONE' && task.status !== 'CANCELLED';
                  return (
                    <TableRow key={task.id} hover sx={{ cursor: 'pointer' }} onClick={() => navigate(`/tasks/${task.id}`)}>
                      <TableCell>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <CategoryDot categoryId={task.category_id} categories={categories} size={7} />
                          <Box sx={{
                            fontSize: 13, fontWeight: 500, color: task.status === 'DONE' ? ds.textMuted : ds.text,
                            textDecoration: task.status === 'DONE' ? 'line-through' : 'none',
                          }}>
                            {task.title}
                          </Box>
                        </Box>
                      </TableCell>
                      <TableCell><PriorityChip priority={task.priority} /></TableCell>
                      <TableCell>
                        <Box sx={{
                          fontSize: 13,
                          fontWeight: overdue || dueToday ? 700 : 400,
                          color: overdue || dueToday ? ds.dangerText : ds.textSub,
                        }}>
                          {dueToday ? t('common.today') : formatDate(task.due_date)}
                        </Box>
                      </TableCell>
                      <TableCell>
                        <ProgressBar
                          value={task.progress_percent}
                          height={8}
                          color={task.status === 'DONE' ? ds.success : overdue ? ds.danger : ds.primary}
                          showLabel
                        />
                      </TableCell>
                      <TableCell><StatusChip task={task} /></TableCell>
                    </TableRow>
                  );
                })}
                {items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} sx={{ textAlign: 'center', py: '32px', color: ds.textMuted, fontSize: 13 }}>
                      {t('taskList.empty')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}
    </Box>
  );
};

export default TaskList;
