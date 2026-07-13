# Progress

進行中・未着手タスクのみを管理する（完了したら本ファイルから削除し、必要なら
`CHANGELOG.md` / `history/` へ移す）。バックログは `docs/DesignDocument.md` の
MVP スコープ（10章）から起こしたもの。

確定した前提:

- **DB は MariaDB 10.6+**（設計書 3.3.3 / 4.2、判断は `decisions/ADR-0001-database-mariadb.md`）。
- 雛形のサンプル `Item` 一式は撤去済み（`CHANGELOG.md` 参照）。

- 状態: ⬜未着手 / 🚧進行中 / 🟡要判断
- 影響度・重要度・難易度・工数: 大 / 中 / 小
- バックログは「優先」列の昇順（1 が最優先）。

## バックログ

| 優先 | # | 概要 | 状態 | 影響度 | 重要度 | 難易度 | 工数 |
|---|---|---|---|---|---|---|---|
| 1 | T1 | スキーマ・マイグレーション整備（users/categories/milestones/tasks/work_logs/task_dependencies/inbox_items） | ⬜未着手 | 大 | 大 | 中 | 大 |
| 2 | T2 | Domain 層エンティティ・値オブジェクト・状態遷移（TODO→DOING→DONE ほか） | ⬜未着手 | 大 | 大 | 中 | 大 |
| 3 | T3 | 進捗率・優先度スコアの算出ロジック | ⬜未着手 | 中 | 大 | 中 | 中 |
| 4 | T4 | 「今日のタスク」抽出ロジック（v_today_tasks 相当） | ⬜未着手 | 中 | 大 | 中 | 中 |
| 5 | T5 | 依存関係の循環検出（DFS） | ⬜未着手 | 中 | 中 | 大 | 中 |
| 6 | T6 | タスク CRUD API（階層・論理削除対応） | ⬜未着手 | 大 | 大 | 中 | 大 |
| 7 | T7 | 作業ログ API（見積・実績・残の管理） | ⬜未着手 | 中 | 大 | 小 | 中 |
| 8 | T8 | マイルストーン API | ⬜未着手 | 中 | 中 | 小 | 中 |
| 9 | T9 | カテゴリ API | ⬜未着手 | 小 | 中 | 小 | 小 |
| 10 | T10 | 依存関係 API（循環チェック連携） | ⬜未着手 | 中 | 中 | 中 | 中 |
| 11 | T11 | Inbox API（タスク化変換フロー含む） | ⬜未着手 | 中 | 中 | 中 | 中 |
| 12 | T12 | ダッシュボード API（today / kpi 集計） | ⬜未着手 | 中 | 大 | 中 | 中 |
| 13 | T13 | ガント表示用 API | ⬜未着手 | 中 | 中 | 中 | 中 |
| 14 | T14 | 週次レビュー集計 API | ⬜未着手 | 小 | 中 | 中 | 中 |
| 15 | T15 | エラー形式の統一（RFC 7807 Problem Details） | ⬜未着手 | 中 | 中 | 小 | 小 |
| 16 | T16 | フロントエンド基盤（React18+TS+MUI+Vite+React Query+Router） | ⬜未着手 | 大 | 大 | 中 | 大 |
| 17 | T17 | ダッシュボード画面 | ⬜未着手 | 中 | 大 | 中 | 中 |
| 18 | T18 | 今日のタスク画面 | ⬜未着手 | 中 | 大 | 小 | 中 |
| 19 | T19 | タスク一覧画面（フィルタ・ソート） | ⬜未着手 | 中 | 大 | 中 | 中 |
| 20 | T20 | タスク編集画面（Markdown メモ含む） | ⬜未着手 | 中 | 大 | 中 | 大 |
| 21 | T21 | ガントチャート画面（WBS＋依存矢印） | ⬜未着手 | 中 | 中 | 大 | 大 |
| 22 | T22 | カレンダー画面（月表示） | ⬜未着手 | 小 | 中 | 中 | 中 |
| 23 | T23 | Inbox 画面 | ⬜未着手 | 小 | 中 | 小 | 中 |
| 24 | T24 | マイルストーン画面 | ⬜未着手 | 小 | 中 | 小 | 中 |
| 25 | T25 | 週次レビュー画面 | ⬜未着手 | 小 | 中 | 小 | 中 |
| 26 | T26 | Docker Compose 構成の分離（web / api(RESTful) / db の3コンテナ化） | ⬜未着手 | 大 | 大 | 中 | 大 |
| 27 | T27 | DB バックエンドの DI 化（MariaDB / SQLite を注入で切替。テストは SQLite） | ⬜未着手 | 大 | 大 | 中 | 中 |
| 28 | T28 | デプロイ用スクリプト整備（reset / migrate / app モードで DB・ストレージ状態を更新） | ⬜未着手 | 大 | 大 | 中 | 大 |
| 29 | T29 | ゼロコンフィグ起動（何も設定しなくてもログイン画面が表示される） | ⬜未着手 | 大 | 大 | 中 | 中 |

## 詳細

1. **T1（スキーマ）** — Alembic マイグレーションで管理（`ALTER`/`CREATE` の直接実行禁止）。
   `tasks` の CHECK 制約（priority/urgency 1–5、日付整合、自己参照禁止）を移植する。ENUM は
   ネイティブ型を使わず `native_enum=False`。ビュー `v_task_summary` / `v_today_tasks` と
   トリガー `trg_tasks_before_update` を DB 側に置くかアプリ層で再現するかは本タスク着手時に確定する。
2. **T4（今日のタスク）** — 抽出条件は設計書 5.3、bucket 分類とスコア計算を含む。ビューを
   使わない場合は同等のクエリをリポジトリ層で実装する。
3. **T26（Compose 分離）** — 現状は単一 `Dockerfile` のみ。web（フロント配信）/ api（RESTful
   バックエンド）/ db（MariaDB）をコンテナ分割し `docker-compose.yml` で束ねる。db は
   スキーマを焼き込まない素の MariaDB（UTC 固定）とし、スキーマ構築は api コンテナ起動時の
   マイグレーションで行う。FlaskApp の `docker-compose.yml` / `scripts/entrypoint.sh` /
   `db/Dockerfile` を参考にする。
4. **T27（DB の DI 化）** — 接続先（MariaDB / SQLite）を `settings` の DB URL と DI で切替え、
   Domain / Application 層は接続実装に依存しない。テスト（`tests/unit` `tests/integration`）は
   SQLite を使う。`BigInteger` は既存方針どおり `with_variant(Integer, "sqlite")`、ENUM は
   `native_enum=False` を守り両バックエンドで動くようにする。
5. **T28（デプロイスクリプト）** — FlaskApp の `scripts/`（`deploy.sh` / `entrypoint.sh` /
   `run_db_migrations.py` / `seed_master_data.py`）を参考に、`app` / `migrate` / `reset` の
   3モードを用意する。`app`=アプリのみ更新、`migrate`=`alembic upgrade head`（既存データ保持）、
   `reset`=DB・ストレージを削除して init_master + seed_master_data で再構築（破壊的）。
   `scripts/README.md` に現在の挙動を記載する。
6. **T29（ゼロコンフィグ起動）** — `.env` 不在でも `docker-compose.yml` の `${VAR:-default}` と
   `system_settings_defaults.py` の既定値で起動し、初期管理者（`shared/domain/auth/master_data.py`）
   が seed されて **何も設定しなくてもログイン画面が出る**状態にする。既定資格情報は開発向けである
   ことを README に明記する。
