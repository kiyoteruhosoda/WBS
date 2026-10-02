# ADR-0009: 予定の表・リポジトリ・API（task #156 第 2 段）

- 状態: 承認
- 日付: 2026-10-01
- 関連: task #156（移植）・ADR-0007（第 1 段: ドメインとユースケース）・ADR-0008（打刻）

## 背景

ADR-0007 でドメインとユースケースまでを写した。この段で表（Alembic の `0003`）とリポジトリの実装、
API を足す。ADR-0007 から持ち越した判断は 4 つ: リポジトリの `save` で確定しないこと、期間の索引の
番号の数え方、例外・移動の持ち方、祝日データの入れ方。あわせて、打刻（ADR-0008）の
「Start の既定はいまの予定のタスク」の口（`ScheduledTaskLookup`）を本物に差し替える。

## 決定

### 表

| 表 | 中身 |
|---|---|
| `calendar_events` | 予定 1 件 1 行。`user_id`（利用者で分ける）・`kind`（`SINGLE` / `RECURRING`）・`start_utc`（単発の開始・繰り返しのアンカー、naive な UTC）・`duration_minutes`・`recurrence_rule`（JSON の文字列）・`task_id`（任意、`tasks` を指す）・`span_start_day` / `span_end_day`・`version` |
| `calendar_event_exceptions` | 繰り返しの 1 回への例外（飛ばす・古いデータの上書き）。回の鍵（`occurrence_date` ＋ `occurrence_time`）で一意 |
| `calendar_event_moves` | 繰り返しの 1 回を移した先（予定のタイムゾーンの壁時計）。回の鍵で一意 |
| `business_calendars` | 営業日カレンダー。`user_id`・`workdays`（`MO,TU,...`）・`shift_on_holidays_only`・`is_enabled` |
| `business_calendar_holidays` | 祝日。（カレンダー, 日）で一意 |

- **例外と移動は子表にした。繰り返しの規則は JSON の列にした。** 例外・移動は回の鍵で指される
  「1 回ごとの記録」で、同じ回に 2 つあってはならない（DB の一意制約で守れる）。数も年に数十件まで
  増えうる。規則は値オブジェクト 1 つで、種類ごとに形が違い（毎週・毎月 3 種・毎年 2 種・営業日シフト）、
  列に開くと NULL だらけになるうえ、検索に使わない。JSON の形は `src/application/recurrence_rule_mapping.py`
  が唯一の出所で、API の入出力と同じ形（移植元 docs/storage.md §5 の「直列化の出所を 1 つに」と同じ）。
  ⚠ キーを変えるときはデータ移行を伴う。
- **期間の索引の番号は `date.toordinal()`**（`CalendarEvent.indexed_day_span()` の値、余白 ±31 日込み）。
  移植元の `DayNumber` より 1 大きいが、比べる相手も同じ数え方なので揃っていればよい。
  索引は `(user_id, span_start_day, span_end_day)`。
- `calendar_events` と `business_calendars` は SQLite の `AUTOINCREMENT` で、**消した id を使い回さない**
  （使い回すと、古い画面が同じ id・同じ版 1 の別の予定を直してしまいうる）。
- 時刻は `DATETIME`（naive な UTC）・壁時計の時刻は `TIME`・列挙は文字列（ネイティブ ENUM にしない）。

### リポジトリ

- **`save` / `delete` は flush までで commit しない。** 確定はユースケースの最後に `UnitOfWork.commit()`
  で 1 度（API では、このリクエストの `Session`）。「この回だけ」「以降」は 2 件を書くので、途中で
  落ちたら両方とも残らない。
- **楽観ロックは表でも効かせる。** 書く前に `UPDATE calendar_events SET version = <新しい版>
  WHERE id = ? AND version = <この接続が読んだ版>` を出し、1 行に当たらなければ `ConflictError`（409）。
  消すときも同じ確かめをしてから消す。ユースケースの `ensure_version(expected_version)`（画面が読んだ版との
  比較）を抜けても、読んでから書くまでの間に別のリクエストが書いていれば止まる。当たった時点で書き込みの
  鍵を握るので、確定までの間に割り込まれない。「読んだ版」はリポジトリが読んだときに覚えておく。
  ⚠ ORM の `version_id_col` に任せなかった: identity map は弱参照で、リポジトリが行の写しを集約へ移した後に
  捨てられると、書く直前に読み直された（新しい版の）写しで比べてしまい、食い違いを見逃した。
- 子表は保存のたびに集約の今の中身で置き換える。⚠ 同じ回の鍵を消して入れ直すと、ORM は INSERT を
  DELETE より先に出すので一意制約に当たる。先に消して flush してから入れる。

