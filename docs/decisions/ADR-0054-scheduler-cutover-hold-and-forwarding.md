# ADR-0054: 予定まわりを Scheduler へ移す間の関所（切り替えの 503 と移転モード。Scheduler の ADR-0054 の段 0・1）

- 状態: 承認
- 日付: 2026-10-19
- 関連: task #535・段 2 #533・目的 #522、
  **Scheduler の ADR-0054 決定 3**（forge `kyon/nolumiascheduler-server` の `docs/decisions/ADR-0054-nolumiascheduler-server-is-split-out-of-wbs.md`。設計の正本）、
  **ADR-0053**（同じ形の、打刻まわりを Tracker へ移す関所。この ADR はそれに倣う）、
  ADR-0014（予定済みの時間）・ADR-0015（「今日」）・ADR-0017（実績）・ADR-0018（Bearer の口）・ADR-0021（予定のアラーム）・
  ADR-0025（定常業務）・ADR-0027（カレンダー）・ADR-0031（Web Push）・ADR-0037（iCalendar の取り込み）

⚠ 番号はこのリポジトリの続き番号。Scheduler の ADR-0054（分け方の全体）とは別の文書で、この ADR はその段 0・1 のうち WBS 側の部分だけを決める。
番号が同じなのはたまたま（Scheduler のリポジトリは WBS の 0053 までを引き継いで 0054 から数えた）。

## 背景

個人の予定（予定・カレンダー・休みの層・iCalendar の取り込み・アラーム・Web Push・定常業務）を WBS から NolumiaScheduler
（scheduler.nolumia.com）へ移す（#522・#533）。Scheduler の ADR-0054 決定 3 で、移り方は段 1（Tracker）と同じ「切り替えの数分だけ
書き込みを 503 で待たせ、WBS の DB の写しを Scheduler へ写し、その後は WBS が Bearer のアラームの口を Scheduler へ中継する」と決めた。
古い wbstimer（wbs.nolumia.com からアラームを引く）は、新しい版（#536）に入れ替わるまで WBS を叩き続けるので、WBS の口は残す。
ただし中身は Scheduler に一本化し、WBS の予定の表と Scheduler の表の両方が正本になる時間を作らない。

ここで決めるのは、WBS がそのために持つ設定・口ごとの扱い・画面の替え方。**設定が無ければ今までと何も変わらない**（main へのマージで
本番へ配られるため）。打刻の関所（ADR-0053。本番は移転モードで動いている）とは**別の設定・別の関所**で、互いの口に触らない。

## 決定

### 1. 設定（ConfigMap で渡す）

| 環境変数 | 値 | 意味 |
|---|---|---|
| `SCHEDULER_CUTOVER_HOLD` | `true`（既定は空＝切） | 切り替えの 503。予定まわりの書き込みを 503（`Retry-After: 120`）で断る |
| `SCHEDULER_FORWARD_URL` | Scheduler の api のクラスタの中の番地（例 `http://api.scheduler-prod.svc.cluster.local:8000`。既定は空＝切） | 移転モード |
| `SCHEDULER_PUBLIC_URL` | 既定 `https://scheduler.nolumia.com` | 画面の案内と 409 の理由に出す Scheduler の番地（stg では `https://schedulerstg.nolumia.com`） |

読み方は `TRACKER_*` と同じ（`true`・`1`・`yes`・`on` で入、番地の末尾の `/` は落とす）。両方入っているときは 503 が先
（書き込みは待たせ、Bearer のアラームの読みは中継する）。状態は `off`・`hold`・`moved` の 3 つで、
`GET /api/scheduler-move`（ログイン不要。値は設定だけ）が `{"mode": …, "url": …}` を返す。画面はこれを見る。

### 2. 口ごとの扱い

関所は 1 か所（`src/presentation/middleware/scheduler_move_middleware.py`）。予定まわりの口だけを見て、ほかの口には触らない。

**予定まわりの口**（503・409 の範囲）: `/api/calendar/*`・`/api/calendars/*`・`/api/calendar-view-presets/*`。
予定・繰り返しの回の操作（この回だけ・以降・飛ばす・戻す・移す・済み）・カレンダー・表示の選択・休みの層・取り込みと読み込み直し・
表示の組み合わせが、すべてこの中にある。

