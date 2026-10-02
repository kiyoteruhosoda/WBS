# OPERATIONS

操作手順だけを置く。なぜそうなっているかは `decisions/`（ADR）、過去の経緯は `CHANGELOG.md`。

## IdP で止めた人を、このアプリでも止まるようにしたいとき

ADR-0003 の二段（受け口・定期照合）を有効にする。⚠ **IdP 側の 3 手が要る。**

### 1. 停止の通知の送り先を登録する（IdP 側）

このアプリのクライアントに、back-channel logout の送り先を登録する。

```
https://<このアプリのホスト>/api/auth/backchannel-logout
```

確かめ方（登録の前でも通る。**400 が返れば口が在る**。404 なら経路が違う）:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://<host>/api/auth/backchannel-logout -d 'logout_token=x'
# 400 … 口が在る（トークンが通らないだけ）
# 404 … 経路が違う、または AUTH_MODE=oidc になっていない
```

### 2. このアプリの鍵を用意する（機械としての名乗り）

⚠ **ログイン用のクライアントは public ＋ PKCE で鍵を持たない。** 機械として名乗るには
別に鍵が要る。

```bash
openssl genrsa -out machine.key 2048
openssl rsa -in machine.key -pubout -out machine.pub
```

⚠ **コンテナの実行ユーザーが読めること**（`0400 root` だと読めない。group を実行 gid に合わせる）。

### 3. サービスアカウントを登録し、アプリへ結び付ける（IdP 側）

1. `client_credentials` を使うクライアントとして登録し、`machine.pub` を公開鍵として登録する
2. **アプリの「このアプリの名乗り」に結び付ける。** ⚠ 結び付けるまで名簿の API は 403 を
   返し続ける（トークンそのものは取れる）

### 4. 環境変数を足して配り直す

```bash
MACHINE_CLIENT_ID=wbs-machine
MACHINE_PRIVATE_KEY_FILE=/srv/secrets/oidc/machine.key
MACHINE_PRIVATE_KEY_KID=                 # 鍵を複数登録しているときだけ
```

⚠ **compose の `environment:` に並んでいるキーだけがコンテナへ届く**（`.env` に書いても
並んでいなければ届かない）。

### 5. 効いていることを確かめる

| 見たいこと | どこを見るか |
|---|---|
| 定期照合が回ったか | ログの `auth.oidc.reconciliation.finished`（起動の 60 秒後と毎時） |
| 名乗りがまだ結び付いていない | ログの `auth.oidc.reconciliation.not_bound` |
| 停止の通知が届いたか | ログの `auth.oidc.logout_received` |
| 通知を断った | ログの `auth.oidc.logout_rejected` |

⚠ **`MACHINE_CLIENT_ID` が空なら定期照合は動かない**（ログにも何も出ない）。受け口のほうは
名乗りが無くても効く。

## 打刻アプリ（Android）から Start / Stop を叩けるようにしたいとき

ADR-0018・ADR-0021。アプリは assay に直接ログインし、打刻の 3 つの口（現在・Start・Stop）と
予定の通知の読み取り（`GET /api/calendar/alarms`）だけを assay のアクセストークンで叩く。
⚠ **`APP_CLIENT_IDS` が空なら Bearer は 1 本も通らない**（既定）。

1. assay にアプリ用の **public client** を登録する（PKCE、scope は `openid profile email offline_access`、戻り先は `https://<ホスト>/app/oauth2redirect`）。
   WBS の Web と同じ assay のアプリに結び付けて名簿を 1 つにする。⚠ `resource` は送らない
   （人のログインでは assay が `invalid_target` で断る）
2. 環境変数を足して配り直す（⚠ 管理画面からは入れられない）:

   ```bash
   APP_CLIENT_IDS=<1 で出た client_id>      # 複数はカンマ区切りか JSON の配列
   # App Links（ADR-0019）。アプリのログインの戻り先をアプリへ渡す宣言
   ANDROID_APP_PACKAGE=com.nolumia.wbstimer
   ANDROID_APP_CERT_FINGERPRINTS=<署名証明書の SHA-256 指紋>   # deploy-repo の resources/flutter-apps.json の cert_sha256
   ```

