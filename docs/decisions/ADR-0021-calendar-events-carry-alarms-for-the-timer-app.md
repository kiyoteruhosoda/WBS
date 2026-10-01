# ADR-0021: 予定に通知（アラーム）を戻し、打刻アプリが Bearer で「この先の通知」を読む

- 状態: 承認
- 日付: 2026-10-01
- 関連: task #183（この段）・#182（目的）、ADR-0007「落としたもの」（**その一部を覆す**）・ADR-0009（予定の表と API）・
  ADR-0018（打刻アプリの Bearer。**口を 1 つ足す**）、移植元 NolumiaScheduler の
  `Domain/ValueObjects/EventAlarm.cs`・`Application/Services/AlarmScheduleCalculator.cs`・
  `AlarmApplicationService.cs`・`docs/time-model.md` §10-1・§11

## 背景

NolumiaScheduler の予定には通知（`EventAlarm`: 通知する・15 分前・5 分前・1 分前・開始時刻）があった。WBS へ
移したときは #155 の決定で落とした（ADR-0007「落としたもの」）。**2026-10-01 に持ち主が戻すよう依頼した**
（「予定通知も入れて 元のスケジューラ参照 アプリ通知」、#182）。通知を出すのはブラウザではなく打刻アプリ
（wbstimer、Android）で、FCM は使わない。アプリが WBS から「この先の通知」を取り、端末で時刻どおりに出す。

この ADR は **ADR-0007 の「落としたもの」のうちアラームの行を覆す**（公開/非公開・予定種別・期限切れの掃除は
落としたまま）。

## 決定

### 1. ドメイン: 予定が通知の設定を 1 つ持つ（移植元のまま）

- 値オブジェクト `EventAlarm`（`src/domain/value_objects/event_alarm.py`）: `is_enabled`・`notify_15_min`・
  `notify_5_min`・`notify_1_min`・`notify_at_start`。知らせる時刻の並びは `ALARM_OFFSETS_MINUTES = (15, 5, 1, 0)`
  （0 は開始時刻ちょうど）。既定は `EventAlarm.default()` = 5 つとも true（移植元 `EventAlarm.Default`）。
- `CalendarEvent.alarm: EventAlarm | None`。**`None` は通知を持たない**。`is_enabled=False` も知らせない
  （選んだ時刻は残す。移植元と同じ）。どちらも「知らせない」で、API でも区別して返す。
- **基準は回の開始時刻**（長さ・終了の変更の影響を受けない。time-model §10-1・§11）。
- **繰り返しは系列で 1 つ。** 移した回（`EventMove`）は**移した先の開始時刻**で、系列の設定のまま知らせる。
  飛ばした回は知らせない。移植元にあった「回ごとに黙らせる」（`EventException.AlarmEnabled`）は持たない
  （作る口が無い上書き例外の欄で、WBS は上書き例外を新しく作らない。ADR-0007）。古い上書き例外の回も系列の設定で知らせる。
- **終日の回（ローカル 0:00 ＋ 1440 分）は知らせない**（意味のある開始時刻が無い。移植元と同じ）。
- 「この回だけ」（切り出した単発）・「この回以降」（新しい系列）は、送らなければ**元の系列の通知を引き継ぐ**
  （移植元はコマンドに画面の値を載せていた。画面が系列の値を入れて送るのと同じ結果になる）。

### 2. 表: `calendar_events` に 5 列（移行 `0006`）

| 列 | 型 | 意味 |
|---|---|---|
| `alarm_enabled` | `BOOLEAN NULL` | NULL = 通知を持たない。true / false = 通知する / 止めた |
| `alarm_15_min`・`alarm_5_min`・`alarm_1_min`・`alarm_at_start` | `BOOLEAN NOT NULL DEFAULT false` | 選んだ時刻。通知を持たない行は false |

**既存の予定は通知なし**（`alarm_enabled` は NULL）。downgrade は 5 列を落とす。

### 3. 予定の API の `alarm`

形（`EventAlarmSchema`）:

```json
{"enabled": true, "notify_15_min": true, "notify_5_min": true, "notify_1_min": true, "notify_at_start": true}
```

