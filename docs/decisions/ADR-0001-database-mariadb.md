# ADR-0001: データベースに MariaDB を採用する

- 状態: 承認
- 日付: 2026-07-13

## 背景

リポジトリの初期状態は FastAPI + SQLite の雛形だった。一方、設計書
（`docs/DesignDocument.md` 3.3.3 / 4.2）は MariaDB 10.6+ / InnoDB / utf8mb4 を前提に、
DDL・ビュー（`v_task_summary` / `v_today_tasks`）・トリガー（`trg_tasks_before_update`）・
CHECK 制約・外部キーを用いたデータモデルを定義している。MVP バックログ（T1 以降）を
起こすにあたり、実装の土台となる DB を確定する必要があった。

## 決定

**MariaDB 10.6+ を採用する。** スキーマは Alembic マイグレーションで管理し、
`ALTER TABLE` / `CREATE TABLE` の直接実行は行わない。

## 理由

- 設計書のデータモデルが MariaDB の機能（外部キー、CHECK 制約、ビュー、トリガー、
  utf8mb4 照合順序）に依存しており、これらを前提に画面・API 要件が組まれている。
- 将来のチーム利用（フェーズ2以降のマルチユーザー化）で SQLite の同時書き込み制約が
  ボトルネックになる。MVP から本番想定の RDBMS に揃える方がやり直しが少ない。
- 代替案として雛形の SQLite を継続する案も検討したが、ネイティブ ENUM・トリガー・
  ビューの再現コストと、設計書との乖離を保守し続けるコストが上回ると判断した。

## 影響

- T1（スキーマ整備）以降は MariaDB を前提に実装する。ENUM は DB ネイティブ型を使わず
  `native_enum=False`（CHECK 制約付き VARCHAR）とする。
- テストは引き続き SQLite での実行を許容しうるが、DB 固有機能（ビュー・トリガー）を
  DB 側に置くかアプリ層で再現するかは T1 着手時に確定する。
- README / `pyproject.toml` の「SQLite テンプレート」表記は、MariaDB 対応の実装
  （T1）着手時に更新する。現時点のランタイム雛形は SQLite のまま残している。
