export type TaskStatus = 'TODO' | 'DOING' | 'WAITING' | 'DONE' | 'CANCELLED';
/** 見込みを出さない理由（ADR-0058）。finished は完了・中止・残 0 */
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
  // 自分の残（手の値、空なら 見積 − 実績。DONE は 0）と、手で入れた値そのもの
  remaining_hours: number | null;
  remaining_hours_entered: number | null;
  // 自分の実績（作業ログの合計）
  actual_hours: number;
  has_subtasks: boolean;
  // 進捗率の式に入れた実績と残（子を持つなら自分と全子孫の積み上げ）
  rollup_actual_hours: number;
  rollup_remaining_hours: number | null;
  // 実績 ÷（実績 ＋ 残）× 100。分母 0・残が決まらないときは null（「—」と出す）
  progress_percent: number | null;
  priority_score: number;
  memo: string | null;
  parent_task_id: number | null;
  milestone_id: number | null;
  // 属するプロジェクト（null = 未分類）と、表示用の道筋（「親 / 子」）。子タスクは親と同じ（ADR-0024）
  project_id: number | null;
  project_path: string | null;
  // 担当者（ADR-0055）。担当なしは null
  assignee_user_id?: number | null;
  assignee_name?: string | null;
  // アサイン比率（%）。入れたタスクは担当者の 1 日の空きのうちこの割合で進む。null は順番に片付ける（ADR-0058）
  allocation_percent?: number | null;
  // 終わる見込み（ADR-0058。読むたびに、残を担当者の空きに積んで出す）。出さないときは forecast_gap に理由
  forecast_start?: string | null;
  forecast_finish?: string | null;
  forecast_gap?: ForecastGap | null;
  // 見込みの終わりが期限を越える暦の日数（越えなければ 0）
  forecast_overdue_days?: number;
  completed_at: string | null;
  deleted_at: string | null;
  // アーカイブした時刻（実績のあるタスクは消さずにアーカイブする。ADR-0046）
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
  // 属するプロジェクト（null = 未分類。どのタスクにも付けられる）
  project_id: number | null;
  // 付いた開いているタスクの見込みの終わりのうち、いちばん遅い日（ADR-0058）。
  // 見込みの出ないタスクが forecast_unforecast_count 件あれば「少なくとも」の意味
  forecast_finish?: string | null;
  forecast_unforecast_count?: number;
  forecast_overdue_days?: number;
}

export type ProjectStatus = 'active' | 'archived';

/** プロジェクト（入れ子。task #187 / ADR-0024）。一覧は木の順（親の直後に子）で届く。 */
export interface Project {
  id: number;
  name: string;
  parent_project_id: number | null;
  color: string | null;
  // 任意の短いコード（一覧で名前の横に出すだけ。一意ではない）
  code: string | null;
  description: string | null;
  status: ProjectStatus;
  sort_order: number;
  // 表示用の道筋（「親 / 子」）
  path: string;
  // メンバーが付いているいちばん上のプロジェクトと、そこでの自分の役割（ADR-0055）
  root_project_id: number;
  my_role: ProjectRole | null;
}

/** プロジェクトのメンバーの役割（ADR-0055）。管理者はメンバーの出し入れができる。 */
export type ProjectRole = 'manager' | 'member';

/** メンバー・担当者に選べる人（WBS に 1 度でもログインした人）。 */
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
  // 聞いた本人か（「外す」を「抜ける」と出す）
  is_you: boolean;
  // 1 日の工数（時間）と従事率（%）。1 日にこのプロジェクトに使える時間 = 掛けた値（ADR-0058）
  daily_hours: number;
  engagement_percent: number;
}

/**
 * プロジェクトのカレンダーと、メンバーの休み（ADR-0058・ADR-0059）。
 * 稼働する曜日は根に 1 つ、休日は開いたプロジェクトと先祖のもの（`inherited` は親から引き継いだもの）。
 */
export interface TeamCalendar {
  project_id: number;
  root_project_id: number;
  // 管理者か（曜日・休日と、だれの休みでも入れられる。メンバーは自分の休みだけ）
  can_manage: boolean;
  workdays: WeekdayCode[];
  days_off: { day: string; name: string | null; project_id: number; inherited: boolean }[];
  // 稼働しない曜日に働く日（ADR-0060。休日とは重ならない。近いプロジェクトのものが勝つ）
  extra_workdays: { day: string; name: string | null; project_id: number; inherited: boolean }[];
  // 休む割合（終日 100・半休 50）。hours があればその日の稼働時間（残業・短い日・休日出勤）で、割合は見ない
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

// POST /api/tasks/move-to-project の応答（ADR-0030）
export interface TaskMoveToProjectResult {
  // プロジェクトが替わったタスク（選んだ根と、一緒に移った子孫）
  moved_task_ids: number[];
  // 届かなくなったマイルストーンを外したタスク
  detached_milestone_task_ids: number[];
}

// GET /api/tasks のクエリパラメータ（バックエンドは配列を返す。並び替え・ページングはクライアント側で行う）
export interface TaskListParams {
  status_filter?: string;
  category_id?: number;
  milestone_id?: number;
  parent_task_id?: number;
  // このプロジェクトと子孫のもの（ADR-0024）/ 未分類のものだけ
  project_id?: number;
  unclassified?: boolean;
  // 担当者で絞る: me（自分）・none（担当なし）・利用者の id（ADR-0055）
  assignee?: string;
  // 終わりの無い繰り返しを予定済みに数える終わりの日（YYYY-MM-DD）。省くと今月末（ADR-0051）
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

// ── 認証（SSO）─────────────────────────────────────────────────────────────
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
  /** いちばん上のプロジェクトを作れるか（ADR-0065）。オフラインの控えには無いことがある */
  can_create_projects?: boolean;
}

export interface LogoutResult {
  end_session_url: string | null;
}

/** 色の名前（Google カレンダーの色名。`DEFAULT` は色の指定なし）。カテゴリの色の並びに使う。 */
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

/** 曜日（ドメインの `Weekday`。iCalendar の 2 文字）。 */
export type WeekdayCode = 'MO' | 'TU' | 'WE' | 'TH' | 'FR' | 'SA' | 'SU';

// タスクを消すとどうなるか（ADR-0046）。delete = 消す / archive = 確定した実績があるので消さずにアーカイブする
export interface TaskRemoval {
  task_id: number;
  title: string;
  action: 'delete' | 'archive';
  work_log_hours: number;
  archived: boolean;
}
