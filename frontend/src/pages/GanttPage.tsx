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
  // サイドバーで選んだプロジェクト（と子孫）だけ（task #187、ADR-0024）
  const { scope } = useProjectScope();
  const { data, isLoading, error } = useQuery({
    queryKey: ['tasks', 'scope', scope],
    queryFn: () => getTasks(scopeParams(scope)),
  });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });
  // マイルストーンの期限と見込みの日（ADR-0058）。取れなくてもタスクは出す
  const { data: milestones } = useQuery({
    queryKey: ['milestones', 'scope', scope],
    queryFn: () => getScopedMilestones(scopeParams(scope)),
  });
  // 実績の帯（確定した実績。task #162）。取れなくても計画の帯は出す
  const { data: actualSpans } = useQuery({ queryKey: [...ACTUALS_KEY, 'gantt'], queryFn: () => getGanttActuals() });
  const actuals = useMemo(() => new Map((actualSpans ?? []).map((s) => [s.task_id, s])), [actualSpans]);

  const toggleDone = useMutation({
    mutationFn: (task: Task) => (task.status === 'DONE' ? reopenTask(task) : completeTask(task)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['today'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      qc.invalidateQueries({ queryKey: ['milestones'] });
    },
  });

  // 左の表のセルをその場で保存する。見込みは読み直したときに計算し直される（ADR-0058 決定 4・ADR-0059 決定 3）
  const editTask = useMutation({
    mutationFn: ({ task, patch }: { task: Task; patch: Partial<Task> }) => updateTask(task.id, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] });
      qc.invalidateQueries({ queryKey: ['milestones'] });
      qc.invalidateQueries({ queryKey: ['today'] });
    },
  });

  // 担当に選べるのは、そのタスクのいちばん上のプロジェクトのメンバー（ADR-0055）
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
  // 日の列はプロジェクトのカレンダーで塗る（task #559）。表示しているプロジェクトと、タスクのあるプロジェクトのもの
  const calendarProjects = useMemo(() => {
    const ids = new Set((data ?? []).map((task) => task.project_id).filter((id): id is number => id != null));
    if (typeof scope === 'number') ids.add(scope);
    return [...ids].sort((a, b) => a - b);
  }, [data, scope]);
  // combine の結果は中身が同じなら同じ参照のまま（行の塗り直しの計算を毎回やり直さない）
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

  // 未分類のタスク（担当は作った人だけ）とメンバーが読めないものは変えない
  const assigneeChoices = (task: Task) => {
    const root = task.project_id == null ? undefined : rootOf.get(task.project_id);
    return root === undefined ? null : choicesByRoot.get(root) ?? null;
  };

  // 始まりの順に並べ、子タスクは親の直後へ（枝の罫線でつなぐ。task #639）
  const nested = useMemo(
    () => nestBySubtask((data ?? [])
      // 計画の日付が無くても、終わる見込みがあれば出す
      .filter(showsOnGantt)
      .sort((a, b) => (a.start_date ?? a.due_date ?? '').localeCompare(b.start_date ?? b.due_date ?? ''))),
    [data],
  );
  const tasks = useMemo(() => nested.map((n) => n.task), [nested]);
  const guides = useMemo(() => {
    const list = treeGuides(nested.map((n) => n.level));
    return new Map(nested.map((n, i) => [n.task.id, list[i]]));
  }, [nested]);
  // WBS 番号は絞る前の一覧で（タスクの一覧と同じ番号）
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
