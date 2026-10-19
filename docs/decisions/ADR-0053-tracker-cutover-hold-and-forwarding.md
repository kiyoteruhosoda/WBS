# ADR-0053: 打刻まわりを Tracker へ移す間の関所（切り替えの 503 と移転モード。Tracker の ADR-0053 の段 0・1）

- 状態: 承認
- 日付: 2026-10-19
- 関連: task #526（とくに AC3「移したあと、WBS 側の同じ記録は書き換えられない」）・目的 #522、
  **Tracker の ADR-0053 決定 3**（forge `kyon/nolumiatracker` の `docs/decisions/ADR-0053-nolumiatracker-is-split-out-of-wbs.md`。設計の正本）、
  ADR-0008（打刻）・ADR-0012（締め）・ADR-0018（Bearer の口）・ADR-0019（App Links）・ADR-0021（予定のアラーム）・ADR-0028（PWA と未送信の打刻）・
  ADR-0031（Web Push）・ADR-0042〜0045・0048〜0050（WinTrack の口）

⚠ 番号はこのリポジトリの続き番号。Tracker の ADR-0053（分け方の全体）とは別の文書で、この ADR はその段 0・1 のうち WBS 側の部分だけを決める。

## 背景

個人の工数（打刻・休み・自動の記録と規則・PC を使っていた時間・締め）を WBS から NolumiaTracker（tracker.nolumia.com）へ移す（#522）。
Tracker の ADR-0053 決定 3 で、移り方は「切り替えの数分だけ書き込みを 503 で待たせ、WBS の DB の写しを Tracker へ写し、その後は
WBS が Bearer の口を Tracker へ中継する」と決めた。古い端末（wbs.nolumia.com を向いた wbstimer と WinTrack）は、新しい版に入れ替わるまで
WBS を叩き続けるので、WBS の口は残す。ただし中身は Tracker に一本化し、WBS の表と Tracker の表の両方が正本になる時間を作らない。

ここで決めるのは、WBS がそのために持つ設定・口ごとの扱い・画面の替え方。**設定が無ければ今までと何も変わらない**（main へのマージで
本番へ配られるため）。

## 決定

### 1. 設定（ConfigMap で渡す）

| 環境変数 | 値 | 意味 |
|---|---|---|
| `TRACKER_CUTOVER_HOLD` | `true`（既定は空＝切） | 切り替えの 503。打刻まわりの書き込みを 503（`Retry-After: 120`）で断る |
| `TRACKER_FORWARD_URL` | Tracker の api のクラスタの中の番地（例 `http://api.tracker-prod.svc.cluster.local:8000`。既定は空＝切） | 移転モード |
| `TRACKER_PUBLIC_URL` | 既定 `https://tracker.nolumia.com` | 画面の案内と 409 の理由に出す Tracker の番地（stg では stg の Tracker を指す） |

両方入っているときは 503 が先（書き込みは待たせ、Bearer の読みは中継する）。状態は `off`・`hold`・`moved` の 3 つで、
`GET /api/tracker-move`（ログイン不要。値は設定だけ）が `{"mode": …, "url": …}` を返す。画面はこれを見る。
`/info` は版の確認の口なので形を変えない。

### 2. 口ごとの扱い

関所は 1 か所（`src/presentation/middleware/tracker_move_middleware.py`）。打刻まわりの口だけを見て、ほかの口には触らない。

**打刻まわりの口**（503・409 の範囲）: `/api/time-entries/*`・`/api/breaks/*`・`/api/pc-activity/*`・`/api/tracking-rules/*`・`/api/closing-periods/*`。
自動の打刻（`POST /api/time-entries/auto`）と自動の休み（`PUT /api/breaks/auto/{日}`）もこの中。

| | Bearer（`Authorization` ヘッダーがある。wbstimer・WinTrack） | Cookie（無い。WBS の画面） |
|---|---|---|
| 既定 | 今までどおり | 今までどおり |
| `hold` | 書き込み（GET・HEAD・OPTIONS 以外）は **503** と `Retry-After`。読むのは通す | 同じ |
| `moved` | **Tracker へ中継**（読みも書きも）。締めの口だけは中継せず、書き込みは 409 | 書き込みは **409**（`reason: moved_to_tracker`）。読むのは通す |

- 409 の本文は今までの 409 と同じ形で、`detail` は `Time tracking has moved to Tracker (tracker.nolumia.com)`、`reason` は `moved_to_tracker`、
  `tracker_url` に Tracker の番地。画面は `detail` の文で理由を見分け、「理由: 記録は Tracker に移りました（tracker.nolumia.com）」と出す。
- 503 の本文の `reason` は `tracker_cutover`。

**中継する口**（Bearer のとき）: `/api/time-entries`（一覧・足す）・`/api/time-entries/current`・`/start`・`/stop`・`/auto`・`/{id}`（読む・直す）と、
そのほかの `/api/time-entries/*`、`/api/breaks`・`/api/breaks/auto/{日}`、`/api/pc-activity`・`/api/pc-activity/{日}`、
`/api/tracking-rules`・`/api/tracking-rules/tasks` と、そのほかの `/api/tracking-rules/*`。
Bearer を受けない口（補正・規則の編集）は Tracker でも同じく Cookie だけなので、中継しても Tracker が 401 を返す（今の WBS と同じ答え）。

