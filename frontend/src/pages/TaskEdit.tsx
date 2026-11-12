import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
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
import { getProjectMembers, projectMembersKey } from '../api/projects';
import { isForbidden } from '../api/forbidden';
import type { Milestone, Task, TaskStatus, DependencyType } from '../types';
import { formatDate, priorityBand, priorityBandValue, todayDate } from '../utils/format';
import type { PriorityBand } from '../utils/format';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { PlusIcon, TrashIcon } from '../components/icons';
import TaskRemovalDialog from '../components/tasks/TaskRemovalDialog';
import { milestoneReachable, parseScope, pickableProjects } from '../projects/projectScope';
import { useProjectScope } from '../projects/useProjectScope';

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
  // Manually set remaining. When empty, "estimate - actual" is used as the default
  remaining_hours: string;
  parent_task_id: string;
  milestone_id: string;
  // '' = uncategorized. Child tasks follow the parent (not selectable. ADR-0024)
  project_id: string;
  // Assignee (ADR-0055). '' = unassigned, 'auto' = not sent (a new task gets its creator)
  assignee: string;
  // Allocation (%). '' = no allocation (done one after another. ADR-0058)
  allocation_percent: string;
  memo: string;
}

const defaultForm: FormData = {
  title: '', category_id: '', priority: 3, urgency: 3, status: 'TODO',
  start_date: '', due_date: '', estimated_hours: '', actual_hours: '', remaining_hours: '',
  parent_task_id: '', milestone_id: '', project_id: '', assignee: 'auto', allocation_percent: '', memo: '',
};

const toForm = (t: Task): FormData => ({
  title: t.title, category_id: String(t.category_id ?? ''), priority: t.priority,
  urgency: t.urgency, status: t.status, start_date: t.start_date ?? '',
  due_date: t.due_date ?? '', estimated_hours: String(t.estimated_hours ?? ''),
  actual_hours: String(t.actual_hours ?? 0),
  remaining_hours: t.remaining_hours_entered === null ? '' : String(t.remaining_hours_entered),
  parent_task_id: String(t.parent_task_id ?? ''),
  milestone_id: String(t.milestone_id ?? ''), project_id: String(t.project_id ?? ''),
  assignee: t.assignee_user_id == null ? '' : String(t.assignee_user_id),
  allocation_percent: t.allocation_percent == null ? '' : String(t.allocation_percent), memo: t.memo ?? '',
});

// "Today" in the user's configured time zone as YYYY-MM-DD (the date the actual-time delta is recorded on)
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

