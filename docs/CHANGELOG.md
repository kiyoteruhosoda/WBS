# CHANGELOG

完了した重要な変更の要約（新しいものを上に）。詳しい経緯は `history/` を参照。

## 2026-07-20

- 個人設定を追加。設定画面（`/settings`）から言語（日本語/英語）とタイムゾーンを変更できる
  （`users.language` 列を追加、`GET/PUT /api/settings`）。タイムゾーンはフロントの「今日」
  判定・日付表示にも反映される（バックエンドのダッシュボード集計は従来から `users.timezone` を使用）。
- フロントエンドの日英切り替え（軽量 i18n）を導入。全画面の UI 文言を
  `frontend/src/i18n/translations.ts` の辞書経由に変更。
- 設定画面にアプリ情報（バージョン・Git ハッシュ・ビルド日時・環境）を表示。
  nginx 経由で到達できるよう ops ルーター（`/info` 等）を `/api` 配下にも公開。
- 進捗率・残り時間の算出方法を変更。進捗率 = 実績時間 ÷ 見積時間（上限100%）、
  残り時間 = 見積時間 − 実績時間（下限0）とし、残り時間の直接入力を廃止
  （作成・更新 API から `remaining_hours` を削除、レスポンスでは自動計算値を返す）。
  タスク編集画面では実績時間を入力でき、変更分は作業ログとして記録される。
- ダッシュボードの「いま取り組んでいるタスク」を進行中タスク全件表示に変更（従来は1件のみ）。
- ガントチャートの初期スクロール位置を「今日」に合わせるようにした。
- 「今日」画面のバケット分類を変更。開始日が到来したタスク（期限未超過）は
  「開始済み」バケットではなく「今日」バケットに入るようにし、「開始済み」バケットを廃止
  （`DashboardUseCases.get_today_buckets` / `domain/services.py today_bucket` / フロント表示）。
- タスク編集画面で保存後、タスク詳細ではなくタスク一覧（`/tasks`）へ戻るように変更。
- デプロイ先ホスト用の `scripts/build-remote.sh` を追加（DeployBridge の同名スクリプトが原型）。
  開発コンテナ内ビルド → deploy bundle の取り出し → `./scripts/deploy.sh <MODE>` 実行までを
  ワンコマンド化し、自己更新（リポジトリ HEAD との刻印照合・差分時は exit 2 で再実行要求）にも
  対応。ホスト側の手書きスクリプトが bundle の実配置（配置 dir 直下の `scripts/deploy.sh`）と
  食い違うパス `./deploy/scripts/deploy.sh` を呼んで失敗していた問題の恒久対策。

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