| 口 | 省いた | `null` | オブジェクト |
|---|---|---|---|
| `POST /api/calendar/events`（作る） | **既定（5 つとも true）** | 通知なし | その設定 |
| `PUT /api/calendar/events/{id}`・`PUT .../series` | 今のまま | 通知を外す | その設定 |
| `POST .../occurrences/split`・`.../following` | 元の系列のもの | 通知なし | その設定 |

- **新しい予定の既定はアプリケーション層（`CalendarEventUseCases` の作る口）が持つ。** コマンドの `alarm` が
  `UNSET` なら `EventAlarm.default()`。画面の編集ダイアログも新しい予定に同じ既定を入れて**明示して送る**
  （`frontend/src/calendar/eventForm.ts` の `DEFAULT_ALARM`）。タスクを週表示へ落として作る予定は送らない
  （＝作る口の既定）。
- 応答: `CalendarEventResponse.alarm`・`GET /api/calendar/occurrences` の各回の `alarm`（予定の設定。`null` あり）。
- 直すときに省くと今のまま、にしたのは、ドラッグの日時変更（`PUT .../events/{id}` に詳細だけ載せる）で
  通知を消さないため（色の `null` = 今のまま、と同じ考え）。

### 4. 打刻アプリ向けの読み取り: `GET /api/calendar/alarms`

**この口の形はアプリ（wbstimer）との約束。** 変えるときはアプリと同時に変え、この節を書き直す。

- 認証: `get_app_or_web_user`（`AppOrWebUserDep`）。Web のセッション Cookie、または ADR-0018 の
  `Authorization: Bearer <assay のアクセストークン>`（`client_id` が `APP_CLIENT_IDS` に載っているもの）。
  ADR-0018 の決定 4（Bearer があれば Cookie へ落とさない）・5（`APP_CLIENT_IDS` が空なら通さない）はそのまま。
  **読むだけ。** 予定の書き込み・ほかの予定の口は Cookie だけのまま。
- クエリ（どちらも必須）:
  - `from`: 期間の始まり（**含む**）。ISO 8601 の瞬間。`Z` を推奨（オフセット `+09:00` も可。URL では `+` を
    `%2B` にする）。オフセットの無い値は UTC とみなす。秒・小数秒も可
  - `to`: 期間の終わり（**含まない**）。`from < to` かつ **`to − from ≤ 7 日`**（`MAX_ALARM_WINDOW`）
- 何を返すか: 利用者自身の予定のうち、通知を持ち（`alarm` が `null` でない）・`enabled` が true の予定の、
  終日でない回について、選んだ時刻ごとに 1 件。**`from ≤ notify_at < to` のものだけ**。回の展開は
  `/calendar/occurrences` と同じ（繰り返し・営業日シフト・祝日・移した回。飛ばした回は出ない）。
  並びは `notify_at` の昇順（同じなら `starts_at`、`event_id` の順）。
- 応答 `200`:

  ```json
  {
    "window_start": "2026-10-05T00:00:00Z",
    "window_end": "2026-10-06T00:00:00Z",
    "alarms": [
      {
        "id": "12:2026-10-05T01:00:00Z:15",
        "occurrence_id": "12:2026-10-05T01:00:00Z",
        "event_id": 12,
        "title": "設計レビュー",
        "location": "会議室A",
        "task_id": 34,
        "task_title": "設計書",
        "starts_at": "2026-10-05T01:00:00Z",
        "duration_minutes": 60,
        "notify_at": "2026-10-05T00:45:00Z",
        "minutes_before": 15,
        "is_recurring": false
      }
    ]
  }
  ```

  | 欄 | 型 | 意味 |
  |---|---|---|
  | `window_start` / `window_end` | string（UTC、`Z`） | 受け取った `from` / `to` を UTC にしたもの |
  | `id` | string | 通知 1 件の識別子 `<event_id>:<starts_at>:<minutes_before>`。端末の重複除け・取り消しの鍵 |
  | `occurrence_id` | string | 回の識別子 `<event_id>:<starts_at>`（同じ回の 15/5/1/0 分前をまとめる。スヌーズ・「次の通知」の範囲） |
  | `event_id` | integer | 予定の id |
  | `title` | string | 回の題名（古い上書き例外・移した回の題名を反映） |
  | `location` | string \| null | 場所 |
  | `task_id` | integer \| null | 結んだタスク。**消えた・他人のものなら `null`**（「打刻開始」で Start に渡す） |
  | `task_title` | string \| null | そのタスクの題名（`task_id` が `null` なら `null`） |
  | `starts_at` | string（UTC、`Z`） | 回の開始の瞬間 |
  | `duration_minutes` | integer | 回の長さ |
  | `notify_at` | string（UTC、`Z`） | 知らせる瞬間 = `starts_at − minutes_before` 分 |
  | `minutes_before` | integer（15 / 5 / 1 / 0） | 開始の何分前か。0 は開始時刻 |
  | `is_recurring` | boolean | 繰り返しの予定の回か |

  時刻はすべて `UtcDatetime`（`Z` 付き）。`id` / `occurrence_id` の中の `starts_at` も同じ書き方。
