# OPERATIONS

操作手順だけを置く。なぜそうなっているかは `decisions/`（ADR）、過去の経緯は `CHANGELOG.md`。

## ログインのトークンの署名鍵を用意したいとき（`AUTH_MODE=oidc` では必須）

無いと起動しない（ADR-0069）。k8s では、ホストの上で乱数を作ってその場で封印する（平文を残さない）:

```bash
head -c 48 /dev/urandom | base64 -w0 | sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubeseal --raw \
  --namespace <namespace> --name wbs-session --scope strict \
  --controller-namespace kube-system --controller-name sealed-secrets-controller
```

出た暗号文を SealedSecret の `signing-key` に書き、`/run/session/signing-key` へ読み取り専用で置いて `SESSION_SIGNING_KEY_FILE=/run/session/signing-key` を渡す。

⚠ **鍵を替えると全員が 1 回ログインし直す。** ログアウトの札とリフレッシュトークンも読めなくなる（控えの行は期限で消える）。

## ログインの寿命を短くして確かめたいとき

`ACCESS_TOKEN_EXPIRES_SECONDS` と `REFRESH_TOKEN_EXPIRES_SECONDS` を設定して配り直す（既定は 300 と 1209600）。⚠ 使い回しの見分けの 30 秒は固定（`REUSE_GRACE`）なので、リフレッシュの寿命は 30 秒より長くする。

使い回しの記録は `kubectl -n <namespace> logs deploy/api | grep refresh_token.reused`。

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

## SSO を後から入れて、既に居る利用者を引き継ぎたいとき

⚠ **既定では、メールアドレスが同じでも既存の利用者へ寄せない**（ADR-0004）。移行のあいだ
だけ開ける。

```bash
OIDC_LINK_BY_EMAIL=true
```

⚠ **移行が済んだら戻す。** 結び付いた後の人はこの枝を通らないので、戻しても入れなくなる人は
出ない。

## いちばん上のプロジェクトを作れる人を足したい・外したいとき

相手に 1 度 WBS へログインしてもらってから、api の中で付ける（ADR-0065）。⚠ 中の素の `python` にはアプリの部品が無いので `.venv/bin/python` で流す。

```bash
kubectl -n wbs-prod exec deploy/api -- sh -c 'cd /app && .venv/bin/python scripts/grant_project_creator.py <メール>'            # 付ける
kubectl -n wbs-prod exec deploy/api -- sh -c 'cd /app && .venv/bin/python scripts/grant_project_creator.py <メール> --revoke'   # 外す
```

外しても、もう作った根の管理者のまま。根を手放させたいときは、その根のメンバーの画面で管理者を替える。

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
