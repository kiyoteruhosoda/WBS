# ADR-0070: Tracker・Scheduler へ移したものと「今日」・週次レビューを WBS から外す（段 4）

- 状態: 承認
- 日付: 2026-11-03
- 関連: task #543（親 #542 第 4 段・目的 #522）、**ADR-0053・ADR-0054**（移転モードの関所。この ADR で外す）、
  Tracker の ADR-0053・Scheduler の ADR-0054（分け方の全体。段 4 は「中継に来る数が 14 日 0 なら WBS から消す」）、
  ADR-0015（「今日」の画面）・ADR-0017（実績の見える化）・ADR-0046（タスクの削除とアーカイブ）・ADR-0056（Tracker から締めた時間を受け取る口）

## 背景

2026-10-19 に、個人の工数（打刻・休み・PC を使っていた時間・自動記録の規則・締め）を NolumiaTracker へ、
個人の予定（予定・カレンダー・休みの層・取り込み・アラーム・定常業務）を NolumiaScheduler へ本番で移した。
WBS は「移転モード」で、古い端末（wbstimer・WinTrack）の Bearer の口だけを中継していた（`TRACKER_FORWARD_URL`・`SCHEDULER_FORWARD_URL`）。
画面の書き込みは 409、読みは凍った値を返していた。WBS はチームのプロジェクトの道具（ADR-0055 メンバー・担当、ADR-0058〜0060 カレンダー）に戻る。

段 4 の約束は「中継に来る数が 14 日 0 なら消す」。14 日は 2026-11-02 に明けた。2026-11-03 に確かめたこと:

- `kubectl -n wbs-prod logs deploy/api` の `tracker.relay`・`scheduler.relay` は 0 件。ただし Pod が 11/02 22:21 UTC に入れ替わっていて、
  ログは約 9.5 時間分しか無い（ADR-0053・0054 の「影響」に書いたとおり、日ごとに数えて残す仕組みは作らなかった）。
- 同じ時間に edge では wbstimer（`Dart/3.13`）からアラームの口へ 17 件来ていたが、WBS には打刻・アラームの口への呼び出しが 0 件。
  今動いている端末は Scheduler・Tracker へ直接行っている。
- wbstimer の配布の宣言（deploy-repo `resources/flutter-apps.json`）は `TRACKER_HOST=tracker.nolumia.com`・`SCHEDULER_HOST=scheduler.nolumia.com`・
  `appLinkHost=tracker.nolumia.com`。ADR-0053・0054 で「WBS に残す」とした口（`GET /api/calendar/alarms`・`/app/oauth2redirect`・
  `/.well-known/assetlinks.json`・`/api/wintrack/releases/*`）の使い手はもう WBS を向いていない。
- WinTrack の既定の送り先は `https://tracker.nolumia.com`。前の版で WBS を設定していた PC も起動時に Tracker へ戻す（WinTrack ADR-0015）。

Web Push（端末への通知）の 4 種類（予定のアラーム・定常業務の開始・打刻の止め忘れ・締めの時期）も、すべて Tracker・Scheduler が送る。

## 決定

### 1. 外す口（404 になる。試験 `tests/integration/api/test_moved_routes_are_gone.py`）

- 打刻まわり: `/api/time-entries/*`・`/api/breaks/*`・`/api/pc-activity/*`・`/api/tracking-rules/*`・`/api/closing-periods/*`・`/api/wintrack/releases/*`
- 予定まわり: `/api/calendar/*`（アラームを含む）・`/api/calendars/*`・`/api/calendar-view-presets/*`
- 端末への通知: `/api/push/*`
- 移転モードの状態: `/api/tracker-move`・`/api/scheduler-move`
- 「今日」: `/api/today`。週次レビュー: `/api/reviews/weekly`
- 打刻アプリの App Links: `/.well-known/assetlinks.json`（画面の nginx の転送も外す）

### 2. 外す仕組み

- 移転モードの関所（`TrackerMoveMiddleware`・`SchedulerMoveMiddleware`）と中継。設定 `TRACKER_CUTOVER_HOLD`・`TRACKER_FORWARD_URL`・
  `TRACKER_PUBLIC_URL`・`SCHEDULER_*` は読まなくなる（deploy-repo の ConfigMap から外すのは WBS の版が出た後）
- 定期の係: Web Push の送り手・取り込んだカレンダーの読み込み直し
- アプリの Bearer の口（ADR-0018 の `get_app_or_web_user`）。設定 `APP_CLIENT_IDS`・`ANDROID_APP_PACKAGE`・`ANDROID_APP_CERT_FINGERPRINTS`・
  `WEB_PUSH_*`・`CALENDAR_FEED_KEY_FILE`・`WINTRACK_RELEASES_*` も読まなくなる
