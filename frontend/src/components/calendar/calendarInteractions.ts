import type { CalendarOccurrence } from '../../types';
import type { OccurrenceTiming } from '../../calendar/weekGestures';
import type { CalendarDeadline } from '../../calendar/taskDeadlines';

/** 空き枠のドラッグで選んだ範囲（閲覧者のローカル日と、その日の 0:00 からの分。終わりは排他）。 */
export interface CreateRange {
  date: string;
  startMinute: number;
  endMinute: number;
}

/**
 * タスクの一覧から時間グリッドへ引いている途中の行き先（task #159）。週表示にゴーストで描く。
 * 日と分は閲覧者のローカル。
 */
export interface TaskDropPreview {
  date: string;
  startMinute: number;
  durationMinutes: number;
  title: string;
}

/** 回の時刻 ＋ その開始の UTC 瞬間（API の `start` にそのまま渡せる Z 付き ISO 8601）。 */
export interface OccurrenceSchedule extends OccurrenceTiming {
  start: string;
}

/**
 * 週表示のドラッグで回の時刻を変えた意図（移植元 `EventDragCompleted` / `EventResizeCompleted`）。
 * - `move`: 長さはそのまま、開始（日をまたいでよい）を変える
 * - `resize`: 上端なら開始、下端なら終わりを変える（長さが変わる）
 *
 * `scope` が `occurrence` のとき（繰り返しの回）は「この回だけ移動」として残す。系列は変えない。
 * 元に戻すときは `occurrence.is_moved` を見る: 動かす前に振替でなかった回は、振替を消して系列の
 * 位置へ戻す（`before` の時刻へ振り替え直すのではない。移植元 `HadMoveBeforeDrag`）。
 */
export interface OccurrenceReschedule {
  kind: 'move' | 'resize';
  /** 動かす前の回（API の応答のまま） */
  occurrence: CalendarOccurrence;
  scope: 'event' | 'occurrence';
  before: OccurrenceSchedule;
  after: OccurrenceSchedule;
}

/**
 * カレンダーの操作の口。どれも省ける（省いたボタンは出さない。ドラッグの口を省けばその操作はしない）。
 */
export interface CalendarInteractions {
  /** 作成の意図（空き枠のタップ・選んだ日の「予定を作る」）。タップは :00 / :30 に丸める */
  onCreateEvent?: (date: string, startMinute?: number) => void;
  onEditOccurrence?: (occurrence: CalendarOccurrence) => void;
  onDeleteOccurrence?: (occurrence: CalendarOccurrence) => void;
  /** 選んだ日の一覧で、タスク・マイルストーンの期限を押した */
  onOpenDeadline?: (deadline: CalendarDeadline) => void;
  /** 週のグリッドの空き枠をドラッグして範囲を選んだ（30 分単位） */
  onCreateRange?: (range: CreateRange) => void;
  /** 週のグリッドで回を動かした・伸ばし縮めた（15 分単位・最短 15 分） */
  onRescheduleOccurrence?: (change: OccurrenceReschedule) => void;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
}