// Radio pills for priority/urgency (high/medium/low)
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
  const [milestoneCleared, setMilestoneCleared] = useState(false);
  const [removing, setRemoving] = useState(false);
  const { scope, projects } = useProjectScope();

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

  const isChild = form.parent_task_id !== '';
  const projectNumber = form.project_id ? Number(form.project_id) : null;
  // Selectable milestones: those of this project and its ancestors, and uncategorized ones (ADR-0024)
  const reachableMilestones = (milestonesList: Milestone[] | undefined, projectId: number | null) =>
    (milestonesList ?? []).filter((m) => milestoneReachable(projects, m.project_id, projectId));
  // Assignee candidates are the members of the tree (ADR-0055). For uncategorized tasks only the creator
  const memberProject = isChild ? (task?.project_id ?? projectNumber) : projectNumber;
  const { data: members } = useQuery({
    queryKey: projectMembersKey(memberProject ?? 0),
    queryFn: () => getProjectMembers(memberProject ?? 0),
    enabled: memberProject !== null,
  });
  const assigneeChoices = memberProject === null ? [] : (members?.members ?? []);
  const changeProject = (value: string) => {
    const next = value ? Number(value) : null;
    const current = milestones?.find((m) => String(m.id) === form.milestone_id);
    const keep = current === undefined || milestoneReachable(projects, current.project_id, next);
    setMilestoneCleared(!keep);
    // A new task moved to uncategorized gets its creator (me) back as assignee
    const assignee = next === null && isNew && form.assignee !== '' ? 'auto' : form.assignee;
    setForm({ ...form, project_id: value, milestone_id: keep ? form.milestone_id : '', assignee });
  };
  useEffect(() => { if (task) setForm(toForm(task)); }, [task]);
  // A new task defaults to me (once members are loaded, show my row as selected)
  useEffect(() => {
    const me = members?.members.find((m) => m.is_you);
    if (isNew && me) setForm((f) => (f.assignee === 'auto' ? { ...f, assignee: String(me.user_id) } : f));
  }, [isNew, members]);
  // A new task goes into the given project (`?project=<id>`, coming from a group header in the task list; `none` is uncategorized),
  // otherwise into the currently filtered project
  const [searchParams] = useSearchParams();
  const projectParam = searchParams.get('project');
  useEffect(() => {
    if (!isNew) return;
    const asked = projectParam === null ? null : parseScope(projectParam);
    const preset = asked === null ? scope : asked;
    if (typeof preset === 'number') setForm((f) => (f.project_id === '' ? { ...f, project_id: String(preset) } : f));
  }, [isNew, scope, projectParam]);

  const save = useMutation({
    mutationFn: async (data: Partial<Task>) => {
      const saved = isNew ? await createTask(data) : await updateTask(Number(id), data);
      // Record the change in actual hours as a work log (actuals are the sum of work logs)
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
      qc.invalidateQueries({ queryKey: ['kpi'] });
      qc.invalidateQueries({ queryKey: ['worklogs', id] });
      qc.invalidateQueries({ queryKey: ['task'] });
      // Milestone forecast dates change too (ADR-0058)
      qc.invalidateQueries({ queryKey: ['milestones'] });
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
    // Dependencies move forecast dates (ADR-0058)
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deps', id] }); setDepPredId('');
      qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['milestones'] });
    },
  });

  const delDep = useMutation({
    mutationFn: (predId: number) => removeDependency(Number(id), predId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deps', id] });
      qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['milestones'] });
    },
  });

  const allocationInvalid = form.allocation_percent !== ''
    && !(Number.isInteger(Number(form.allocation_percent)) && Number(form.allocation_percent) >= 1 && Number(form.allocation_percent) <= 100);

  const assigneeChanged = form.assignee !== 'auto'
    && (isNew || form.assignee !== (task?.assignee_user_id == null ? '' : String(task.assignee_user_id)));

  const handleSubmit = () => {
    if (!form.title.trim()) {
      setShowTitleError(true);
      return;
    }
    if (allocationInvalid) return;
    save.mutate({
      title: form.title, category_id: form.category_id ? Number(form.category_id) : null,
      priority: form.priority, urgency: form.urgency, status: form.status,
      start_date: form.start_date || null, due_date: form.due_date || null,
      estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
      // Sending empty clears the manual value and goes back to the estimate - actual default
      remaining_hours: form.remaining_hours === '' ? null : Number(form.remaining_hours),
      parent_task_id: form.parent_task_id ? Number(form.parent_task_id) : null,
      milestone_id: form.milestone_id ? Number(form.milestone_id) : null,
      // Child tasks belong to the parent's project (not sent; moving the parent moves its descendants)
      ...(isChild ? {} : { project_id: form.project_id ? Number(form.project_id) : null }),
      // Send the assignee only when changed (an existing assignee stays even if they left. ADR-0055)
      ...(assigneeChanged ? { assignee_user_id: form.assignee === '' ? null : Number(form.assignee) } : {}),
      // Tasks with children don't use time (their forecast rolls up the children), so don't send it
      ...(isParent ? {} : { allocation_percent: form.allocation_percent === '' ? null : Number(form.allocation_percent) }),
      memo: form.memo || null,
    });
  };

  if (!isNew && taskLoading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  }

  const titleError = showTitleError && !form.title.trim();

  // Default when remaining is empty (estimate - actual, never negative). Undefined when the estimate is empty too
  const estNum = Number(form.estimated_hours);
  const actNum = form.actual_hours === '' ? 0 : Number(form.actual_hours);
  const defaultRemaining =
    form.estimated_hours === '' || isNaN(estNum)
      ? null
      : Math.max(Math.round((estNum - (isNaN(actNum) ? 0 : actNum)) * 100) / 100, 0);
  // Progress of a task with children is the roll-up of its children, so don't let it have its own remaining
  const isParent = !isNew && (task?.has_subtasks ?? false);

  return (
    <Box sx={{ maxWidth: 640, mx: 'auto' }}>
      {!isNew && removing && (
        <TaskRemovalDialog
          taskId={Number(id)} open={removing} onClose={() => setRemoving(false)}
          onDone={() => { setRemoving(false); navigate('/tasks'); }}
        />
      )}
      {!isNew && (
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: '14px', minHeight: 40 }}>
          <Tab label={t('taskEdit.tabBasic')} sx={{ minHeight: 40 }} />
          <Tab label={t('taskEdit.tabWorklog')} sx={{ minHeight: 40 }} />
          <Tab label={t('taskEdit.tabDependencies')} sx={{ minHeight: 40 }} />
        </Tabs>
      )}
      {save.isError && <Alert severity="error" sx={{ mb: '14px' }}>{isForbidden(save.error) ? t('move.crossTreeManagerOnly') : t('taskEdit.saveError')}</Alert>}
      {task?.archived_at && <Alert severity="info" sx={{ mb: '14px' }}>{t('taskRemoval.archivedNotice')}</Alert>}

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
            )}
            <Box sx={{ flex: '1 1 160px' }}>
              <FieldLabel>{t('taskEdit.remainingHours')}</FieldLabel>
              {isParent ? (
                <TextField
                  fullWidth size="small" disabled
                  value={task?.rollup_remaining_hours ?? '—'}
                  helperText={t('taskEdit.remainingRollup')}
                />
              ) : (
                <TextField
                  fullWidth size="small" type="number"
                  slotProps={{ htmlInput: { min: 0, step: 0.5 } }}
                  value={form.remaining_hours}
                  placeholder={defaultRemaining === null ? '' : String(defaultRemaining)}
                  helperText={
                    defaultRemaining === null
                      ? t('taskEdit.remainingHelpNoEstimate')
                      : t('taskEdit.remainingHelp', { hours: defaultRemaining })
                  }
                  onChange={e => setForm({ ...form, remaining_hours: e.target.value })}
                />
              )}
            </Box>
          </Box>

          {/* Project (task #187). Child tasks follow the parent and can't choose here */}
          <Box>
            <FieldLabel>{t('taskEdit.project')}</FieldLabel>
            {isChild ? (
              <TextField
                fullWidth size="small" disabled
                value={task?.project_path ?? t('scope.none')}
                helperText={t('taskEdit.projectFromParent')}
              />
            ) : (
              <Select
                fullWidth size="small" displayEmpty
                value={form.project_id}
                onChange={e => changeProject(String(e.target.value))}
                // Once chosen, show the full path (so same-named sub-projects on other branches aren't confused)
                renderValue={(v) => (v === '' ? t('scope.none') : projects.find((p) => String(p.id) === v)?.path ?? '')}
              >
                <MenuItem value="">{t('scope.none')}</MenuItem>
                {pickableProjects(projects, task?.project_id ?? null).map(({ project, depth }) => (
                  <MenuItem key={project.id} value={String(project.id)} sx={{ pl: `${16 + depth * 14}px` }}>
                    {project.name}
                  </MenuItem>
                ))}
              </Select>
            )}
          </Box>

          {/* Assignee (task #544). Chosen from the members of the tree */}
          <Box>
            <FieldLabel>{t('taskEdit.assignee')}</FieldLabel>
            <Select
              fullWidth size="small" displayEmpty
              value={form.assignee}
              onChange={e => setForm({ ...form, assignee: String(e.target.value) })}
              renderValue={(v) => {
                if (v === '') return t('taskEdit.noAssignee');
                if (v === 'auto') return t('member.you');
                const member = assigneeChoices.find((m) => String(m.user_id) === v);
                if (member) return member.display_name || member.email;
                return t('taskEdit.assigneeOutside', { name: task?.assignee_name ?? '' });
              }}
            >
              <MenuItem value="">{t('taskEdit.noAssignee')}</MenuItem>
              {memberProject === null && (
                <MenuItem value={isNew ? 'auto' : String(task?.user_id ?? '')}>{t('member.you')}</MenuItem>
              )}
              {assigneeChoices.map((m) => (
                <MenuItem key={m.user_id} value={String(m.user_id)}>
                  {m.display_name || m.email}{m.is_you ? `（${t('member.you')}）` : ''}
                </MenuItem>
              ))}
              {memberProject !== null && form.assignee !== '' && form.assignee !== 'auto'
                && !assigneeChoices.some((m) => String(m.user_id) === form.assignee) && (
                <MenuItem value={form.assignee}>{t('taskEdit.assigneeOutside', { name: task?.assignee_name ?? '' })}</MenuItem>
              )}
            </Select>
            <Box sx={{ fontSize: 12, color: ds.textMuted, mt: '4px' }}>{t('taskEdit.assigneeHint')}</Box>
          </Box>

          {/* Allocation (task #554, ADR-0058). Hidden for tasks with children since they don't use time */}
          {!isParent && (
            <Box>
              <FieldLabel>{t('taskEdit.allocation')}</FieldLabel>
              <TextField
                size="small" type="number" sx={{ width: 160 }}
                value={form.allocation_percent}
                placeholder={t('taskEdit.allocationNone')}
                error={allocationInvalid}
                slotProps={{ htmlInput: { min: 1, max: 100, step: 5, 'aria-label': t('taskEdit.allocation') } }}
                onChange={e => setForm({ ...form, allocation_percent: e.target.value })}
              />
              <Box sx={{ fontSize: 12, color: allocationInvalid ? ds.danger : ds.textMuted, mt: '4px' }}>
                {allocationInvalid ? t('taskEdit.allocationInvalid') : t('taskEdit.allocationHint')}
              </Box>
            </Box>
          )}

          <Box>
            <FieldLabel>{t('taskEdit.milestone')}</FieldLabel>
            <Select
              fullWidth size="small" displayEmpty
              value={form.milestone_id}
              onChange={e => { setMilestoneCleared(false); setForm({ ...form, milestone_id: String(e.target.value) }); }}
            >
              <MenuItem value="">{t('taskEdit.none')}</MenuItem>
              {reachableMilestones(milestones, isChild ? (task?.project_id ?? null) : projectNumber).map(m => (
                <MenuItem key={m.id} value={String(m.id)}>{m.name}</MenuItem>
              ))}
            </Select>
            <Box sx={{ fontSize: 12, color: milestoneCleared ? ds.dangerText : ds.textMuted, mt: '4px' }}>
              {milestoneCleared ? t('taskEdit.milestoneCleared') : t('taskEdit.milestoneHint')}
            </Box>
          </Box>

          <Box sx={{
            display: 'flex', justifyContent: 'flex-end', gap: '12px',
            pt: '14px', borderTop: `1px solid ${ds.borderPale}`,
          }}>
            {!isNew && task && !task.archived_at && (
              <Button
                onClick={() => setRemoving(true)} startIcon={<TrashIcon size={14} />}
                sx={{ color: ds.dangerText, mr: 'auto' }} data-testid="task-remove"
              >
                {t('taskRemoval.open')}
              </Button>
            )}
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
