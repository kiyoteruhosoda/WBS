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

## SSO を後から入れて、既に居る利用者を引き継ぎたいとき

⚠ **既定では、メールアドレスが同じでも既存の利用者へ寄せない**（ADR-0004）。移行のあいだ
だけ開ける。

```bash
OIDC_LINK_BY_EMAIL=true
```

⚠ **移行が済んだら戻す。** 結び付いた後の人はこの枝を通らないので、戻しても入れなくなる人は
出ない。
