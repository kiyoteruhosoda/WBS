# CHANGELOG

完了した重要な変更の要約（新しいものを上に）。詳しい経緯は `history/` を参照。

## 2026-07-18

- デプロイ時に api コンテナが `ModuleNotFoundError: No module named 'src'` で再起動ループし
  unhealthy になる問題を修正。`scripts/run_db_migrations.py` / `scripts/seed_master_data.py` が
  現行の SQLAlchemy 実装に存在しない関数（`resolve_db_path` / `get_connection`）を import して
  いたのを `init_db()`（`DATABASE_URL` 準拠・冪等）ベースへ書き直し、リポジトリルートを
  import パスへ追加してスクリプト直接実行でも `src` を解決できるようにした。
  `entrypoint.sh` は依存の入っていないシステム Python ではなく venv（`/app/.venv`）の Python で
  実行するよう修正し、`deploy.sh` の migrate も同じ entrypoint 経由に統一。Dockerfile の CMD も
  entrypoint 経由に変更。seed は `ADMIN_EMAIL` が既定値以外なら初期ユーザーのメールへ反映する。
- デプロイ時の photonest 同等機能を追加補完。(1) デプロイ bundle 用 compose を
  `docker/deploy/docker-compose.yml` に切り出して唯一の出所とし、api イメージへ焼き込み、
  `deploy.sh` がデプロイのたびにイメージ内のコピーで配置先の compose を上書きするようにした
  （配置先のファイルが古いまま同じ障害が再発する事故の防止）。(2) デプロイ末尾に
  デプロイされたバージョン（`APP_VERSION` / `GIT_SHA` / `BUILD_TIME`）を表示。
  (3) ヘルスチェック失敗時の診断に api の healthcheck 履歴を追加。あわせて
  `docker compose build` にバージョンメタデータのビルド引数を渡していなかった問題
  （イメージ内の `/info` が常に `dev` / `unknown` になる）と、`--app-version` 指定時に
  build タグと save タグが食い違う問題を修正。ローカル compose には `name: wbs` を設定し、
  コンテナ等の Docker リソース名を常に wbs プレフィックスに固定。
- `.env.example` を追加（ローカル docker compose 用の全キーのコメント付きサンプル）。
  `deploy.sh` が自動生成する `.env` テンプレートもセクション構成に拡充。
- デプロイ後の手放し運用に対応（photonest と同様の構成）。全サービスに `restart: unless-stopped` と
  healthcheck を追加し、ホスト再起動・コンテナ異常終了後も自動復帰するようにした。web は
  `depends_on: condition: service_healthy` で api の healthy を待ってから起動する。
  外部からの待受ポートを web (nginx) の 1 ポートに集約し、既定を prod `8100` / stg `8101`
  （ローカル compose は `8100`）へ変更。デプロイ bundle の api はホストポートを公開せず
  `/api/` プロキシ経由のみとした。
- ビルドが `uv` 使用時にバックエンド依存を明示的に同期するよう修正（`scripts/build.py` の
  `BackendDependencies` を `uv sync --frozen` 実行に変更）。`uv run` の暗黙同期に依存すると、
  依存追加前に作られた既存 venv がそのまま使われ `prometheus_fastapi_instrumentator` を取り込めず
  テストが `ModuleNotFoundError` で失敗していた。あわせてロックファイルの ruff で検出される
  `main.py` / `migrations/env.py` の import 並び順（I001）を修正。
- フロントエンド全画面をデジタル庁デザインシステム準拠のデザイン（design handoff）へ刷新。
  デザイントークン（Primary `#0017C1`・Noto Sans JP・角丸8px 等）を `frontend/src/theme.ts` に集約し、
  サイドバー＋トップバーの共通シェル、ステータス/優先度チップ、進捗バー、ヒーロー型ダッシュボードを実装。
  ガントチャート（今日ライン・土日シェード・ステータス色バー）とカレンダー（月グリッド）を自作コンポーネント化し、
  `gantt-task-react` / `@fullcalendar/*` を依存から削除。
- フロントエンド API 層をバックエンドの実契約に修正（`/tasks` は配列返却・`status_filter` パラメータ・
  並び替えとフィルタはクライアント側、`/work-logs` パス、依存関係レスポンスの `predecessors` 形式）。
  進捗%は作業ログ由来のためダッシュボードの操作を「作業を記録」に変更。

## 2026-07-13

- DB 方針を MariaDB に確定（`decisions/ADR-0001-database-mariadb.md`）。
- 雛形のサンプル `Item` 一式（Domain / Application / Infrastructure / Presentation の
  各層とテスト）を撤去。`main.py` の `/items` ルーター登録と関連 DI・SQLite テーブル
  定義も削除。ドメイン語彙を Task Scheduler へ寄せるための前処理。

## 2026-07-13

- React 18 + TypeScript + MUI v9 + Vite フロントエンドを `frontend/` に新規作成。
  ダッシュボード・今日のタスク・タスク一覧・タスク編集・ガントチャート・カレンダー・インボックスの
  7画面を実装。TanStack Query + axios で API 通信、react-router-dom v6 でルーティング。
  `npm run build` がエラーなしで成功することを確認済み。