- タスクの「予定済みの時間」（`scheduled_hours`・`unscheduled_hours`。ADR-0014）。移した後は常に null だった

### 3. 表（移行 0035。⚠ 中身は捨てる）

消す: 打刻まわり 9 表（`time_entries`・`time_entry_carvings`・`auto_time_entry_receipts`・`work_breaks`・`pc_activity_days`・`pc_activity_spans`・
`tracking_rules`・`tracking_rule_books`・`closing_periods`）、予定まわり 9 表（`calendars`・`calendar_days_off`・`calendar_imports`・
`calendar_imported_occurrences`・`calendar_view_presets`・`calendar_events`・`calendar_event_exceptions`・`calendar_event_moves`・`calendar_event_completions`）、
Web Push 3 表（`push_subscriptions`・`push_preferences`・`push_dispatches`）、`work_logs.closing_period_id`。

残す: `work_logs` の行はすべて（WBS の締めで作った `source=closing` の行も、Tracker から届いた `source=tracker` の行も）。
チームのカレンダー（`team_workweeks`・`team_days_off`・`member_days_off`・`team_extra_workdays`）は WBS のもの。

DROP するか残すかは持ち主が選んだ（2026-11-03「今回消す」）。写しは切り替えのときに Tracker・Scheduler へ取ってあり、
WBS の DB は毎日 19:30 に nolumialab と labbackup の 2 か所へ退避している（直前の退避は 2026-11-02 19:30）。
戻す移行は空の表を作る（中身は戻らない）。

### 4. 画面

- メニューから「今日」「カレンダー」「締め」「自動記録の規則」を外す。最初の画面は「タスク」（`/` は `/tasks` へ）。外した画面の古い道も `/` へ
- 上部の打刻ボタン（移した後は「Tracker で記録」の案内）・予定の通知の音の切り替え・締めの知らせ・画面の中の予定の知らせを外す
- 設定から「端末への通知」と時刻の表記（12/24 時間。打刻の時刻入力にだけ使っていた）を外す。Service Worker は通知を出さない（画面の殻だけ）
- タスクの一覧・編集・ガントから「時間を取る」（カレンダーへ）と「予定済みの時間」を外す。タスクの開始・期限が個人の休みに当たる知らせも外す
  （個人の休みの層は Scheduler へ移した。チームの休日はガントの列とプロジェクトのカレンダーで見る）
- 打刻アプリのログインの戻り先の画面（`/app/oauth2redirect`）を外す

### 5. 実績の見える化（ADR-0017 を狭める）

- 数えるのは確定した実績（`work_logs`）だけ。期間ごとの「予定した時間」「打刻」「差」「タスク外」と、積み上げ・書き出しの時間の種類（`source`）を外す
  （移した後はどれも 0 だった）。期間ごとの「確定済みか」（`closed`）も外す（WBS の締めの期間が無くなった）
- 「直近の締め」と残の見直し（`stale_remaining`）は、Tracker から直近に届いた締めの期間（`work_logs.tracker_first_day` の最も新しいもの。
  届いた時刻はその行の更新時刻）で決める。期間の終わりは届いた実績の最後の日

### 6. タスクの削除（ADR-0046 を狭める）

確定した実績があればアーカイブ、無ければ削除。打刻・WinTrack の規則・計測中の判定は外す（Tracker のもの）。

## 理由

- 中継は 14 日分を数えられなかったが、今動いている端末（wbstimer の今の版・WinTrack）が WBS を向いていないことを、
  配布の宣言・既定値と、同じ時間の edge と WBS の記録の突き合わせで確かめた。古い版が残っていても、壊れるのは古い版の打刻とアラームだけで、
  記録の正本はもう Tracker・Scheduler にある（WBS が受けても 409 か中継だった）。
- 表を残す案は、読むコードが無いまま形だけが残り、モデルと移行の突き合わせ（`test_migration_model_consistency.py`）からも外せない。
  写しと日次の退避があるので、持ち主の選択で消した。
- 実績の「予定」「打刻」を 0 のまま出し続ける案は、意味の無い列が並ぶ。Tracker・Scheduler の画面で見るものを WBS で見せない。

## 影響

- 古い wbstimer・WinTrack が WBS を叩くと 404 になる（古い版の打刻とアラームは届かない）。新しい版へ入れ替えれば直る。
- deploy-repo の WBS の ConfigMap と Secret（`TRACKER_*`・`SCHEDULER_*`・`APP_CLIENT_IDS`・`ANDROID_APP_*`・VAPID・購読の鍵・WinTrack の置き場）は、
  この版が出た後に外す（残っていても読まれないだけ）。
- ADR-0053・ADR-0054 は「置換（ADR-0070 による）」。ADR-0014・0015・0018（Bearer の口）・0019・0021・0031 ほか、移したものの ADR の決定は WBS では効かない。
