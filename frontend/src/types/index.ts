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
  // 予定済みの時間: 今日以降に始まる、このタスクに結んだ予定の回の合計（終日の回は数えない。ADR-0014）
  scheduled_hours: number | null;
  // 残のうち、まだ予定に取っていない分（残 − 予定済み、0 未満は 0）。残が決まらないときは null
  unscheduled_hours: number | null;
  priority_score: number;
  memo: string | null;
  parent_task_id: number | null;
  milestone_id: number | null;
  // 属するプロジェクト（null = 未分類）と、表示用の道筋（「親 / 子」）。子タスクは親と同じ（ADR-0024）
  project_id: number | null;
  project_path: string | null;
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
  // 属するプロジェクト（null = 未分類。どのタスクにも付けられる）
  project_id: number | null;
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
/**
 * 予定の通知（ADR-0021。移植元 `EventAlarm`）。基準は回の開始時刻。
 * `enabled` が false なら、どれを選んでいても知らせない。予定の `alarm` が null は通知を持たない。
 */
export interface EventAlarmData {
  enabled: boolean;
  notify_15_min: boolean;
  notify_5_min: boolean;
  notify_1_min: boolean;
  notify_at_start: boolean;
}

/** 予定の分類（ADR-0025）: 予定 / タスク（毎日の定常業務など。回ごとに済みを付ける）。 */
export type CalendarEventType = 'EVENT' | 'TASK';

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
  /** 予定の通知（繰り返しは系列のもの。移した回も同じ） */
  alarm: EventAlarmData | null;
  /** 予定の分類（ADR-0025）。TASK は回ごとに済みを付ける */
  event_type: CalendarEventType;
  /** タスクの分類の回に済みが付いている（予定の分類は常に false） */
  is_done: boolean;
  /** 予定が属するカレンダー（ADR-0027） */
  calendar_id: number | null;
  /** そのカレンダーの色。予定の `color_key` が DEFAULT ならこれで塗る */
  calendar_color_key: EventColorKey;
  /** プライベートのカレンダーの予定（ADR-0033）。見た目で分ける。省かれていれば仕事 */
  is_private?: boolean;
  /**
   * 取り込んだカレンダーの回（ADR-0037。`/calendars/imported-occurrences` を画面で回の形に直したもの）。
   * 読み取り専用: 動かす・直す・消す・済みは無い（`event_id` は 0）
   */
  is_imported?: boolean;
}

