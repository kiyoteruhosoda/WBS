# ADR-0007: NolumiaScheduler の予定のドメインを Python へ写す（第 1 段: ドメインとユースケース）

- 状態: 承認
- 日付: 2026-10-01
- 関連: task #156（移植）・#155（範囲の決定）

## 背景

デスクトップ版の予定表 NolumiaScheduler（C#/.NET）のドメインを WBS へ持ってくる。範囲は #155 で
決まっている（単発・繰り返し・例外・この回だけ／以降の編集・営業日カレンダー・色・場所。
アラーム・公開/非公開・予定種別は持ってこない）。加えて予定に WBS のタスク（`task_id`、任意）を
持たせる。一次資料は移植元の `docs/time-model.md`（§8 スキーマ・§10 仕様）。

表とリポジトリの実装・API は、並行している Alembic 導入の PR が入ってから足す。この段では
ドメインとアプリケーション層までを、インメモリのリポジトリで試験する。

## 決定

**時刻モデルは移植元のまま写す。** 単発は「開始の UTC 瞬間 ＋ 長さ（分）」、繰り返しは
「先頭の回の UTC 瞬間（アンカー）＋ 長さ ＋ 規則」。終了は持たない。終日という概念は持たない
（ローカル 0:00 ＋ 1440 分）。各回の瞬間はアンカーからの整数日の足し算で決め、tz データベースを
引き直さない。タイムゾーンは IANA 名（`zoneinfo`）で、「どのローカル日か」を決めるメタデータ。

置き場所（WBS の 4 層に合わせた）:

| 移植元 | こちら |
|---|---|
| `Aggregates/CalendarEvent`・`Entities/EventException`・`EventMove` | `src/domain/entities/calendar_event.py` |
| `Aggregates/BusinessCalendar`・`Holiday` | `src/domain/entities/business_calendar.py` |
| `RecurrenceRule`・`WeeklyRule`・`MonthlyRule` 3 種・`YearlyRule` 2 種・`AdjustmentRule` | `src/domain/value_objects/recurrence.py` |
| `SingleEventSchedule`・`RecurringEventSchedule`・`OccurrenceLocalKey`・`EventOccurrence` | `src/domain/value_objects/event_schedule.py` |
| `LocalSchedulePoint` | `src/domain/value_objects/local_schedule_point.py` |
| `TimeZoneId`・`EventColorKey` | `time_zone.py`・`event_color.py` |
| `OccurrenceExpander`・`BusinessDayShiftService`・`OccurrenceDisplayProjection` | `src/domain/services/` |
| `ICalendarEventRepository`・`IBusinessCalendarRepository` | `src/domain/repositories/` |
| `CalendarEventApplicationService`・`BusinessCalendarApplicationService` | `src/application/use_cases/calendar_event_use_cases.py`・`business_calendar_use_cases.py` |

### 名前の付け方

- C# の `I` 接頭辞・`Service` 接尾辞は落とし、WBS の既存の形（`〇〇Repository`・`〇〇UseCases`）に揃えた。
- `OccurrenceLocalKey` → **`OccurrenceKey`**。中身（予定のタイムゾーンでの候補日 ＋ 系列の開始時刻）は同じ。
- `LocalDateValue` / `LocalTimeValue` / `EventId` / `EventTitle` / `Location` / `Description` / `VersionNo` /
  `BusinessCalendarId` は持たず、`date` / `time` / `int` / `str` にした。検査（日付の範囲・空の題名・
  版が 1 以上）は使う側（集約）で行う。ID は WBS の他の表と同じ採番の整数（移植元は GUID の文字列）。
- 列挙は `StrEnum` で、値は大文字の綴り（`WEEKLY`・`HOLIDAY`・`BUSINESS_DAY`・`SKIP` …）。曜日は
  iCalendar の略号（`MO`〜`SU`）で、移植元の JSON と同じ綴り。DB へはこの文字列で入れる
  （ネイティブ ENUM にしない）。
- `AdjustmentRule(AdjustmentDirection)` の互換用コンストラクタは
  `previous_business_day_on_holiday()` / `next_business_day_on_holiday()` にした。
- ドメインサービスの判定（`Cancels` / `Shifts`）は `AdjustmentRule` から `BusinessDayShiftService` へ寄せた
  （値オブジェクトが集約 `BusinessCalendar` を引数に取らないように）。

### 移植元から変えたこと

- **瞬間は naive な UTC**（`src/shared/clock.utcnow()` と保存値の形）。aware を渡されたら UTC へ直す。
  作成・更新の時刻はユースケースに渡す `now`（既定 `utcnow`）で付ける（移植元の `TimeProvider`）。