**WBS に残す口**（関所の外。今までどおり WBS が答える）: 予定のアラーム（`GET /api/calendar/alarms`。段 2 で Scheduler へ）、
wbstimer のログインの戻り先（`/app/oauth2redirect`）と `/.well-known/assetlinks.json`、WinTrack の更新の中継（`/api/wintrack/releases/*`）。
タスク・予定・手で書いた実績など、ほかの口もすべて今までどおり。

### 3. 中継のしかた

- **WBS は名乗らない。** 届いた `Authorization` をそのまま渡し、トークンを確かめるのは Tracker（ADR-0018 と同じ規則。Tracker の
  `APP_CLIENT_IDS` に wbstimer と WinTrack の client_id を入れる）。WBS は中継の前に利用者を引かない。
- 渡すヘッダーは `Authorization`・`Content-Type`・`Accept`・`Accept-Language`・`User-Agent`・`If-None-Match` だけ。**WBS の Cookie は渡さない**
  （Tracker には意味が無く、WBS のログインを外へ出すことになる）。道と問い合わせの文字列と本文はそのまま。
- 返すのは状態・本文と、ヘッダーの `Content-Type`・`WWW-Authenticate`・`Retry-After`・`Location`・`Cache-Control`・`ETag` だけ。転送は辿らずに返す。
- Tracker に届かない・30 秒で答えないときは **502**（`reason: tracker_unreachable`）。5xx なので端末は手元に残して送り直す。
- **1 件ごとにログを 1 行**: `event=tracker.relay`・`method`・`route`（番号は `{id}`、日付は `{day}` に伏せた口の名前）・`client_id`・
  `status_code`・`duration_ms`。`client_id` はトークンが名乗る値をそのまま読んだもの（確かめていない。数えるための見出し）。
  届かなかったものは `event=tracker.relay.failed`。段 4 で「14 日続けて 0」を数えるのはこの行。

### 4. 画面

- 移転モード（`mode=moved`）のとき:
  - 上部の打刻ボタンを「Tracker で記録」（Tracker を開く）に替える。移す前に端末へ溜めた打刻があれば 1 度だけ送り、409 で断られたら
    「記録できませんでした」と理由（Tracker に移りました）を出して捨てる（黙って溜めたままにしない）。
  - 締めの画面（`/closing`）と自動記録の規則の画面（`/tracking-rules`・`/tracking-rules/new`）は、Tracker の同じ画面（道と問い合わせを
    そのまま付ける）への案内に替える。上部の「未確定の締めの期間があります」は出さない。
  - 「今日」は、いまの打刻の欄を Tracker への案内に替え、今日の実績の欄と、予定から打刻を始めるボタンを出さない。
    いまの打刻（`GET /api/time-entries/current`）も読まない。**サーバも `GET /api/today` で打刻を返さない**（打刻・走っている打刻・
    今日の実績が空）。予定・タスクはこれまでどおり。
  - 実績の画面は、打刻から数える時間（`TRACKED`）を**サーバが出さない**（0）。上に「打刻から数える時間は Tracker に移った。確定した実績は
    Tracker から届くようになるまで増えない」と出す。確定した実績（`work_logs`）は今までどおり。
  - 設定の「端末への通知」から、打刻の止め忘れと締めの時期の 2 つを外す（5 を参照）。
- 切り替え中（`mode=hold`）は画面を替えない。打刻ボタンは押せて、503 は端末に残して後で送る（ADR-0028）。
- `/api/tracker-move` を読めない間（読み込み中・オフライン）は移していないとみなす（打刻ボタンが消えると、移す前の配備で
  オフラインの打刻を残せなくなる）。移した後に古い扱いで押しても、サーバが 409 で断って理由を出す。

### 5. Web Push

移転モードでは、送る係が**打刻の止め忘れ**と**締めの時期**を決めない（Tracker が送る）。予定の通知と定常業務の開始は段 2 まで WBS から送る。
購読と設定の値（`push_preferences`）はそのまま残す（Tracker の ADR-0053 決定 2 で写す元）。

### 6. 切り替えの手順（親が流す順番）

API の Pod は `Recreate`（新旧を重ねない）なので、設定を変えて入れ替える間も、古い設定の Pod が書き込みを受けることはない
（入れ替わりの数十秒は edge が 503 を返し、端末は手元に残す）。

1. **この ADR の版を配る**（設定なし。何も変わらない）
2. Tracker の prod が WBS と同じ契約で答えることを確かめる（#526 AC2）
3. WBS の ConfigMap に `TRACKER_CUTOVER_HOLD=true` を入れて当て直す → `GET /api/tracker-move` が `hold`、打刻の書き込みが 503 になったのを見る
4. WBS の DB の写しを取る（SQLite のバックアップの仕組み。WBS は読むだけ）→ Tracker の prod へ写す → 件数と締めの結果を突き合わせる
5. WBS の ConfigMap を `TRACKER_FORWARD_URL=<Tracker の api の番地>` にし、**同じ当て直しで** `TRACKER_CUTOVER_HOLD` を外す
   → `mode=moved`。溜まっていた書き込みが中継で Tracker に入る（`event=tracker.relay` の行が出る）