| | Bearer（`Authorization` ヘッダーがある。wbstimer） | Cookie（無い。WBS の画面） |
|---|---|---|
| 既定 | 今までどおり | 今までどおり |
| `hold` | 書き込み（GET・HEAD・OPTIONS 以外）は **503** と `Retry-After`。読むのは通す | 同じ |
| `moved` | `GET /api/calendar/alarms` は **Scheduler へ中継**。ほかの口は中継せず、書き込みは 409・読みは今までどおり WBS が答える | 書き込みは **409**（`reason: moved_to_scheduler`）。読むのは通す |

- 409 の本文は今までの 409 と同じ形で、`detail` は `Calendar has moved to Scheduler (scheduler.nolumia.com)`、`reason` は `moved_to_scheduler`、
  `scheduler_url` に Scheduler の番地。画面は `detail` の文で理由を見分け、「理由: 予定は Scheduler に移りました（scheduler.nolumia.com）」と出す。
- 503 の本文の `reason` は `scheduler_cutover`。

**中継する口**（Bearer のとき）: `GET /api/calendar/alarms` だけ。

**Bearer でもほかの予定の口は中継しない**（Scheduler の ADR-0054 決定 3 で「中継するか 401 のままかは打刻の関所と同じ考えで決める」とされたもの）。
打刻の関所は「WBS で Bearer を受けていた口だけを中継し、画面だけの口（締め）は中継しない」と決めた（ADR-0053 決定 2）。予定まわりで
Bearer を受けていたのはアラームの口だけ（ADR-0018・0021）なので、同じ考えで中継はアラームの口に限る。ほかの口に Bearer で来る古い端末は無く
（Windows アプリ #537 は scheduler.nolumia.com を直接叩く）、中継すると「WBS に来た Bearer の予定の書き込みが Scheduler に入る」道が
新しくできてしまう。Bearer の書き込みは 409、読みは今までどおり WBS が答える（WBS はその口で Bearer を受けないので、SSO の配備では 401）。

**関所の外**（今までどおり WBS が答える）: タスク・プロジェクト・手で書いた実績など予定でない口すべてと、`/api/push/*`（通知の購読と設定。
3 を参照）。打刻まわりの口（`/api/time-entries/*` など）は打刻の関所が見る。道が重ならないので、2 つの関所は互いに触らない
（試験 `test_the_two_gates_do_not_touch_each_others_routes`）。

### 3. WBS のサーバーが予定を読む・書くところ（移転モード）

移した後の WBS の予定の表は凍っている。凍った値を今のものに見せないよう、**サーバーで**読まない。

| どこ | 移転モードでは |
|---|---|
| `GET /api/today` | `tasks_to_schedule`（まだ予定を取っていないタスク）を空で返す。予定の表から決まる値で、「時間を取る」先のカレンダーも WBS に無いため。予定の回と取り込んだ回は、もともとこの口では返さず（`/api/calendar/occurrences`・`/api/calendars/imported-occurrences` を画面が別に読む）、画面が移転モードでは読まない |
| タスク（`GET /api/tasks` ほか、`TaskUseCases` を使う口すべて） | `scheduled_hours`・`unscheduled_hours` を null（予定済みの時間を数える口を渡さない） |
| 実績（`/api/actuals/*`） | 予定から数える時間（`PLANNED`）を 0 |
| Web Push の送る係 | `event_alarm`・`routine_start` を決めない（Scheduler が送る）。購読と設定の値（`push_preferences`）はそのまま残す（Scheduler の ADR-0054 決定 2 で写す元） |
| 取り込んだカレンダーを読み込み直す係（15 分ごと） | **切り替え中（`hold`）と移転モードでは起動しない。** 読み込み直しも予定の表（`calendar_imports`・`calendar_imported_occurrences`）に書くため。写しを取った後に WBS で書くと、その分は Scheduler に入らない |

### 4. 画面