- 誤り:

  | 状態 | いつ | 本文 |
  |---|---|---|
  | `401` | 認証が無い・Bearer が受け取れない（署名・発行者・宛名・期限・`client_id`・機械のトークン） | `{"type","title","status","detail","instance"}` |
  | `403` | Bearer は正しいが Web で 1 度もログインしていない（結び付きが無い）・利用者を無効にした | 同上 |
  | `422` | `from` / `to` が無い・読めない（FastAPI の検証。`{"detail": [...]}`） | FastAPI の形 |
  | `422` | `from ≥ to`・`to − from > 7 日`（`ValidationError`） | `{"type","title":"Validation Error","status":422,"detail",...}` |

- **鳴らす規則は端末が持つ**（移植元 `AlarmScheduleCalculator.IsDue`）: `notify_at` より**早くは鳴らさない**。
  遅れても **1 分以内なら鳴らす**（`notify_at ≤ now ≤ notify_at + 1 分`）。それより遅れたら鳴らさない。
  端末は取りこぼしを拾うため `from` を「今 − 1 分」にして引けばよい。スヌーズ・「次の通知」・「残りを止める」も
  端末の状態（サーバは持たない）。

## 理由

- **端末で出す（サーバから押さない）**: FCM を使わない（#182）。通知の時刻は予定から決まるので、アプリが先の分を
  まとめて引いて端末の目覚ましに積めば、電波の無い間も鳴る。サーバに「鳴らした」状態を持たせると、端末ごと・
  スヌーズごとの状態が要り、移植元でも `AlarmApplicationService` の中（画面の側）に置いていた。
- **通知 1 件ずつの平らな一覧にした**: 回ごとに `minutes_before` の配列を返す形も考えたが、端末がやるのは
  「この時刻にこれを出す」を積むことで、平らな方が `notify_at` で並べ・期間で切り・重複を除くのが素直。
  `occurrence_id` で回にまとめ直せる。
- **期間は UTC の瞬間・半開区間・7 日まで**: 端末の目覚ましは瞬間で積むので、ローカル日で区切る必要が無い。
  半開区間なら続けて引いても同じ通知が 2 度出ない。7 日は 1 回の展開の重さの上限で、端末は数時間〜1 日ずつ
  引けば足りる。
- **列にした（JSON にしなかった）**: 欄が固定の 5 つで、規則（ADR-0009 の JSON の列）と違い種類ごとに形が
  変わらない。NULL で「持たない」を表せる。
- **回ごとの上書きを持たない**: 移植元で回ごとに黙らせる欄は上書き例外にあったが、WBS は上書き例外を作らない
  （ADR-0007）。1 回だけ通知を変えたいときは「この回だけ」で切り出せば、単発が自分の通知を持つ。
- **既存の予定は通知なし**: いきなり過去の予定すべてで端末が鳴り始めるのを避ける（持ち主の指示が無い部分は
  #182 の既定で決めた）。

## 影響

- 打刻アプリ（wbstimer）はこの口で作る（孫の課題）。通知の文言（「5 分後」・タスクに結んだ回の開始時刻の通知の
  「打刻開始」）はアプリが `minutes_before`・`task_id` から組み立てる。
- アプリのトークンで通る口が 4 つになった（ADR-0018 の 3 つ ＋ この口）。盗まれたトークンで読めるのは、
  その人の 7 日分の予定の題名・場所・タスク名まで。書き込みはできない。
- Web の画面は通知を鳴らさない（ブラウザの通知は作っていない）。編集ダイアログで設定するだけ。
- 端末がこの口を引く頻度で、展開（`/calendar/occurrences` と同じ処理）が走る。重くなったら期間の上限を縮める。
