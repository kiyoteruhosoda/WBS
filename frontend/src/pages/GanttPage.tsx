import React, { useMemo } from 'react';
import { useQueries, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, CircularProgress, Alert } from '@mui/material';
import { getTasks, completeTask, reopenTask, updateTask } from '../api/tasks';
import { getScopedMilestones } from '../api/milestones';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { showsOnGantt } from '../forecast/forecastView';
import { getCategories } from '../api/categories';
import { getProjectMembers, getProjects, getTeamCalendar, projectMembersKey, PROJECTS_KEY, teamCalendarKey } from '../api/projects';
import type { Task, TeamCalendar } from '../types';
import { ds, headingFont } from '../theme';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import GanttChart from '../components/GanttChart';
import { ACTUAL_DAY_COLOR } from '../actuals/actualsView';
import { ACTUALS_KEY, getGanttActuals } from '../api/actuals';
import { scopeParams } from '../projects/projectScope';
import { nestBySubtask } from '../projects/taskListView';
import { treeGuides, wbsCodes } from '../projects/wbsCode';
import { useProjectScope } from '../projects/useProjectScope';

const legend: { labelKey: TranslationKey; color: string }[] = [
  { labelKey: 'status.TODO', color: ds.todoGray },
  { labelKey: 'status.DOING', color: ds.primary },
  { labelKey: 'status.DONE', color: ds.success },
  { labelKey: 'status.LATE', color: ds.danger },
];