- 移転モード（`mode=moved`）のとき:
  - カレンダー（`/calendar`）とカレンダーの設定（`/calendar/settings`）は、Scheduler の同じ画面（道と問い合わせをそのまま付ける）への案内に替える
    （`SchedulerMovedNotice`。打刻の `TrackerMovedNotice` と同じ形）。
  - 「今日」は、予定の欄（時間の表・定常業務・まだ時間を取っていないタスクと「時間を取る」）を出さず、Scheduler への案内を出す。予定の回・取り込んだ回・休みも読まない。
  - タスクの一覧・タスクの編集・ガントは、「予定済みの時間」と「時間を取る」を出さない。
  - 実績の画面は上に「予定は Scheduler に移った。ここでは予定の時間を出さない（0）」と出す。
  - 設定の「端末への通知」から、予定の通知・定常業務の開始・画面の中の予定の知らせ・端末ごとの「予定の通知を受け取る」を外し、
    「予定の通知は Scheduler から届く。Scheduler で通知を許す」と出す。
  - 上部の、画面の中の予定の知らせ（`InPageAlarm`。`GET /api/calendar/alarms` を Cookie で読む）と音の入り切りを出さない。
    凍った予定で鳴らすと、Scheduler で直した予定と食い違うため。
- 切り替え中（`mode=hold`）は画面を替えない。予定の書き込みは 503 で断られ、「保存できませんでした」と出る（予定の編集は手元に溜めない）。
- `/api/scheduler-move` を読めない間（読み込み中・オフライン）は移していないとみなす（移す前の配備でカレンダーが消えると予定を見られなくなる）。
  移した後に古い扱いで書いても、サーバーが 409 で断る。画面は理由（「予定は Scheduler に移りました（…）」）を出し、
  `/api/scheduler-move` を読み直してカレンダーを Scheduler への案内に替える。この 409 は版の食い違い（ほかで変わっていた）とは分けて扱う。

### 5. 中継のしかた

打刻の関所（ADR-0053 決定 3）と同じ。

- **WBS は名乗らない。** 届いた `Authorization` をそのまま渡し、トークンを確かめるのは Scheduler（Scheduler の `APP_CLIENT_IDS` に wbstimer の client_id を入れる）。
- 渡すヘッダーは `Authorization`・`Content-Type`・`Accept`・`Accept-Language`・`User-Agent`・`If-None-Match` だけ。**WBS の Cookie は渡さない。**
  道と問い合わせの文字列と本文はそのまま。
- 返すのは状態・本文と、ヘッダーの `Content-Type`・`WWW-Authenticate`・`Retry-After`・`Location`・`Cache-Control`・`ETag` だけ。転送は辿らずに返す。
- Scheduler に届かない・30 秒で答えないときは **502**（`reason: scheduler_unreachable`）。wbstimer は手元のアラームを残して次の回に引き直す。
- **1 件ごとにログを 1 行**: `event=scheduler.relay`・`method`・`route`（`/api/calendar/alarms`）・`client_id`・`status_code`・`duration_ms`。
  届かなかったものは `event=scheduler.relay.failed`。段 3（Scheduler の ADR-0054 の表の段 3）で「14 日続けて 0」を数えるのはこの行。

中継の係（`HttpSchedulerRelay`）と口（`SchedulerRelay`）は打刻の関所のものと同じ形だが、**共有しない**。2 つの関所は段 4 で別々の時期に消すので、
片方を消すときにもう片方を壊さないため。

### 6. 切り替えの手順（親が流す順番）

API の Pod は `Recreate`（新旧を重ねない）なので、設定を変えて入れ替える間も、古い設定の Pod が書き込みを受けることはない
（入れ替わりの数十秒は edge が 503 を返す）。**切り替えの時刻と手順は前もって持ち主へ知らせる**（503 の間、WBS の画面での予定の編集は断られる）。

1. **この ADR の版を配る**（設定なし。何も変わらない）
2. Scheduler の prod が WBS と同じ契約で答えることを確かめる（#535 AC1・AC2）
3. WBS の ConfigMap に `SCHEDULER_CUTOVER_HOLD=true` を入れて当て直す → `GET /api/scheduler-move` が `hold`、予定の書き込みが 503 になったのを見る
   （取り込んだカレンダーの読み込み直しも止まる）
