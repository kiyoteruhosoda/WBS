import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Box, CircularProgress, Alert, Table, TableBody, TableCell, TableHead,
  TableRow, TableSortLabel, Select, MenuItem, FormControl, InputLabel,
  TableContainer, OutlinedInput, InputAdornment, TextField, IconButton, Tooltip,
  Checkbox, Button, ToggleButton, ToggleButtonGroup, Snackbar, Chip,
} from '@mui/material';
import MoreTimeIcon from '@mui/icons-material/MoreTime';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import AddIcon from '@mui/icons-material/Add';
import { scheduleTaskPath } from '../calendar/taskScheduling';
import { getTasks } from '../api/tasks';
import { getCategories } from '../api/categories';
import { getMilestones } from '../api/milestones';
import { formatDate, formatHours, isOverdue, isDueToday } from '../utils/format';
import type { Task, TaskMoveToProjectResult, TaskStatus } from '../types';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import StatusChip from '../components/StatusChip';
import PriorityChip from '../components/PriorityChip';
import ProgressBar from '../components/ProgressBar';
import CategoryDot from '../components/CategoryDot';
import ProjectScopeSelect from '../components/ProjectScopeSelect';
import MoveToProjectDialog from '../components/tasks/MoveToProjectDialog';
import { SearchIcon } from '../components/icons';
import { scopeParams } from '../projects/projectScope';
import { useProjectScope } from '../projects/useProjectScope';
import {
  followingIds, groupRows, groupTaskIds, groupTasksByProject, planProjectMove, sortTasks,
  type TaskGroupNode, type TaskListRow, type TaskSortKey,
} from '../projects/taskListView';

const STATUSES: TaskStatus[] = ['TODO', 'DOING', 'WAITING', 'DONE', 'CANCELLED'];

// プロジェクトで束ねるか（端末の好み。失われても困らない。task #187・ADR-0030）
const GROUPED_KEY = 'wbs.taskList.groupByProject';
const readGrouped = (): boolean => {
  try {
    return window.localStorage.getItem(GROUPED_KEY) !== 'off';
  } catch {
    return true;
  }
};

/** スマホ幅では隠す列（題名・期限・ステータスと打刻の予定だけ残す）。 */
const wideOnly = { display: { xs: 'none', sm: 'table-cell' } } as const;
/** プロジェクトの列は PC 幅だけ（狭い幅では題名の下に道筋を出す）。 */
const desktopOnly = { display: { xs: 'none', md: 'table-cell' } } as const;