3. 使う人は **Web で 1 度ログインしておく**（結び付きが無いとアプリの口は 403）
4. 確かめる:

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' -H 'Authorization: Bearer x' https://<ホスト>/api/time-entries/current   # 401
   curl -s -o /dev/null -w '%{http_code}\n' -H 'Authorization: Bearer x' 'https://<ホスト>/api/calendar/alarms?from=2026-10-05T00:00:00Z&to=2026-10-06T00:00:00Z'   # 401
   curl -s -o /dev/null -w '%{http_code}\n' -H 'Authorization: Bearer x' https://<ホスト>/api/tasks                  # 401（アプリの口ではない）
   curl -s https://<ホスト>/.well-known/assetlinks.json                                                              # 200 と JSON（text/html なら nginx が裏へ渡していない）
   ```

## SSO を後から入れて、既に居る利用者を引き継ぎたいとき

⚠ **既定では、メールアドレスが同じでも既存の利用者へ寄せない**（ADR-0004）。移行のあいだ
だけ開ける。

```bash
OIDC_LINK_BY_EMAIL=true
```

⚠ **移行が済んだら戻す。** 結び付いた後の人はこの枝を通らないので、戻しても入れなくなる人は
出ない。

## PWA のアイコンを変えたいとき

1. `scripts/generate_pwa_icons.py` の配色（`GRADIENT_*`）か図柄（`MARK_BOXES`）を直す
2. `python3 scripts/generate_pwa_icons.py` を流し、`frontend/public/` に出たファイルをまとめてコミットする
3. 色を変えたら `frontend/public/manifest.webmanifest` の `theme_color` と `frontend/index.html` の `theme-color` も揃える

## PWA が本番で効いているか確かめたいとき

ログインしていない状態（Cookie なし）で、次がすべて 200 で転送されないこと:

```bash
for p in /sw.js /manifest.webmanifest /pwa-192x192.png /pwa-512x512.png /pwa-maskable-512x512.png; do
  curl -s -A "Mozilla/5.0" -o /dev/null -w "%{http_code} %{content_type} $p\n" "https://wbs.nolumia.com$p"
done
curl -sI -A "Mozilla/5.0" https://wbs.nolumia.com/sw.js | grep -i cache-control   # no-cache
```

配った版は `curl -s -A "Mozilla/5.0" https://wbs.nolumia.com/api/info` の `git_sha` で見る。ブラウザで見るときは、
先に Service Worker を更新して読み直す（`(await navigator.serviceWorker.getRegistrations()).forEach(r => r.update())`、
1〜2 秒待って再読み込み）。

## 取り込んだカレンダーの URL を購読できるようにしたいとき

ADR-0037。⚠ **鍵が無ければ購読はできない**（既定。ファイルと 1 回だけの URL は使える）。

1. 32 バイトの鍵を**ホストの上で**作り、api のコンテナから読める場所に置く（値を環境変数・画面に入れない）:

   ```bash
   openssl rand -base64 32 > calendar-feed.key
   ```

   ⚠ 作り直すと、保存してある購読の URL は開けなくなる（各カレンダーで「ファイル・URL で入れ直す」が要る）。
2. 環境変数を足して配り直す:

   ```bash
   CALENDAR_FEED_KEY_FILE=/run/calendar-feed/key   # 1 の置き場（コンテナの中のパス）
   ```

3. 確かめる:
   - 起動のログに `calendar.import.subscription_disabled` が**出ない**こと。`calendar.import.key_unreadable` が出たら
     置き場・権限・形（base64 か 16 進の 32 バイト）を見直す
   - ログイン中に `GET /api/calendars/import-settings` が `subscription_available: true`
   - 読み込み直したときはログに `calendar.import.refreshed`、失敗は `calendar.import.refresh_failed`（理由だけ。URL は出ない）

## 端末への通知（Web Push）を使えるようにしたいとき

ADR-0031。⚠ **鍵が無ければ通知は送らない**（既定。画面は「このサーバーでは使えません」）。

1. VAPID の秘密鍵（P-256）を**ホストの上で**作り、api のコンテナから読める場所に置く（値を環境変数・画面に入れない）:

   ```bash
   openssl ecparam -name prime256v1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt -out vapid.pem
   ```

   ⚠ 中身を画面・ログへ出さない。⚠ **作り直すと、いまある購読はすべて届かなくなる**（各端末で「この端末で受け取る」を押し直す）。
2. 環境変数を足して配り直す:

   ```bash
   WEB_PUSH_VAPID_PRIVATE_KEY_FILE=/run/push/vapid.pem   # 1 の置き場（コンテナの中の道）
   WEB_PUSH_SUBJECT=mailto:<連絡先>                       # 通知サービスが困ったときの連絡先
   ```

3. 確かめる:
   - 起動のログに `push.dispatch.disabled` が**出ない**こと（出たら 2 が届いていない）。`push.key_unreadable` が出たら
     置き場・権限・形（P-256 の PEM）を見直す
   - 設定 → 「端末への通知」で「この端末で受け取る」が押せること（ログイン中に `GET /api/push/config` が `enabled: true`）
   - 送ったときはログに `push.dispatch.finished`（送った数・届いた数・外した数・失敗した数）
