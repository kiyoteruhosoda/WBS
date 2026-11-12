export type TaskStatus = 'TODO' | 'DOING' | 'WAITING' | 'DONE' | 'CANCELLED';
/** Why no forecast is given (ADR-0058). finished = done, cancelled, or 0 remaining */
export type ForecastGap =
  | 'finished' | 'no_assignee' | 'no_remaining' | 'no_capacity' | 'waiting' | 'child_unforecast' | 'beyond_horizon';
export type DependencyType = 'FS' | 'SS' | 'FF' | 'SF';

export interface Task {
  id: number;
  user_id: number;
  title: string;
  category_id: number | null;
  priority: number;
  urgency: number;
  status: TaskStatus;
  start_date: string | null;
  due_date: string | null;
  estimated_hours: number | null;
  // Own remaining (manual value, or estimate − actual when empty; 0 for DONE) and the manually entered value itself
  remaining_hours: number | null;
  remaining_hours_entered: number | null;
  // Own actual (sum of work logs)
  actual_hours: number;
  has_subtasks: boolean;
  // Actual and remaining used in the progress formula (rolled up over self and all descendants when it has children)
  rollup_actual_hours: number;
  rollup_remaining_hours: number | null;
  // actual ÷ (actual + remaining) × 100. null when the denominator is 0 or remaining is undetermined (shown as "—")
  progress_percent: number | null;
  priority_score: number;
  memo: string | null;
  parent_task_id: number | null;
  milestone_id: number | null;
  // Owning project (null = unassigned) and its display path ("parent / child"). Subtasks share their parent's (ADR-0024)
  project_id: number | null;
  project_path: string | null;
  // Assignee (ADR-0055). null when unassigned
  assignee_user_id?: number | null;
  assignee_name?: string | null;
  // Allocation ratio (%). When set, the task progresses at this share of the assignee's free time per day. null = handled in order (ADR-0058)
  allocation_percent?: number | null;
  // Forecast finish (ADR-0058; computed on each read by stacking remaining onto the assignee's free time). When not given, forecast_gap holds the reason
  forecast_start?: string | null;
  forecast_finish?: string | null;
  forecast_gap?: ForecastGap | null;
  // Calendar days by which the forecast finish exceeds the due date (0 if it doesn't)
  forecast_overdue_days?: number;
  completed_at: string | null;
  deleted_at: string | null;
  // When it was archived (tasks with actuals are archived instead of deleted. ADR-0046)
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Category {
  id: number;
  name: string;
  color: string | null;
  sort_order: number;
}

export interface Milestone {
  id: number;
  name: string;
  due_date: string | null;
  description: string | null;
  // Owning project (null = unassigned; can be attached to any task)
  project_id: number | null;
  // Latest forecast finish among the attached open tasks (ADR-0058).
  // If forecast_unforecast_count tasks have no forecast, it means "at least"
  forecast_finish?: string | null;
  forecast_unforecast_count?: number;
  forecast_overdue_days?: number;
}

export type ProjectStatus = 'active' | 'archived';

/** Project (nested. task #187 / ADR-0024). The list arrives in tree order (children right after their parent). */
export interface Project {
  id: number;
  name: string;
  parent_project_id: number | null;
  color: string | null;
  // Optional short code (only shown next to the name in lists; not unique)
  code: string | null;
  description: string | null;
  status: ProjectStatus;
  sort_order: number;
  // Display path ("parent / child")
  path: string;
  // Topmost project that has members, and the caller's role there (ADR-0055)
  root_project_id: number;
  my_role: ProjectRole | null;
}

/** Role of a project member (ADR-0055). Admins can add and remove members. */
export type ProjectRole = 'manager' | 'member';

/** A person selectable as member or assignee (anyone who has signed in to WBS at least once). */
export interface Person {
  id: number;
  display_name: string;
  email: string;
}

export interface ProjectMember {
  user_id: number;
  display_name: string;
  email: string;
  role: ProjectRole;
  // Whether this is the requester (show "remove" as "leave")
  is_you: boolean;
  // Daily work hours and engagement rate (%). Hours per day available for this project = their product (ADR-0058)
  daily_hours: number;
  engagement_percent: number;
}

/**
 * Project calendar and members' time off (ADR-0058, ADR-0059).
 * Working weekdays are held once at the root; holidays come from the opened project and its ancestors (`inherited` = taken over from a parent).
 */
export interface TeamCalendar {
  project_id: number;
  root_project_id: number;
  // Whether admin (can set weekdays, holidays and anyone's time off; members only their own time off)
  can_manage: boolean;
  workdays: WeekdayCode[];
  days_off: { day: string; name: string | null; project_id: number; inherited: boolean }[];
  // Working days on non-working weekdays (ADR-0060. Never overlap holidays; the nearest project's entry wins)
  extra_workdays: { day: string; name: string | null; project_id: number; inherited: boolean }[];
  // Share of the day off (full day 100, half day 50). If hours is set, it is that day's working hours (overtime, short day, holiday work) and the share is ignored
  leave: { user_id: number; day: string; off_percent: number; hours: number | null }[];
}

export interface ProjectMembers {
  root_project_id: number;
  can_manage: boolean;
  members: ProjectMember[];
}

export interface WorkLog {
  id: number;
  task_id: number;
  work_date: string;
  hours: number;
  memo: string | null;
}

export interface InboxItem {
  id: number;
  title: string;
  memo: string | null;
  converted_task_id: number | null;
  converted_at: string | null;
  created_at: string;
}

export interface DashboardKpi {
  total_tasks: number;
  incomplete_tasks: number;
  overdue_tasks: number;
  this_week_completed: number;
  this_week_hours: number;
}

export interface GanttTask {
  id: number;
  title: string;
  start_date: string | null;
  due_date: string | null;
  status: TaskStatus;
  parent_task_id: number | null;
  project_id: number | null;
  project_path: string | null;
  progress_percent: number | null;
  dependencies: number[];
}

export interface TaskDependency {
  predecessor_task_id: number;
  successor_task_id: number;
  dependency_type: DependencyType;
  lag_days: number;
}

export interface TaskDependenciesResponse {
  task_id: number;
  predecessors: TaskDependency[];
  successors: TaskDependency[];
}

// Response of POST /api/tasks/move-to-project (ADR-0030)
export interface TaskMoveToProjectResult {
  // Tasks whose project changed (the selected roots and the descendants moved with them)
  moved_task_ids: number[];
  // Tasks whose milestone was detached because it is no longer reachable
  detached_milestone_task_ids: number[];
}

// Query parameters of GET /api/tasks (the backend returns an array; sorting and paging are done client side)
export interface TaskListParams {
  status_filter?: string;
  category_id?: number;
  milestone_id?: number;
  parent_task_id?: number;
  // Those of this project and its descendants (ADR-0024) / unassigned only
  project_id?: number;
  unclassified?: boolean;
  // Filter by assignee: me (self), none (unassigned), or a user id (ADR-0055)
  assignee?: string;
  // End date (YYYY-MM-DD) up to which open-ended recurrences count as scheduled. Defaults to the end of this month (ADR-0051)
  scheduled_until?: string;
}

export interface UserSettings {
  display_name: string;
  timezone: string;
  language: string;
}

export interface AppInfo {
  version: string;
  git_sha: string;
  build_time: string;
  environment: string;
}

// ── Authentication (SSO) ─────────────────────────────────────────────────────────────
export interface AuthConfig {
  mode: 'single_user' | 'oidc';
  sso_enabled: boolean;
  provider_name: string | null;
  login_path: string | null;
}

export interface CurrentUser {
  user_id: number;
  email: string;
  display_name: string;
  timezone: string;
  language: string;
  /** Whether the user can create top-level projects (ADR-0065). May be missing from the offline copy */
  can_create_projects?: boolean;
}

export interface LogoutResult {
  end_session_url: string | null;
}

/** Color name (Google Calendar color names; `DEFAULT` = no color). Used for the category color list. */
export type EventColorKey =
  | 'DEFAULT'
  | 'TOMATO'
  | 'TANGERINE'
  | 'BANANA'
  | 'BASIL'
  | 'SAGE'
  | 'PEACOCK'
  | 'BLUEBERRY'
  | 'LAVENDER'
  | 'GRAPE'
  | 'GRAPHITE';

/** Weekday (the domain `Weekday`; iCalendar two-letter code). */
export type WeekdayCode = 'MO' | 'TU' | 'WE' | 'TH' | 'FR' | 'SA' | 'SU';

// What deleting a task does (ADR-0046). delete = delete / archive = has confirmed actuals, so archive instead of deleting
export interface TaskRemoval {
  task_id: number;
  title: string;
  action: 'delete' | 'archive';
  work_log_hours: number;
  archived: boolean;
}
