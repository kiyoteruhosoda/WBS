# Task Scheduler

個人・小規模プロジェクト向けの WBS / タスク管理 MVP です。DDD を意識し、Domain 層に状態遷移・スコア算出などの業務ルールを寄せ、Presentation 層は REST API として公開します。

## 実装済み

- タスク、カテゴリ、マイルストーン、作業ログ、依存関係、Inbox のスキーマ初期化
- タスク CRUD、論理削除、DONE 遷移時の完了時刻・残工数更新
- 進捗率、期限超過日数、優先度スコア、今日のタスク抽出
- DFS による依存関係の循環検出
- Dashboard / Today / Gantt / Weekly review 用 API
- React 18 + TypeScript + MUI + Vite + React Query + Router のフロントエンド基盤
- web / api / db の Docker Compose 分離
- `app` / `migrate` / `reset` モードの起動スクリプト
- `.env` 不在でも起動できる開発向けデフォルト設定
- IdP との SSO 連携（OIDC 認可コードフロー + PKCE）。利用者ごとにデータが分かれる

## ローカル開発

```bash
uv sync
uv run uvicorn main:app --reload
```

API: <http://127.0.0.1:8000/docs>

## Docker Compose

```bash
docker compose up --build
```

- Web: <http://127.0.0.1:8100>
- API: <http://127.0.0.1:8000/docs>
- DB: MariaDB 10.11（UTC）

全サービスに `restart: unless-stopped` と healthcheck を設定しているため、ホスト再起動やコンテナ異常終了後も自動で復帰します。

`.env` がなくても `${VAR:-default}` により起動します。設定を変える場合は `cp .env.example .env` して編集してください（全キーの説明は `.env.example` を参照）。初期ユーザーは開発用の `local@example.com` / `local-dev-password` を想定しています。本番では必ず環境変数で変更してください。

## SSO（IdP 連携）

既定の `AUTH_MODE=single_user` では認証はかからず、全リクエストが初期ユーザー 1 人の
ものとして扱われます（従来どおりの動作）。**ネットワーク越しに公開する配備では
`AUTH_MODE=oidc` にしてください。**

### 1. IdP にこのアプリを登録する

OpenID Connect の Confidential client（または PKCE のみの Public client）として登録し、
リダイレクト URI に `https://<このアプリのホスト>/api/auth/callback` を許可します。
必要なスコープは `openid email profile` です。

### 2. 環境変数を設定する

```bash
AUTH_MODE=oidc
OIDC_ISSUER=https://idp.example.com/realms/wbs
OIDC_CLIENT_ID=wbs
OIDC_CLIENT_SECRET=...                  # public client なら不要
OIDC_REDIRECT_URI=https://wbs.example.com/api/auth/callback
OIDC_ALLOWED_EMAIL_DOMAINS=example.com  # テナント共用の IdP では必ず設定する
```

`OIDC_ISSUER` からディスカバリ文書
（`<issuer>/.well-known/openid-configuration`）を自動で取得するため、
認可・トークン・JWKS の各エンドポイントを個別に書く必要はありません。
全キーの説明は `.env.example` を参照してください。設定が欠けている場合、アプリは
起動時にエラーで停止します（設定漏れのまま「認証なしで公開」にならないように）。

### 3. 動作を確かめる

| したいこと | 方法 |
|---|---|
| SSO が有効か確認する | `curl https://<host>/api/auth/config` |
| ログインする | ブラウザで画面を開く（未ログインならログイン画面が出る） |
| ログイン中の利用者を見る | `GET /api/auth/me` |
| ログアウトする | 画面右上のアカウント → ログアウト |

利用者は初回ログイン時に自動で作られます。あらかじめ登録した人だけを通したい場合は
`OIDC_AUTO_PROVISION=false` にしてください。

### 既存のデプロイに後から入れる場合

`scripts/deploy.sh` が `.env` テンプレートを作るのは**配置先に `.env` が無いときだけ**です。
すでに動いている stg / prod では既存の `.env` はそのまま残るため、上記のキーを手で
追記してから再デプロイしてください。追記せずに再デプロイすると、認証は掛からないまま
（`AUTH_MODE=single_user`）で起動します。

なお、`.env` に書いたキーは compose の `environment:` に並んでいるものだけがコンテナへ
届きます。設定キーを増やしたときは `docker-compose.yml` と
`docker/deploy/docker-compose.yml` の両方に足してください（`tests/unit/scripts/test_auth_env_passthrough.py`
が食い違いを検出します）。

### IdP の前段に WAF / CDN がある場合

このアプリが IdP へ出す HTTP には `User-Agent: wbs-oidc/1.0` を必ず付けています
（`src/infrastructure/auth/idp_http.py`）。ライブラリ既定の UA を自動化ツールとして
弾く WAF があるためです。

⚠ **JWKS だけ経路が違います。** ディスカバリ・トークン・userinfo は `httpx` ですが、
JWKS は PyJWT の `PyJWKClient` が **`urllib`** で取りに行きます。JWKS だけが弾かれると
**トークン交換までは成功したまま ID トークンの署名検証で落ちる**ので、画面には
「ログインに失敗しました」としか出ず、サーバのログにも例外が残りません
（コールバックが握ってログイン画面へ戻すため）。切り分けは IdP 側 / WAF 側のログか、
次で確認します。

```bash
# api コンテナの中から。403 なら UA が弾かれている
python -c "import urllib.request; print(urllib.request.urlopen('<jwks_uri>').status)"
```

### 覚えておくこと

- 利用者の同一性は IdP の `(iss, sub)` で決まります。IdP 側でメールアドレスが
  変わっても同じ利用者として扱われます。
- SSO 導入前から居る利用者は、初回 SSO ログイン時に**検証済みメールアドレスの一致**で
  既存アカウントに紐づきます。
- `AUTH_COOKIE_SECURE=true`（既定）のセッション Cookie は https でしか送られません。
  http の開発環境では `false` にしてください。

## API 例

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"設計レビュー","priority":5,"urgency":4}'

curl http://127.0.0.1:8000/today-tasks
```

## ビルド

```bash
./scripts/build.sh --app-version local
```

- `--target api`: backend lint / test のみ実行
- `--target web`: frontend install / build のみ実行
- `--target docker`: deploy と同じ `wbs-api:<version>` / `wbs-web:<version>` イメージを build
- `--target deploy`: Docker image tar と stg/prod 対応のホスト実行用 `scripts/deploy.sh` を `dist/deploy/` に生成（デフォルト）
- `--skip-tests` / `--skip-frontend-install`: ローカル開発時の高速化オプション
- frontend build は開発時の lockfile 不整合を自動補正できるよう、依存解決に `npm install` を使います。
- backend build は `uv` があれば `uv run`、なければ実行中の Python に必要な dev dependencies を `pip install -e . ruff pytest httpx` で補完してから `python -m ruff` / `python -m pytest` にフォールバックします。

## テスト

```bash
uv run pytest
```
