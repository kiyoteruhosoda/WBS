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
  remaining_hours: number | null;
  actual_hours: number;
  progress_percent: number;
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
  progress_percent: number;
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
  start_time: string | null; // HH:MM
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
  /** 回の操作（移動・取り消しなど）で `expected_version` に渡す版 */
  event_version: number;
  title: string;
  /** 開始の UTC 瞬間（Z 付き ISO 8601） */
  start: string;
  duration_minutes: number;
  /** 閲覧者のローカル日（YYYY-MM-DD）。終日の回はこの日に置く */
  date: string;
  /** 閲覧者のローカル時刻（HH:MM） */
  start_time: string;
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

/** 曜日（ドメインの `Weekday`。iCalendar の 2 文字）。 */
export type WeekdayCode = 'MO' | 'TU' | 'WE' | 'TH' | 'FR' | 'SA' | 'SU';

export interface MonthlyRuleData {
  kind: 'DAY_OF_MONTH' | 'NTH_WEEKDAY' | 'LAST_DAY';
  day?: number | null;
  /** 1〜5、-1 は最終 */
  week_index?: number | null;
  weekday?: WeekdayCode | null;
}

export interface YearlyRuleData {
  kind: 'DAY_OF_MONTH' | 'NTH_WEEKDAY';
  month: number;
  day?: number | null;
  week_index?: number | null;
  weekday?: WeekdayCode | null;
}

/** 営業日シフト（`shift_amount` が負なら前倒し）。 */
export interface AdjustmentRuleData {
  condition: 'HOLIDAY' | 'ALWAYS';
  shift_unit: 'BUSINESS_DAY' | 'CALENDAR_DAY';
  shift_amount: number;
  calendar_id: number | null;
  action: 'SHIFT' | 'CANCEL';
}

/** 繰り返しの規則（API の入出力と表の JSON で同じ形。`src/application/recurrence_rule_mapping.py`）。 */
export interface RecurrenceRuleData {
  type: 'WEEKLY' | 'MONTHLY' | 'YEARLY';
  interval: number;
  /** null は終了日なし */
  end_date: string | null;
  weekly: { weekdays: WeekdayCode[] } | null;
  monthly: MonthlyRuleData | null;
  yearly: YearlyRuleData | null;
  adjustment: AdjustmentRuleData | null;
}

/** 予定 1 件（`GET /api/calendar/events/{id}` の応答）。 */
export interface CalendarEvent {
  id: number;
  kind: 'SINGLE' | 'RECURRING';
  title: string;
  /** 予定のタイムゾーン（IANA 名）。繰り返しの鍵はこのゾーンの壁時計 */
  time_zone: string;
  /** 単発の開始・繰り返しの先頭の回の UTC 瞬間 */
  start: string;
  duration_minutes: number;
  recurrence: RecurrenceRuleData | null;
  location: string | null;
  description: string | null;
  color_key: EventColorKey;
  task_id: number | null;
  exceptions: { occurrence: OccurrenceSeriesKey; type: string }[];
  moves: {
    occurrence: OccurrenceSeriesKey;
    new_date: string;
    new_start_time: string | null;
    new_duration_minutes: number | null;
    title: string | null;
    location: string | null;
  }[];
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

/** 営業日カレンダー（`/api/business-calendars`）。 */
export interface BusinessCalendar {
  id: number;
  name: string;
  time_zone: string;
  workdays: WeekdayCode[];
  shift_on_holidays_only: boolean;
  is_enabled: boolean;
  holidays: CalendarHoliday[];
  created_at: string | null;
  updated_at: string | null;
}

// 打刻（task #154）。時刻は Z 付きの UTC
export type TimeEntrySource = 'timer' | 'manual' | 'split';

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