/** 終日の帯に出す休み（休みの層の日・曜日の休み。`calendar/daysOff.ts` が組み立てる）。 */
export interface CalendarHoliday {
  date: string; // YYYY-MM-DD
  name: string | null;
  /** 休みの理由（休みの層から作ったとき。塗りを分ける。ADR-0029）。WEEKLY は曜日の休み */
  reason?: DayOffReason | 'WEEKLY';
  /** 終日の帯の色（層の色） */
  color?: string;
  /** 控えめに出す帯（曜日の休み）。終日の欄でほかの日の予定を押し下げない */
  subtle?: boolean;
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
  /** 通知。null は通知を持たない */
  alarm: EventAlarmData | null;
  /** 分類（ADR-0025）。TASK は WBS のタスクに結ぶ */
  event_type: CalendarEventType;
  /** 属するカレンダー（ADR-0027） */
  calendar_id: number;
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

/** 予定のカレンダー（`/api/calendars`。ADR-0027）。表示するか（`is_visible`）はサーバーに覚える。 */
export type CalendarKind = 'EVENTS' | 'WORKWEEK' | 'DAYS_OFF' | 'IMPORTED';
/** 休みの日の一覧の層の理由（ADR-0029） */
export type DayOffReason = 'NATIONAL_HOLIDAY' | 'COMPANY' | 'PERSONAL';

export interface Calendar {
  id: number;
  /**
   * EVENTS = 予定を入れる / WORKWEEK = 営業日の層（曜日の規則）/ DAYS_OFF = 休みの日の一覧の層 /
   * IMPORTED = 外の iCalendar を読み込んだカレンダー（読み取り専用。ADR-0037）
   */
  kind: CalendarKind;
  name: string;
  /** DEFAULT は色の指定なし（予定は結んだタスクの色・標準の色） */
  color_key: EventColorKey;
  sort_order: number;
  /** 既定のカレンダー（消せない。消したカレンダーの予定の行き先） */
  is_default: boolean;
  /** カレンダーの画面に出す */
  is_visible: boolean;
  /** 営業日の層の稼働する曜日（ほかは null） */
  workdays: WeekdayCode[] | null;
  /** 休みの日の一覧の層の理由（ほかは null） */
  day_off_reason: DayOffReason | null;
  /** 営業日の判定で休みとして数える（休みの日の一覧の層） */
  counts_as_day_off: boolean;
  /**
   * 仕事 / プライベート（ADR-0033）。プライベートの予定は計画（予定した時間・締め）と打刻の既定のタスクに
   * 数えず、タスクを結べない。省かれていれば仕事とみなす
   */
  scope?: CalendarScope;
  /** 取り込んだカレンダーの読み込みの状態（ほかは null・省略） */
  imported?: CalendarImportStatus | null;
  created_at: string | null;
  updated_at: string | null;
}

export type CalendarScope = 'WORK' | 'PRIVATE';

/** 外の iCalendar を読めなかった理由（422 の `reason`・`last_error`。ADR-0037） */
export type FeedFailureReason =
  | 'invalid_url' | 'blocked_address' | 'unreachable' | 'not_found' | 'forbidden' | 'http_error'
  | 'too_large' | 'not_icalendar' | 'too_many_events' | 'subscription_unavailable';

/** 取り込んだカレンダーの読み込みの状態（ADR-0037）。URL そのものは返らない */
export interface CalendarImportStatus {
  source: 'FILE' | 'URL';
  /** 最後に読み込めた時刻（UTC） */
  imported_at: string;
  event_count: number;
  /** URL を購読している（定期的に読み込み直す） */
  is_subscribed: boolean;
  /** 購読している URL の手掛かり（ホスト名と末尾だけ） */
  url_hint: string | null;
  last_attempt_at: string | null;
  /** 最後の読み込みの失敗の理由（成功すれば null） */
  last_error: string | null;
}

/** 読み込む中身: ファイルの中身か、URL（購読するか） */
export type FeedSourceInput =
  | { type: 'FILE'; content: string }
  | { type: 'URL'; url: string; subscribe: boolean };

export interface CalendarImportSettings {
  /** URL を購読できる配備か（false でも 1 回だけの URL とファイルは使える） */
  subscription_available: boolean;
  refresh_interval_minutes: number;
}

/** 取り込んだ回（`GET /api/calendars/imported-occurrences`。閲覧者のタイムゾーンへ直したもの） */
export interface ImportedOccurrence {
  id: string;
  calendar_id: number;
  title: string;
  location: string | null;
  start: string;
  duration_minutes: number;
  date: string;
  start_time: string;
  is_all_day: boolean;
  calendar_color_key: EventColorKey;
}

/** ある日が休みである理由 1 つ（`GET /api/calendars/days-off`。ADR-0029）。 */
export interface DayOffMark {
  date: string;
  /** WEEKLY = 曜日の休み（営業日の層の曜日に当たらない） */
  reason: DayOffReason | 'WEEKLY';
  calendar_id: number | null;
  name: string | null;
  /** 営業日の判定で休みとして数える（false の層の日は塗るが営業日のまま） */
  counts_as_day_off: boolean;
}

/** 休みの日の一覧の層の 1 日。 */
export interface LayerDayOff {
  date: string;
  name: string | null;
}

/** 表示の組み合わせ（`/api/calendar-view-presets`）。当てると `calendar_ids` だけが表示になる。 */
export interface CalendarViewPreset {
  id: number;
  name: string;
  calendar_ids: number[];
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
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

// 「今日」の画面の要約（task #160、ADR-0015）。時刻は Z 付きの UTC
export interface TaskActual {
  /** 未割当の打刻は null */
  task_id: number | null;
  task_title: string | null;
  seconds: number;
}

export interface TodaySummary {
  /** 利用者のタイムゾーンでの今日（YYYY-MM-DD）。予定の回はこの日を問う */
  date: string;
  time_zone: string;
  /** 今日の区切り（[開始, 終了)） */
  day_start: string;
  day_end: string;
  server_now: string;
  running: TimeEntry | null;
  /** 今日に掛かる打刻（日をまたぐものはそのまま。切るのは画面） */
  entries: TimeEntry[];
  /** 今日の分だけの合計（走っている打刻は server_now まで） */
  total_seconds: number;
  actuals: TaskActual[];
  /** 今日やるべきタスクのうち、まだ予定を取っていないもの（優先度の点の高い順） */
  tasks_to_schedule: Task[];
}

// ── 締め（task #161 / ADR-0012）。仕様の正は /api/docs ──────────────────

export interface ClosingPeriodRange {
  /** 初日（利用者のタイムゾーンの日付。1 日か 16 日） */
  first_day: string;
  /** 末日（含む） */
  last_day: string;
}

export interface ClosingPeriod extends ClosingPeriodRange {
  status: 'open' | 'closed';
  /** 区切りに使ったタイムゾーン（確定済みなら確定したときの値） */
  time_zone: string;
  /** 区切りの始まりの瞬間（含む） */
  starts_at: string;
  /** 区切りの終わりの瞬間（含まない） */
  ends_at: string;
  closed_at: string | null;
}

export interface DailyTaskTotal {
  work_date: string;
  task_id: number | null;
  task_title: string | null;
  /** 丸めない長さ（秒）。日をまたぐ打刻は 0:00 で割ってある */
  seconds: number;
  /** タスクのいまのプロジェクト（未割当・消えたタスク・未分類は null。task #189） */
  project_id?: number | null;
}

export interface ClosingOverlap {
  /** 重なっている 2 本（始まりの早い順） */
  entry_ids: [number, number];
  seconds: number;
}

export interface ClosingFindings {
  long_running_entry_ids: number[];
  overlaps: ClosingOverlap[];
  unassigned_entry_ids: number[];
  missed_occurrences: CalendarOccurrence[];
  count: number;
}

export interface ClosingBoard {
  period: ClosingPeriod;
  entries: TimeEntry[];
  occurrences: CalendarOccurrence[];
  daily_totals: DailyTaskTotal[];
  findings: ClosingFindings;
}

export interface PendingClosings {
  has_pending: boolean;
  current: ClosingPeriodRange;
  pending: ClosingPeriodRange[];
}
