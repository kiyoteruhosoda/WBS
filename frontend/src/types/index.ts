export type TaskStatus = 'TODO' | 'DOING' | 'WAITING' | 'DONE' | 'CANCELLED';
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
  completed_at: string | null;
  deleted_at: string | null;
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

export interface DashboardToday {
  buckets: {
    OVERDUE: Task[];
    TODAY: Task[];
    TOMORROW: Task[];
    DOING: Task[];
  };
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
  progress_percent: number | null;
  dependencies: number[];
}

export interface WeeklyReview {
  completed_count: number;
  new_count: number;
  overdue_count: number;
  total_hours: number;
  hours_by_category: { category_name: string; hours: number }[];
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

// GET /api/tasks のクエリパラメータ（バックエンドは配列を返す。並び替え・ページングはクライアント側で行う）
export interface TaskListParams {
  status_filter?: string;
  category_id?: number;
  milestone_id?: number;
  parent_task_id?: number;
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
}

export interface LogoutResult {
  end_session_url: string | null;
}

// ── 予定（task #156 のドメイン。API は Alembic の後に足す） ─────────────────────

/** 予定の色（ドメインの `EventColorKey`。Google カレンダーの色名。`DEFAULT` は色の指定なし）。 */
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

/** 繰り返しの元の鍵（予定のタイムゾーンでの候補日・系列の開始時刻）。この回だけの移動・飛ばしで回を指す。 */
export interface OccurrenceSeriesKey {
  date: string; // YYYY-MM-DD
  start_time: string; // HH:MM
}

/**
 * 予定の 1 回（API の応答の 1 件）。
 *
 * ドメインの `list_occurrences(viewer_time_zone=...)` が返す `EventOccurrence`（閲覧者のタイムゾーンへ
 * 投影済み）を、そのまま JSON にした形。画面はこれを受けて、閲覧者のローカル 0:00 で日ごとに割る。
 * - 時刻付きの回は `start`（UTC の瞬間）＋ `duration_minutes` で置く（終了は持たない。time-model §1）。
 * - 終日（ローカル 0:00 ＋ 1440 分）は「浮いた日」で、`date` の日にそのまま置く（ゾーンでずらさない）。
 */
export interface CalendarOccurrence {
  /** 回の識別子（React の key・選択に使う）。`event_id` と系列の鍵から作る */
  id: string;
  event_id: number;
  title: string;
  /** 開始の UTC 瞬間（Z 付き ISO 8601） */
  start: string;
  duration_minutes: number;
  /** 閲覧者のローカル日（YYYY-MM-DD）。終日の回はこの日に置く */
  date: string;
  /** 終日（0:00 開始 ＋ 1440 分）。ドメインの `is_all_day` */
  is_all_day: boolean;
  color_key: EventColorKey;
  location: string | null;
  /** 結んだ WBS のタスク（任意） */
  task_id: number | null;
  /** 繰り返しの予定の回か */
  is_recurring: boolean;
  /** この回だけ動かした（振替） */
  is_moved: boolean;
  /** この回だけ中身を変えた（古いデータの上書き例外） */
  is_overridden: boolean;
  series_key: OccurrenceSeriesKey | null;
}

/** 祝日・休日（有効な営業日カレンダーから集めたもの）。 */
export interface CalendarHoliday {
  date: string; // YYYY-MM-DD
  name: string | null;
}

// 打刻（task #154）。時刻は Z 付きの UTC
export type TimeEntrySource = 'timer' | 'manual' | 'split' | 'schedule';

export interface TimeEntry {
  id: number;
  user_id: number;
  task_id: number | null;
  task_title: string | null;
  started_at: string;
  ended_at: string | null;
  memo: string | null;
  source: TimeEntrySource;
  is_running: boolean;
  duration_seconds: number;
  is_long_running: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface CurrentTimeEntry {
  entry: TimeEntry | null;
  server_now: string;
}

export interface StartTimeEntryResult {
  started: TimeEntry;
  stopped: TimeEntry | null;
  server_now: string;
}

export interface StopTimeEntryResult {
  stopped: TimeEntry | null;
  server_now: string;
}