6. 写しが合わなかったら: 5 へ進まず `TRACKER_CUTOVER_HOLD` を外す（WBS のまま続ける。503 の間に溜まった分は端末から送り直される）

戻すとき（移転モードの後）は、設定を外すだけでは戻らない（中継の間の記録は Tracker にしか無い）。戻すなら Tracker から写し戻す別の手順が要る。

## 理由

### 関所を 1 か所のミドルウェアにした

口の数（打刻まわりだけで 30 近い）に依存関数を足して回る案は、足し忘れた口が 1 つあれば WBS の表に書けてしまう（AC3 に反する）。
道の前置きで決めれば、口が増えても漏れない。また中継は WBS の認証（利用者を WBS の DB で引く）と本文の検査より**前に**行う必要がある
（WBS は名乗らない・Tracker と同じ答えを返す）ので、ルーターの中では書けない。

### 503 で待たせる（3 つの端末とも 5xx は手元に残す。各コードで確かめた）

| 端末 | 5xx のとき | 捨てるもの | どこで |
|---|---|---|---|
| WBS の画面 | 溜めた押下を残し、30 秒おきなどに送り直す | 409・422 だけ | `frontend/src/timer/pendingPresses.ts` の `REFUSED_FOR_GOOD = [409, 422]`（それ以外の失敗で送るのを止めて残す） |
| wbstimer | 4xx（401 以外）は `RequestRejectedError`、5xx は `InfrastructureError` にして送るのを止め、残す | 409・422 だけ | `lib/infrastructure/api/web_api_client.dart` の `_send`、`lib/application/usecases/timer/sync_timer_presses_usecase.dart` の `refusedForGood = {409, 422}` |
| WinTrack | 打刻の区間は `WbsException` を受けて列に残し（`MarkAttempted`）、次の回に送る。休み・PC の時間は送れた日だけ覚えるので、5xx の日は次の回に丸ごと送る | 区間ごとの `rejected`、休みの 409（確定済み）、PC の時間の 422 | `src/WinTrack.Core/Sync/SyncService.cs` の `RunAsync`、`Sync/BreakSync.cs`・`Sync/PcActivitySync.cs` |

409・422 にすると画面と wbstimer は捨てるので、切り替えの間は 503 にする。

- その場で人が押して結果を見る操作（WinTrack のトレイからの「開始」、wbstimer の打刻の修正、画面の補正・締め・規則の編集）は
  溜めずに「できませんでした」と出す。数分のことなので、押し直してもらう。
- edge（edge-prod）は 503 の本文を自分の「停止中」に差し替える（`Retry-After` も残らないかもしれない）。状態は 503 のままなので、
  端末の扱いは変わらない。`Retry-After` を読む端末は無い。

### Cookie の口は中継せず 409 にした

WBS が利用者の代わりに Tracker を呼ぶには、アプリどうしの信頼（共有の秘密や代理のトークン）が要る（Tracker の ADR-0053 の理由 2〜3）。
画面は同じ配布で Tracker への案内に替わるので、古いタブからの数件のために作る価値は無い。409 なら画面は理由付きで知らせて捨てる。
Cookie の**読み**は通す（移した時点で凍った値で、新しい画面は読まない。古いタブが壊れて見えるのを避ける）。

### 締めの口は Bearer でも中継しない

締めは画面だけの口（Bearer を受けない）。Tracker の決定 3 の中継の範囲にも入っていない。

### 「今日」と実績はサーバ側でも打刻を読まない

画面だけで隠すと、古いタブや別の画面（実績の書き出し・内訳）が凍った打刻を今の値として出す。サーバで空にすれば、どの読み手にも出ない。

### 状態を `/info` ではなく `/api/tracker-move` で出した

`/info` は版の確認の口（deck と人が版を突き合わせる）で、試験も項目を固定している。画面のための 1 項目を混ぜない。

## 影響

- 設定が無ければ何も変わらない（試験 `test_by_default_nothing_changes`）。
- #526 AC3 は `tests/integration/api/test_tracker_move.py` が示す: 移転モードで、打刻まわりの書き込みすべて（画面・wbstimer・WinTrack が
  使うもの 18 種）を Cookie でも Bearer でも送り、WBS の打刻まわりの表（打刻・休み・PC の時間・規則・控え・切り抜き・締め・実績）が
  1 行も変わらないこと。
- 中継の行は Pod のログ（標準出力）に出る。Pod が入れ替わると消えるので、段 4 で「14 日続けて 0」を数えるには、日ごとに数えて残す仕組みが別に要る。
- WBS の確定した実績と進捗率は段 3（Tracker から締めた時間が届く）まで止まる（Tracker の ADR-0053 決定 4。持ち主が承知のうえ）。
- 段 4（WBS の片付け）で、この関所・中継・打刻まわりの表・画面の打刻まわりを消す。