- **ユースケースの入力は UTC の瞬間 ＋ 長さ。** 移植元のコマンドは画面の「開始〜終了・終日」を
  受けて長さへ直していた（`ResolveTimes`）。その変換は画面の仕事にした。回の移動は UTC の瞬間を
  受け、予定のタイムゾーンの壁時計に直して `EventMove` に持つ（保存形は移植元と同じ）。
  「すべて」の編集はアンカーを省くと今のアンカーのまま（移植元の `NewStartDate` 省略に当たる）。
- **利用者で分ける。** 予定と営業日カレンダーは `user_id` を持ち、どの操作も持ち主を確かめる
  （他人のものは `NotFoundError`）。繰り返しが参照する営業日カレンダーと、予定に結ぶタスクも
  同じ利用者のものに限る。
- **楽観ロックを入口で使えるようにした。** 移植元は `Version` を進めるだけで比べていなかった。
  コマンドに `expected_version` を持たせ、違えば `ConflictError`（409 にする想定）。
- **確定はユースケースの最後に 1 度**（`UnitOfWork.commit()`。SQLAlchemy の `Session` がそのまま満たす）。
  この回を切り出す・以降を分けるは 2 件を書くので、⚠ **表の実装ではリポジトリの `save` の中で
  commit しないこと。**
- 「飛ばしを戻す」（`restore_occurrence`）を足した。ドメインには移植元にもあった
  （`RemoveOccurrenceException`）が、アプリケーション層の口が無かった。
- `list_occurrences`（期間の回を、閲覧者のタイムゾーンへ投影して返す）を足した。移植元では画面の
  ViewModel がしていた「前後 1 日広げて展開 → 投影 → 閲覧者の日で絞る」を、API から使えるよう
  アプリケーション層へ下ろした。
- 展開の結果は日付・開始時刻の順に並べて返す（移植元は候補の生成順で、週の中の曜日の並びは
  規則の書き順だった）。`WeeklyRule` の曜日は重複を落として月曜始まりに並べ直す。
- 規則の検査（間隔・週インデックス・下位規則の有無など）で投げるのは、`ArgumentException` 系ではなく
  WBS の `ValidationError`。
- 期間の索引の日の通し番号は `date.toordinal()`（移植元の `DateOnly.DayNumber` より 1 大きい）。
  表の列に入れる値はこちらの番号で揃える。
- DST の重なり（2 度ある時刻）は `fold=0`（先の方）で解く。.NET は標準時側を取るので、DST のある
  ゾーンの重なりの 1 時間だけ結果が違いうる（JST には無い）。

### 落としたもの

- **アラーム**（`EventAlarm`・`AlarmApplicationService`・`AlarmScheduleCalculator`）・
  **公開/非公開**（`Visibility`）・**予定種別**（`EventType`）——#155 の決定。上書き・移動・回からも
  その欄を落とした。
- 期限切れの判定と掃除（`EventExpirationService`・`PurgeExpiredEventsService`）。デスクトップ版の
  保存先を軽くするためのもので、Web 版で消す決まりはまだ無い。あわせて壁時計で終わりを出す
  `LocalSchedulePoint.EndInstant` も持ってきていない（使うのはこの 2 つだけだった）。
- 変更の通知（`ICalendarEventChanges`）・アプリの設定（`IAppSettingsRepository`）・画面の既定値
  （`EventEditDefaults`）。
- 「上書き」例外（`ExceptionType.OVERRIDE`）は **新しくは作らない**が、展開では読む。デスクトップ版の
  JSON の取り込み（#155 の表の最後の行）で古いデータに残っているため。

## 理由

- 時刻モデルを変えない: 移植元で詰めた判断（instant 優先・整数日の足し算・終日を概念にしない）は
  Web 版でもそのまま成り立ち、デスクトップ版のデータを取り込むときに変換が要らない。
- 値オブジェクトを薄くした: `date` / `time` は不変で比較もでき、包む利点が小さい。包むと表との
  変換が増える。
- 試験は移植元の CoreTests（`RecurringMatrixTests`・`OccurrenceExpanderTests`・`CalendarEventTests`・
  `CalendarEventSpanTests`・`BusinessCalendarTests`・`OccurrenceDisplayProjectionTests`・
  `LocalSchedulePointTests`・`ValueObjectTests`・`CalendarEventApplicationServiceTests`・
  `BusinessCalendarServiceTests` の画面に依らない分）を 1 本ずつ写した。`NolumiaSchedulerTest/Inputs/Json`
  の入力例には期待値が無いので、§9 の変換規則で今の形へ組み立て、期待値は暦から出した。

## 影響

- 次の段（表・リポジトリ・API）で決めること: `calendar_events`（`span_start_day` / `span_end_day` に
  `indexed_day_span()` を入れる。例外と移動は子表か JSON 列か）・`business_calendars`（祝日は子表）。
  どちらも `user_id` を持つ。祝日データの入れ方（#155）もそこで決める。
- 予定から作業の記録へつなぐ S6 は、展開した回の `task_id` を使える。
