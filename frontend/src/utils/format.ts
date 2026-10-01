import type { Task, TaskStatus } from '../types';

// ユーザー設定のタイムゾーン。「今日」の判定に使う（未設定時はブラウザのローカル）。
// I18nProvider が設定読み込み時に反映する。
let activeTimeZone: string | null = null;

export const setActiveTimeZone = (tz: string | null): void => {
  activeTimeZone = tz;
};

// 設定タイムゾーンでの「今日」を、ローカル日付（時刻0時）として返す
export const todayDate = (): Date => {
  const now = new Date();
  if (activeTimeZone) {
    try {
      // en-CA ロケールは YYYY-MM-DD 形式を返す
      const ymd = new Intl.DateTimeFormat('en-CA', { timeZone: activeTimeZone }).format(now);
      const [y, m, d] = ymd.split('-').map(Number);
      return new Date(y, m - 1, d);
    } catch {
      // 不正なタイムゾーンはローカルにフォールバック
    }
  }
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
};

// APIの日付文字列をローカル日付として解釈する。
// `YYYY-MM-DD` を new Date() に渡すと UTC 深夜扱いになり、UTCより西のタイムゾーンで前日にずれるため、
// 日付のみの文字列は明示的にローカルの年月日で構築する。
export const parseDate = (dateStr: string | null | undefined): Date | null => {
  if (!dateStr) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(dateStr);
  return isNaN(d.getTime()) ? null : d;
};

// ── 日付の書き方（ADR-0020）─────────────────────────────────────────
// 文の中・表の中の日付は `M/D`（ゼロ埋めしない）。今年（利用者のタイムゾーンの「今日」の年）でなければ
// `YYYY/M/D`。期間は `M/D〜M/D` の形で、年は初日が今年でないときだけ初日に、末日の年が初日と違うときだけ末日に付ける。
// 例外（ここを通さない）: カレンダーの見出し（移植元の書式）・締めの画面の見出し（年を常に出す）・ガントの日の軸。

type DateInput = string | Date | null | undefined;

const toDate = (value: DateInput): Date | null => (value instanceof Date ? value : parseDate(value));

const monthDay = (d: Date): string => `${d.getMonth() + 1}/${d.getDate()}`;

/** 日付 1 つ。今年なら `9/30`、ほかの年なら `2025/9/30`。無ければ「—」。 */
export const formatDate = (value: DateInput): string => {
  const d = toDate(value);
  if (!d) return '—';
  return d.getFullYear() === todayDate().getFullYear() ? monthDay(d) : `${d.getFullYear()}/${monthDay(d)}`;
};

/**
 * 期間の両端。並べ方（`{from}〜{to}`）は翻訳の側（`common.dateRange` など）。
 * 初日は `formatDate` と同じ。末日は初日と同じ年なら年を省く（`2025/12/16〜12/31`、`2025/12/16〜2026/1/15`）。
 */
export const dateRangeParts = (from: DateInput, to: DateInput): { from: string; to: string } => {
  const a = toDate(from);
  const b = toDate(to);
  if (!b) return { from: formatDate(a), to: '—' };
  const sameYear = a ? a.getFullYear() === b.getFullYear() : b.getFullYear() === todayDate().getFullYear();
  return { from: formatDate(a), to: sameYear ? monthDay(b) : `${b.getFullYear()}/${monthDay(b)}` };
};

// ── 時間の書き方（ADR-0020）─────────────────────────────────────────
// 工数（見積・予定・残・実績の合計・確定実績・差）は時間の小数 `1.5h`（小数 2 桁まで、末尾の 0 は落とす）。
// 打刻を見て直す場面（今日・締め・タイマー）の量は時刻と並べて読むので `H:MM`（走っている経過と正確な長さは `H:MM:SS`）。
// 締めの表の 15 分丸め（`formatQuarterHours`）も `H:MM` の側。

/** 工数の時間（`1.5h`）。null は「—」。 */
export const formatHours = (hours: number | null | undefined): string =>
  hours == null ? '—' : `${Number(hours.toFixed(2))}h`;

/** 秒で来る工数を `1.5h` に。 */
export const formatSecondsAsHours = (seconds: number): string => formatHours(seconds / 3600);

/** 差（打刻 − 予定）。正なら「+」を付ける。 */
export const formatSignedSecondsAsHours = (seconds: number): string => {
  if (seconds === 0) return '±0h';
  return `${seconds > 0 ? '+' : '−'}${formatSecondsAsHours(Math.abs(seconds))}`;
};

/** 打刻の長さの `H:MM`（秒は切り捨て）。 */
export const formatClockDuration = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds / 60));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};

/** 打刻の正確な長さ・走っている経過の `H:MM:SS`（端数の秒は切り捨て、負は 0）。 */
export const formatExactDuration = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

export type PriorityBand = 'high' | 'mid' | 'low';

// priority 1〜5 を 高/中/低 の3段階に丸める
export const priorityBand = (p: number): PriorityBand => (p >= 4 ? 'high' : p === 3 ? 'mid' : 'low');

// 高/中/低 選択時に保存する priority 値
export const priorityBandValue: Record<PriorityBand, number> = { high: 5, mid: 3, low: 1 };

const dateOnly = (d: Date): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export const isOverdue = (task: Pick<Task, 'due_date' | 'status'>): boolean => {
  if (task.status === 'DONE' || task.status === 'CANCELLED') return false;
  const due = parseDate(task.due_date);
  if (!due) return false;
  return dateOnly(due) < todayDate();
};

export const isDueToday = (task: Pick<Task, 'due_date'>): boolean => {
  const due = parseDate(task.due_date);
  if (!due) return false;
  return dateOnly(due).getTime() === todayDate().getTime();
};

// 表示用ステータス（遅延を含む）
export type DisplayStatus = TaskStatus | 'LATE';

export const displayStatus = (task: Pick<Task, 'due_date' | 'status'>): DisplayStatus =>
  isOverdue(task) ? 'LATE' : task.status;

export const overdueDays = (task: Pick<Task, 'due_date'>): number => {
  const parsed = parseDate(task.due_date);
  if (!parsed) return 0;
  const due = dateOnly(parsed);
  const today = todayDate();
  return Math.max(0, Math.round((today.getTime() - due.getTime()) / 86400000));
};

export const getCurrentWeek = (): string => {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const dayOfYear = Math.floor((now.getTime() - new Date(now.getFullYear(), 0, 0).getTime()) / 86400000);
  const weekNum = Math.ceil((dayOfYear + jan4.getDay()) / 7);
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
};