### API

- 回: `GET /api/calendar/occurrences?from=&to=&time_zone=`。閲覧者のタイムゾーン（省くと利用者の設定）へ
  投影済みの回を返す。`start`（Z 付きの UTC 瞬間）・`duration_minutes`・`date` / `start_time`（閲覧者の
  壁時計）・`is_all_day`・`color_key`・`location`・`task_id`・`is_recurring`・`is_moved`・`is_overridden`・
  `series_key`（繰り返しの元の鍵。回の操作でそのまま返す）・`event_version`（回の操作の `expected_version`）・
  `id`（単発は予定の id、繰り返しは `<event_id>:<日>T<時刻>`）。終日の回は浮いた日のまま `date` に置く
  （`start` は閲覧者のその日の 0:00）。
- 予定: `/api/calendar/events`（期間の一覧・1 件・作る・直す・消す）。作るときは `recurrence` が
  あれば繰り返し。繰り返しの編集は 3 つに分けた: すべて（`PUT .../series`）・この回以降
  （`POST .../occurrences/following`、新しい系列を 201 で返す）・この回だけ（`POST .../occurrences/split`、
  新しい単発を 201 で返す）。回の操作は `POST .../occurrences/{skip,restore,move,cancel-move,delete-following}`。
- 営業日カレンダー: `/api/business-calendars`（CRUD）と祝日（1 日ずつ・まとめて・日本の祝日を年ごとに）。
  画面の強調表示には `GET /api/calendar/holidays?from=&to=`（有効なカレンダーの祝日を集めたもの）。
- 入力の瞬間は分の単位まで（秒があれば 422）。回の鍵が壁時計の時刻なので、秒を持たせない。
- 他人の予定・カレンダーは 404（ADR-0005 と同じく、在ることを教えない）。版の食い違いは 409。
  仕様の正は `/api/docs`（OpenAPI）。

### 祝日データ

**日本の祝日は暦から出す**（`src/domain/services/japanese_national_holidays.py`）。
`POST /api/business-calendars/{id}/holidays/japan {"year": 2027}` でその年の祝日・振替休日・国民の休日を
足す。年ごとの一括登録（`.../holidays/bulk`）と 1 日ずつの追加・削除も持つ。

- 規則で決まるもの（固定日・ハッピーマンデー・振替休日・国民の休日）は規則で、法律でその年だけ
  動かした日（2019 年の即位・2020/2021 年の五輪）は表で持つ。扱う年は 2007〜2099。
- 春分・秋分は毎年 2 月の官報で翌年の日が決まる。ここでは 1980〜2099 年に当てはまる近似式で出す。
  公示と食い違ったとき・法律が変わったときは、その日を手で直す（消して足す）。

## 理由

- **祝日をライブラリにしなかった**: `holidays` / `jpholiday` を足すと `uv.lock` が変わる（この段では
  手元で依存を入れ直さない決まり）。日本の祝日の規則は 1 ファイルに収まり、試験で 2019・2020・2021・2026 年の
  公表済みの一覧と突き合わせられる。実行時に外（内閣府の CSV）へ取りに行く形は、取れないときに
  予定が出せなくなるので採らなかった。
- **一括登録 API だけにしなかった**: 毎年人が一覧を貼る手間が残る。暦から出す口があれば、画面は
  「年を選んで入れる」1 操作で済む。会社の休み（年末年始など）は一括登録で足す。
- **編集範囲ごとに口を分けた**: 1 つの口に `scope`（この回／以降／すべて）を持たせると、範囲ごとに
  必須の欄が違い（以降は規則が要る、この回は要らない）、OpenAPI で形を示せない。

## 影響

- 打刻の Start の既定（ADR-0008）がつながった。`CalendarEventUseCases.task_scheduled_at(user_id, at)` が
  `ScheduledTaskLookup` を満たし、`get_time_entry_use_cases` で渡している。重なっていたら後に始まった回、
  始まりが 1 週間より前の回（長い予定）は見ない。結んだタスクが消えている・他人のものなら飛ばす。
- 営業日カレンダーを消しても、それを参照する繰り返しは消えない（シフトせずに名目の日に出る。移植元と同じ）。
  `calendar_id` は規則の JSON の中にあり外部キーは張っていない。
- デスクトップ版の JSON の取り込み（#155 の表の最後の行）は、この表へ写す口として別に作る。

> 追記（2026-10-02）: 営業日カレンダーの表（`business_calendars`・`business_calendar_holidays`）と API
> （`/api/business-calendars`・`GET /api/calendar/holidays`）は ADR-0032 で畳んだ（休みの 4 層に一本化。移行 `0013`）。