4. WBS の DB の写しを取る（SQLite のバックアップの仕組み。WBS は読むだけ）→ Scheduler の prod へ写す → 件数と回の展開を突き合わせる
5. WBS の ConfigMap を `SCHEDULER_FORWARD_URL=<Scheduler の api の番地>` にし、**同じ当て直しで** `SCHEDULER_CUTOVER_HOLD` を外す
   → `mode=moved`。wbstimer のアラームの読みが中継で Scheduler に入る（`event=scheduler.relay` の行が出る）
6. 写しが合わなかったら: 5 へ進まず `SCHEDULER_CUTOVER_HOLD` を外す（WBS のまま続ける。503 の間に断られた画面の編集は、押し直してもらう）

wbstimer のアラームはどの時点でも止まらない（3〜4 の間は WBS の読みが通り、5 からは中継）。
戻すとき（移転モードの後）は、設定を外すだけでは戻らない（Scheduler で書いた予定は Scheduler にしか無い）。戻すなら Scheduler から写し戻す別の手順が要る。

## 理由

### 打刻の関所と同じ形にした

段 1 で本番に入れて動いている型で、試験も運用の手順も揃う。違うのは、予定まわりで Bearer を受けるのが読み取りのアラームの口 1 つだけで、
書き込みの端末が WBS の画面しか無いこと。そのため 503 で待たせて端末に送り直させる必要は打刻ほど無いが、写しを取る間に書かせないために要る。

### 関所を 1 か所のミドルウェアにした

ADR-0053 と同じ。予定まわりの口は 40 近くあり、依存関数を足して回る案では足し忘れた口から WBS の表に書けてしまう。道の前置きで決めれば漏れない。
中継は WBS の認証と本文の検査より前に行う必要がある（WBS は名乗らない）ので、ルーターの中では書けない。

### 取り込みの読み込み直しを止めた

関所は外から来る書き込みだけを止める。WBS が自分で 15 分ごとに外の iCalendar を読みに行って書く分は関所を通らないので、起動のときに止める。
止めないと、写しを取った後に WBS の表だけが変わり、「WBS の予定の表は書き換えられない」が崩れる（Scheduler は自分で読み込み直すので、WBS が読む必要も無い）。

### 「今日」・タスク・実績はサーバー側でも予定を読まない

画面だけで隠すと、古いタブや別の画面（実績の書き出し・内訳、タスクの書き出し）が凍った予定を今の値として出す。サーバーで空・null・0 にすれば、どの読み手にも出ない。
`tasks_to_schedule` は予定から決まる「まだ時間を取っていない」の一覧なので、予定済みの時間が分からない以上は出せない（null のまま並べると、
見積の無いタスクだけが残るなど意味の違う一覧になる）。

### Cookie の口は中継せず 409 にした

ADR-0053 と同じ。WBS が利用者の代わりに Scheduler を呼ぶには、アプリどうしの信頼が要る。画面は同じ配布で Scheduler への案内に替わるので、
古いタブからの数件のために作る価値は無い。Cookie の**読み**は通す（新しい画面は読まない。古いタブが壊れて見えるのを避ける）。

### 状態を `/info` ではなく `/api/scheduler-move` で出した

ADR-0053 と同じ（`/info` は版の確認の口で、形を固定している）。打刻の `/api/tracker-move` とも分けた（片方だけ移す時期がある）。

## 影響

- 設定が無ければ何も変わらない（試験 `test_by_default_nothing_changes`）。
- 「移した後、WBS の予定の表は書き換えられない」は `tests/integration/api/test_scheduler_move.py` が示す: 移転モードと切り替え中に、予定まわりの書き込みすべて
  （画面が使うもの 28 種）を Cookie でも Bearer でも送り、WBS の予定の表 9 つ（カレンダー・休み・取り込み・取り込んだ回・表示の組み合わせ・予定・例外・移動・済み）が
  1 行も変わらないこと。取り込みの読み込み直しが起動しないこと。
- 中継の行は Pod のログ（標準出力）に出る。Pod が入れ替わると消えるので、「14 日続けて 0」を数えるには日ごとに数えて残す仕組みが別に要る（打刻と同じ）。
- 段 4（WBS の片付け）で、この関所・中継・予定の表・カレンダーの画面のコードを消す。打刻の関所とは別々に消せる。