const TaskList: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [statusFilter, setStatusFilter] = useState<TaskStatus[]>([]);
  const [categoryId, setCategoryId] = useState<string>('');
  const [milestoneId, setMilestoneId] = useState<string>('');
  const [keyword, setKeyword] = useState('');
  const [sortKey, setSortKey] = useState<TaskSortKey>('priority_score');
  const [sortDesc, setSortDesc] = useState(false);
  const [grouped, setGroupedState] = useState<boolean>(readGrouped);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [moveOpen, setMoveOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // 範囲はサイドバーと同じ状態（ここで替えればサイドバーも替わる）。絞りはサーバ（task #187、ADR-0024）
  const { scope, projects } = useProjectScope();
  const { data, isLoading, error } = useQuery({
    queryKey: ['tasks', 'scope', scope],
    queryFn: () => getTasks(scopeParams(scope)),
  });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  const { data: milestones } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });

  const setGrouped = (next: boolean) => {
    setGroupedState(next);
    try {
      window.localStorage.setItem(GROUPED_KEY, next ? 'on' : 'off');
    } catch {
      // 覚えられないだけで、画面は動く
    }
  };

  const handleSort = (key: TaskSortKey) => {
    if (sortKey === key) setSortDesc(!sortDesc);
    else { setSortKey(key); setSortDesc(false); }
  };

  const all = useMemo(() => data ?? [], [data]);
  const items = useMemo(() => {
    let list = all;
    if (statusFilter.length > 0) list = list.filter((t) => statusFilter.includes(t.status));
    if (categoryId) list = list.filter((t) => t.category_id === Number(categoryId));
    if (milestoneId) list = list.filter((t) => t.milestone_id === Number(milestoneId));
    if (keyword.trim()) {
      const kw = keyword.trim().toLowerCase();
      list = list.filter((t) => t.title.toLowerCase().includes(kw));
    }
    return sortTasks(list, sortKey, sortDesc, projects);
  }, [all, statusFilter, categoryId, milestoneId, keyword, sortKey, sortDesc, projects]);

  const groups = useMemo(
    () => (grouped ? groupTasksByProject(items, projects, scope) : []),
    [grouped, items, projects, scope],
  );
  const rows: TaskListRow[] = grouped
    ? groupRows(groups, collapsed)
    : items.map((task) => ({ kind: 'task' as const, task, depth: 0, level: 0 }));

  // 選べるのは見えているタスクだけ（絞り込みで隠れたものを知らずに移さない）
  const chosen = useMemo(() => items.filter((t) => selected.has(t.id)).map((t) => t.id), [items, selected]);
  const chosenSet = useMemo(() => new Set(chosen), [chosen]);
  const plan = useMemo(() => planProjectMove(chosen, all), [chosen, all]);
  const following = useMemo(() => followingIds(chosen, all), [chosen, all]);
  const stranded = useMemo(() => new Set(plan.stranded), [plan]);

  const setChecked = (ids: readonly number[], on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (on) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  };
  const allChecked = items.length > 0 && chosen.length === items.length;
  const someChecked = chosen.length > 0 && !allChecked;

  const toggleGroup = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const onMoved = (result: TaskMoveToProjectResult, targetLabel: string) => {
    setMoveOpen(false);
    setSelected(new Set());
    const moved = result.moved_task_ids.length > 0
      ? t('taskList.moved', { count: result.moved_task_ids.length, name: targetLabel })
      : t('taskList.movedNone', { name: targetLabel });
    const detached = result.detached_milestone_task_ids.length;
    setNotice(detached > 0 ? `${moved} ${t('taskList.movedDetached', { count: detached })}` : moved);
  };

  const columnCount = grouped ? 8 : 9;
  const sortLabel = (key: TaskSortKey, label: string) => (
    <TableSortLabel
      active={sortKey === key}
      direction={sortKey === key && sortDesc ? 'desc' : 'asc'}
      onClick={() => handleSort(key)}
    >
      {label}
    </TableSortLabel>
  );

  const groupRow = (g: TaskGroupNode) => {
    const ids = groupTaskIds(g);
    // 親と一緒に移る子も選んだものとして数える（見た目のチェックと揃える）
    const checkedCount = ids.filter((id) => chosenSet.has(id) || following.has(id)).length;
    const isCollapsed = collapsed.has(g.key);
    // 最上位は道筋で（範囲で選んだプロジェクトが最上位になると、名前だけでは親が分からない）
    const label = g.projectId === null ? t('scope.none') : (g.depth === 0 ? g.path : g.name) ?? g.path ?? '';
    return (
      <TableRow key={g.key} data-testid="tasklist-group" sx={{ bgcolor: g.depth === 0 ? ds.hairline : ds.paper }}>
        <TableCell padding="checkbox">
          {/* ⚠ 行のチェックと同じく span で包む（直の子のときだけ MUI が余白を 0 にして、列が揃わない） */}
          <Box component="span">
            <Checkbox
              size="small"
              checked={ids.length > 0 && checkedCount === ids.length}
              indeterminate={checkedCount > 0 && checkedCount < ids.length}
              onChange={(e) => setChecked(ids, e.target.checked)}
              slotProps={{ input: { 'aria-label': t('taskList.selectGroup', { name: label }) } }}
            />
          </Box>
        </TableCell>
        <TableCell colSpan={columnCount - 1} sx={{ py: '4px !important' }}>
          <Box sx={{
            display: 'flex', alignItems: 'center', columnGap: '6px', minWidth: 0,
            pl: { xs: `${g.depth * 10}px`, sm: `${g.depth * 18}px` },
          }}>
            <IconButton
              size="small"
              onClick={() => toggleGroup(g.key)}
              aria-expanded={!isCollapsed}
              aria-label={t(isCollapsed ? 'taskList.expandGroup' : 'taskList.collapseGroup', { name: label })}
              sx={{ p: '4px' }}
            >
              {isCollapsed ? <ChevronRightIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
            </IconButton>
            <Box component="span" sx={{
              width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
              bgcolor: g.projectId === null ? 'transparent' : g.color ?? ds.textMuted,
              border: g.projectId === null ? `1.5px dashed ${ds.textMuted}` : 'none',
            }} />
            <Box sx={{
              fontSize: 13, fontWeight: 700, color: g.archived ? ds.textMuted : ds.text,
              // スマホ幅では折り返す（1 行に詰めると表が画面より広がる）
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: { xs: 'normal', sm: 'nowrap' }, minWidth: 0,
            }} title={g.path ?? label}>
              {label}
            </Box>
            {g.archived && (
              <Chip size="small" label={t('project.archived')} sx={{ height: 18, fontSize: 11, flexShrink: 0 }} />
            )}
            <Box sx={{ fontSize: 12, color: ds.textSub, whiteSpace: 'nowrap', flexShrink: 0 }}>
              {t('taskList.groupSummary', { count: g.total, hours: formatHours(g.remainingHours) })}
            </Box>
            <Box sx={{ flex: 1 }} />
            <Tooltip title={t('taskList.newInGroup', { name: label })}>
              <IconButton
                size="small"
                aria-label={t('taskList.newInGroup', { name: label })}
                onClick={() => navigate(`/tasks/new?project=${g.projectId ?? 'none'}`)}
                sx={{ color: ds.primary, p: '4px' }}
              >
                <AddIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </TableCell>
      </TableRow>
    );
  };

  const taskRow = (task: Task, depth: number, level: number) => {
    const overdue = isOverdue(task);
    const closed = task.status === 'DONE' || task.status === 'CANCELLED';
    const dueToday = isDueToday(task) && !closed;
    const isChosen = chosenSet.has(task.id);
    const follows = following.has(task.id) && !isChosen;
    const checkboxHint = follows
      ? t('taskList.followsParent')
      : task.parent_task_id != null ? t('taskList.subtaskHint') : undefined;
    return (
      <TableRow
        key={task.id} hover selected={isChosen} sx={{ cursor: 'pointer' }}
        onClick={() => navigate(`/tasks/${task.id}`)}
        data-testid="tasklist-row"
      >
        <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
          <Box component="span" title={checkboxHint}>
            <Checkbox
              size="small"
              checked={isChosen || follows}
              disabled={follows}
              onChange={(e) => setChecked([task.id], e.target.checked)}
              slotProps={{ input: { 'aria-label': t('taskList.selectTask', { title: task.title }) } }}
            />
          </Box>
        </TableCell>
        <TableCell>
          <Box sx={{
            display: 'flex', alignItems: 'center', gap: '8px',
            pl: grouped ? { xs: `${depth * 10 + level * 12 + 8}px`, sm: `${depth * 18 + level * 18 + 30}px` } : 0,
          }}>
            <CategoryDot categoryId={task.category_id} categories={categories} size={7} />
            <Box sx={{ minWidth: 0 }}>
              <Box sx={{
                fontSize: 13, fontWeight: 500, color: task.status === 'DONE' ? ds.textMuted : ds.text,
                textDecoration: task.status === 'DONE' ? 'line-through' : 'none',
              }}>
                {task.parent_task_id != null && (
                  <Box component="span" sx={{ color: ds.textMuted, mr: '4px' }} aria-hidden>↳</Box>
                )}
                {task.title}
              </Box>
              {/* 束ねない表では、狭い幅だけ題名の下に道筋（広い幅はプロジェクトの列） */}
              {!grouped && task.project_path && (
                <Box sx={{ fontSize: 11, color: ds.textMuted, display: { xs: 'block', md: 'none' } }} title={t('taskList.project')}>
                  {task.project_path}
                </Box>
              )}
              {stranded.has(task.id) && (
                <Box sx={{ fontSize: 11, color: ds.warnText }}>{t('taskList.strandedRow')}</Box>
              )}
            </Box>
          </Box>
        </TableCell>
        {!grouped && (
          <TableCell sx={desktopOnly}>
            <Box sx={{ fontSize: 12, color: task.project_path ? ds.textSub : ds.textMuted, whiteSpace: 'nowrap' }}>
              {task.project_path ?? t('scope.none')}
            </Box>
          </TableCell>
        )}
        <TableCell sx={wideOnly}><PriorityChip priority={task.priority} /></TableCell>
        <TableCell>
          <Box sx={{
            fontSize: 13, whiteSpace: 'nowrap',
            fontWeight: overdue || dueToday ? 700 : 400,
            color: overdue || dueToday ? ds.dangerText : ds.textSub,
          }}>
            {dueToday ? t('common.today') : formatDate(task.due_date)}
          </Box>
        </TableCell>
        <TableCell sx={wideOnly}>
          <ProgressBar
            value={task.progress_percent}
            height={8}
            color={task.status === 'DONE' ? ds.success : overdue ? ds.danger : ds.primary}
            showLabel
          />
        </TableCell>
        <TableCell><StatusChip task={task} /></TableCell>
        <TableCell sx={wideOnly}>
          <Box sx={{ fontSize: 13, color: ds.textSub, whiteSpace: 'nowrap' }}>
            {formatHours(task.scheduled_hours)}
          </Box>
          {task.unscheduled_hours != null && task.unscheduled_hours > 0 && !closed && (
            <Box sx={{ fontSize: 11, color: ds.textMuted, whiteSpace: 'nowrap' }}>
              {t('taskList.unscheduled', { hours: formatHours(task.unscheduled_hours) })}
            </Box>
          )}
        </TableCell>
        <TableCell padding="checkbox">
          {!closed && (
            <Tooltip title={t('task.scheduleTime')}>
              <IconButton
                size="small"
                aria-label={t('task.scheduleTime')}
                onClick={(e) => { e.stopPropagation(); navigate(scheduleTaskPath(task.id)); }}
              >
                <MoreTimeIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </TableCell>
      </TableRow>
    );
  };

  const carried = plan.carried + plan.followers.length;

  return (
    <Box>
      {/* フィルタツールバー。プロジェクトが先頭（サイドバーの範囲と同じ状態） */}
      <Box sx={{ display: 'flex', gap: '12px', mb: '14px', flexWrap: 'wrap', alignItems: 'center' }}>
        <ProjectScopeSelect inline />
        <TextField
          size="small"
          placeholder={t('taskList.searchPlaceholder')}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          sx={{ minWidth: 200, flex: { xs: '1 1 100%', sm: '0 1 auto' } }}
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
        <FormControl size="small" sx={{ minWidth: 140, flex: { xs: '1 1 140px', sm: '0 0 auto' } }}>
          <InputLabel>{t('taskList.status')}</InputLabel>
          <Select multiple value={statusFilter as unknown as string[]}
            onChange={(e) => setStatusFilter(e.target.value as unknown as TaskStatus[])}
            input={<OutlinedInput label={t('taskList.status')} />}
            renderValue={(sel) => (sel as unknown as TaskStatus[]).map(s => t(`status.${s}`)).join(', ')}>
            {STATUSES.map(s => <MenuItem key={s} value={s}>{t(`status.${s}`)}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140, flex: { xs: '1 1 140px', sm: '0 0 auto' } }}>
          <InputLabel>{t('taskList.category')}</InputLabel>
          <Select value={categoryId} label={t('taskList.category')} onChange={e => setCategoryId(e.target.value)}>
            <MenuItem value="">{t('taskList.all')}</MenuItem>
            {categories?.map(c => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140, flex: { xs: '1 1 140px', sm: '0 0 auto' } }}>
          <InputLabel>{t('taskList.milestone')}</InputLabel>
          <Select value={milestoneId} label={t('taskList.milestone')} onChange={e => setMilestoneId(e.target.value)}>
            <MenuItem value="">{t('taskList.all')}</MenuItem>
            {milestones?.map(m => <MenuItem key={m.id} value={String(m.id)}>{m.name}</MenuItem>)}
          </Select>
        </FormControl>
        <ToggleButtonGroup
          exclusive size="small" value={grouped ? 'grouped' : 'flat'}
          onChange={(_, v: 'grouped' | 'flat' | null) => { if (v) setGrouped(v === 'grouped'); }}
          aria-label={t('taskList.view')}
        >
          <ToggleButton value="grouped" sx={{ px: '12px', py: '5px', fontSize: 12 }} data-testid="tasklist-view-grouped">
            {t('taskList.viewGrouped')}
          </ToggleButton>
          <ToggleButton value="flat" sx={{ px: '12px', py: '5px', fontSize: 12 }} data-testid="tasklist-view-flat">
            {t('taskList.viewFlat')}
          </ToggleButton>
        </ToggleButtonGroup>
        <Box sx={{ fontSize: 13, color: ds.textSub, ml: 'auto' }}>{t('taskList.count', { count: items.length })}</Box>
      </Box>

      {/* まとめて移す（選んでいる間だけ） */}
      {chosen.length > 0 && (
        <Box data-testid="tasklist-bulkbar" sx={{
          display: 'flex', flexWrap: 'wrap', alignItems: 'center', columnGap: '12px', rowGap: '6px',
          px: '14px', py: '10px', mb: '10px', bgcolor: ds.primaryPale,
          border: `1px solid ${ds.primaryPaleBorder}`, borderRadius: '10px',
        }}>
          <Box sx={{ fontSize: 13, fontWeight: 700, color: ds.primary }}>
            {t('taskList.selectedCount', { count: chosen.length })}
          </Box>
          <Button
            variant="contained" size="small" disabled={plan.roots.length === 0}
            onClick={() => setMoveOpen(true)} data-testid="tasklist-move"
          >
            {t('taskList.moveAction')}
          </Button>
          <Button size="small" onClick={() => setSelected(new Set())}>{t('taskList.clearSelection')}</Button>
          {(carried > 0 || plan.stranded.length > 0) && (
            <Box sx={{ flexBasis: '100%', fontSize: 12, color: ds.textSub }}>
              {carried > 0 && <Box>{t('taskList.moveCarried', { count: carried })}</Box>}
              {plan.stranded.length > 0 && (
                <Box sx={{ color: ds.warnText }}>{t('taskList.moveStranded', { count: plan.stranded.length })}</Box>
              )}
            </Box>
          )}
        </Box>
      )}

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>}
      {error && <Alert severity="error">{t('common.loadError')}</Alert>}
      {data && (
        <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', overflow: 'hidden' }}>
          <TableContainer>
            <Table size="small" sx={{
              '& td': { py: '10px' },
              // スマホ幅では左右の余白を詰める（チェックの列は MUI の幅のまま）
              '& td:not(.MuiTableCell-paddingCheckbox), & th:not(.MuiTableCell-paddingCheckbox)': { px: { xs: '6px', sm: '16px' } },
              '& td.MuiTableCell-paddingCheckbox, & th.MuiTableCell-paddingCheckbox': { pl: { xs: '4px', sm: '16px' }, pr: { xs: 0, sm: '12px' } },
              '& th': { whiteSpace: 'nowrap' },
            }}>
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Box component="span">
                      <Checkbox
                        size="small"
                        checked={allChecked}
                        indeterminate={someChecked}
                        disabled={items.length === 0}
                        onChange={(e) => setChecked(items.map((x) => x.id), e.target.checked)}
                        slotProps={{ input: { 'aria-label': t('taskList.selectAll') } }}
                      />
                    </Box>
                  </TableCell>
                  <TableCell sx={{ minWidth: { xs: 120, sm: 220 } }}>{sortLabel('title', t('taskList.taskName'))}</TableCell>
                  {!grouped && <TableCell sx={desktopOnly}>{sortLabel('project', t('taskList.project'))}</TableCell>}
                  <TableCell sx={wideOnly}>{sortLabel('priority_score', t('taskList.priority'))}</TableCell>
                  <TableCell>{sortLabel('due_date', t('taskList.due'))}</TableCell>
                  <TableCell sx={{ ...wideOnly, minWidth: 140 }}>{t('taskList.progress')}</TableCell>
                  <TableCell>{t('taskList.status')}</TableCell>
                  <TableCell sx={wideOnly}>{t('taskList.scheduled')}</TableCell>
                  <TableCell padding="checkbox" />
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (row.kind === 'group' ? groupRow(row.group) : taskRow(row.task, row.depth, row.level)))}
                {items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={columnCount} sx={{ textAlign: 'center', py: '32px', color: ds.textMuted, fontSize: 13 }}>
                      {t('taskList.empty')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      <MoveToProjectDialog
        open={moveOpen}
        plan={plan}
        projects={projects}
        onClose={() => setMoveOpen(false)}
        onMoved={onMoved}
      />
      <Snackbar
        open={notice !== null}
        autoHideDuration={6000}
        onClose={() => setNotice(null)}
        message={notice}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Box>
  );
};

export default TaskList;