const GanttPage: React.FC = () => {
  const qc = useQueryClient();
  const { t } = useI18n();
  // Only the project selected in the sidebar (and its descendants) (task #187, ADR-0024)
  const { scope } = useProjectScope();
  const { data, isLoading, error } = useQuery({
    queryKey: ['tasks', 'scope', scope],
    queryFn: () => getTasks(scopeParams(scope)),
  });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  // Milestone due and forecast dates (ADR-0058). Tasks are still shown if this fails
  const { data: milestones } = useQuery({
    queryKey: ['milestones', 'scope', scope],
    queryFn: () => getScopedMilestones(scopeParams(scope)),
  });
  // Actual bands (confirmed actuals. task #162). Planned bands are still shown if this fails
  const { data: actualSpans } = useQuery({ queryKey: [...ACTUALS_KEY, 'gantt'], queryFn: () => getGanttActuals() });
  const actuals = useMemo(() => new Map((actualSpans ?? []).map((s) => [s.task_id, s])), [actualSpans]);

  const toggleDone = useMutation({
    mutationFn: (task: Task) => (task.status === 'DONE' ? reopenTask(task) : completeTask(task)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      qc.invalidateQueries({ queryKey: ['milestones'] });
    },
  });

  // Save left-table cells in place. Forecasts are recomputed on reload (ADR-0058 decision 4, ADR-0059 decision 3)
  const editTask = useMutation({
    mutationFn: ({ task, patch }: { task: Task; patch: Partial<Task> }) => updateTask(task.id, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['milestones'] });
    },
  });

  // Assignee candidates are the members of the task's top-level project (ADR-0055)
  const { data: projects } = useQuery({ queryKey: PROJECTS_KEY, queryFn: getProjects });
  const rootOf = useMemo(() => new Map((projects ?? []).map((p) => [p.id, p.root_project_id])), [projects]);
  const roots = useMemo(
    () => [...new Set((data ?? []).map((task) => (task.project_id == null ? undefined : rootOf.get(task.project_id)))
      .filter((r): r is number => r !== undefined))],
    [data, rootOf],
  );
  const memberLists = useQueries({
    queries: roots.map((root) => ({ queryKey: projectMembersKey(root), queryFn: () => getProjectMembers(root) })),
  });
  const choicesByRoot = useMemo(() => {
    const map = new Map<number, { value: string; label: string }[]>();
    roots.forEach((root, i) => {
      const members = memberLists[i]?.data?.members;
      if (members) map.set(root, members.map((m) => ({ value: String(m.user_id), label: m.display_name || m.email })));
    });
    return map;
  }, [roots, memberLists]);
  // Day columns are shaded by project calendars (task #559): the displayed project's and those of the tasks' projects
  const calendarProjects = useMemo(() => {
    const ids = new Set((data ?? []).map((task) => task.project_id).filter((id): id is number => id != null));
    if (typeof scope === 'number') ids.add(scope);
    return [...ids].sort((a, b) => a - b);
  }, [data, scope]);
  // combine keeps the same reference when the content is unchanged (avoids recomputing row shading every time)
  const calendarData = useQueries({
    queries: calendarProjects.map((id) => ({ queryKey: teamCalendarKey(id), queryFn: () => getTeamCalendar(id) })),
    combine: (results) => results.map((r) => r.data),
  });
  const taskCalendars = useMemo(() => {
    const map = new Map<number, TeamCalendar>();
    calendarProjects.forEach((id, i) => { const c = calendarData[i]; if (c) map.set(id, c); });
    return map;
  }, [calendarProjects, calendarData]);
  const columnCalendar = typeof scope === 'number' ? taskCalendars.get(scope) ?? null : null;

  // Don't allow changes for uncategorized tasks (assignee is the creator only) or when members can't be loaded
  const assigneeChoices = (task: Task) => {
    const root = task.project_id == null ? undefined : rootOf.get(task.project_id);
    return root === undefined ? null : choicesByRoot.get(root) ?? null;
  };

  // Sort by start, with child tasks right after their parent (joined by branch lines. task #639)
  const nested = useMemo(
    () => nestBySubtask((data ?? [])
      // Show it even without planned dates if there is a forecast end
      .filter(showsOnGantt)
      .sort((a, b) => (a.start_date ?? a.due_date ?? '').localeCompare(b.start_date ?? b.due_date ?? ''))),
    [data],
  );
  const tasks = useMemo(() => nested.map((n) => n.task), [nested]);
  const guides = useMemo(() => {
    const list = treeGuides(nested.map((n) => n.level));
    return new Map(nested.map((n, i) => [n.task.id, list[i]]));
  }, [nested]);
  // WBS numbers come from the unfiltered list (same numbers as the task list)
  const codes = useMemo(() => wbsCodes(data ?? [], projects ?? []).tasks, [data, projects]);

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">{t('common.loadError')}</Alert>;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: '12px', mb: '14px', flexWrap: 'wrap' }}>
        <Box component="h2" sx={{ m: 0, fontFamily: headingFont, fontSize: 16, fontWeight: 700, color: ds.text }}>{t('gantt.schedule')}</Box>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('gantt.totalTasks', { count: tasks.length })}</Box>
        <Box sx={{ flex: 1 }} />
        <Box sx={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
          {legend.map((l) => (
            <Box key={l.labelKey} sx={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 12, color: ds.textSub }}>
              <Box sx={{ width: 12, height: 12, borderRadius: '3px', bgcolor: l.color }} />
              {t(l.labelKey)}
            </Box>
          ))}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 12, color: ds.textSub }}>
            <Box sx={{ width: 12, height: 6, borderRadius: '3px', bgcolor: ACTUAL_DAY_COLOR }} />
            {t('gantt.legendActual')}
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 12, color: ds.textSub }}>
            <Box sx={{ width: 16, height: 8, borderRadius: '3px', border: `1.5px dashed ${ds.primary}`, bgcolor: ds.primaryPale }} />
            {t('gantt.legendForecast')}
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: 12, color: ds.dangerText }}>
            <WarningAmberIcon sx={{ fontSize: 16 }} aria-hidden />
            {t('gantt.legendOverdue')}
          </Box>
        </Box>
      </Box>

      {tasks.length === 0 ? (
        <Box sx={{
          bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px',
          p: '40px', textAlign: 'center', fontSize: 13, color: ds.textMuted,
        }}>
          {t('gantt.empty')}
        </Box>
      ) : (
        <>
          <GanttChart
            tasks={tasks} categories={categories} actuals={actuals} milestones={milestones}
            onToggleDone={(t) => toggleDone.mutate(t)}
            onEditTask={async (task, patch) => { await editTask.mutateAsync({ task, patch }); }}
            assigneeChoices={assigneeChoices}
            columnCalendar={columnCalendar} taskCalendars={taskCalendars}
            codes={codes} guides={guides}
          />
        </>
      )}
    </Box>
  );
};

export default GanttPage;
