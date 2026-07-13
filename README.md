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

- Web: <http://127.0.0.1:8080>
- API: <http://127.0.0.1:8000/docs>
- DB: MariaDB 10.11（UTC）

`.env` がなくても `${VAR:-default}` により起動します。初期ユーザーは開発用の `local@example.com` / `local-dev-password` を想定しています。本番では必ず環境変数で変更してください。

## API 例

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"設計レビュー","priority":5,"urgency":4}'

curl http://127.0.0.1:8000/today-tasks
```

## ビルド

```bash
./scripts/build.sh
./scripts/build.sh --target deploy --app-version local
```

- `--target api`: backend lint / test のみ実行
- `--target web`: frontend install / build のみ実行
- `--target docker`: deploy と同じ `wbs-api:<version>` / `wbs-web:<version>` イメージを build
- `--target deploy`: Docker image tar とホスト実行用 `entrypoint.sh` を `dist/deploy/` に生成
- `--skip-tests` / `--skip-frontend-install`: ローカル開発時の高速化オプション
- frontend build は開発時の lockfile 不整合を自動補正できるよう、依存解決に `npm install` を使います。
- backend build は `uv` があれば `uv run`、なければ実行中の Python に必要な dev dependencies を `pip install -e . ruff pytest httpx` で補完してから `python -m ruff` / `python -m pytest` にフォールバックします。

## テスト

```bash
uv run pytest
```
