
# タスクスケジューラ設計書

# 1. 概要

## 1.1 システム名

**Task Scheduler**

## 1.2 目的

個人および小規模プロジェクト向けのタスク管理システムを提供する。

MVPのゴールは「タスクを登録すること」ではなく、**「今日やるべきことが一目で分かり、タスクの見落としをゼロに近づけること」** とする。

## 1.3 主な要件

* 今日実施すべきタスクを即座に把握できる
* タスクの見落としを防止する
* 工数管理（見積・実績・残）を行う
* WBS（階層化）およびマイルストーン管理を行う
* 将来的なチーム利用へ拡張可能な構成とする

## 1.4 想定利用者

* **MVP**: 個人利用（単一ユーザー）
* **フェーズ2以降**: 小規模チーム（マルチユーザー）

***

# 2. システム要件

## 2.1 機能要件

### 2.1.1 MVP必須要件

| ID   | 要件                |
| ---- | ----------------- |
| F-01 | 今日やるべきタスクが一目で分かる  |
| F-02 | 期限超過タスクを見逃さない     |
| F-03 | 工数管理（見積・実績・残）ができる |
| F-04 | タスクを階層化できる（親子タスク） |
| F-05 | ガントチャート形式で表示できる   |
| F-06 | Markdownでメモを残せる   |
| F-07 | Inboxで思いつきを即メモできる |
| F-08 | マイルストーンで期日管理できる   |

### 2.1.2 フェーズ2要件

* **デスクトップ通知**（朝通知・期限通知）
* Microsoft To Do 連携
* Outlook 予定表連携
* チーム共有（マルチユーザー化）

### 2.1.3 フェーズ3要件

* AIによる優先度提案
* AIによるWBS自動生成
* 工数予測・遅延予測

## 2.2 非機能要件

| 分類     | 項目    | MVP方針             | 将来                |
| ------ | ----- | ----------------- | ----------------- |
| 性能     | ページ表示 | 1秒以内（〜1万タスク）      | 3秒以内（〜10万タスク）     |
| 認証     | ログイン  | ローカル固定ユーザー        | OIDC (Entra ID連携) |
| 認可     | データ分離 | `user_id` カラム保持のみ | ユーザー別アクセス制御       |
| タイムゾーン | 保存形式  | DB は UTC 保存       | 同左                |
| タイムゾーン | 表示    | JST 固定            | ユーザー設定            |
| 文字コード  | 全般    | utf8mb4（絵文字対応）    | 同左                |
| ログ     | アプリログ | ファイル出力 (JSON)     | 集約ログ基盤            |
| バックアップ | DB    | 日次ダンプ             | 継続的レプリケーション       |
| 可用性    | 稼働率   | ベストエフォート          | 99.5%             |

***

# 3. アーキテクチャ

## 3.1 システム構成（MVP）

```text
┌─────────────────────────┐
│  React Frontend (SPA)   │
│  TypeScript + MUI       │
└───────────┬─────────────┘
            │ REST API (JSON)
┌───────────▼─────────────┐
│  FastAPI Backend        │
│  Python 3.12            │
│  SQLAlchemy + Alembic   │
└───────────┬─────────────┘
            │ SQL (mariadb-connector)
┌───────────▼─────────────┐
│  MariaDB 10.6+          │
│  InnoDB / utf8mb4       │
└─────────────────────────┘

  すべて Docker Compose で起動
```

## 3.2 フェーズ2構成（通知追加時）

```text
┌───────────────┐   ┌─────────────────────┐
│  React SPA    │   │  Notification       │
│               │◄──┤  Worker             │
└───────┬───────┘   │  (Desktop Notify)   │
        │           └──────────▲──────────┘
        │                      │
┌───────▼──────────────────────┴──────────┐
│  FastAPI Backend                        │
│  + APScheduler (定期ジョブ)             │
└───────────────────┬─────────────────────┘
                    │
            ┌───────▼───────┐
            │  MariaDB      │
            └───────────────┘
```

## 3.3 技術スタック

### 3.3.1 Frontend

| 項目       | 採用技術                         |
| -------- | ---------------------------- |
| フレームワーク  | React 18                     |
| 言語       | TypeScript 5                 |
| UI       | Material UI (MUI) v5         |
| 状態管理     | React Query (TanStack Query) |
| ルーティング   | React Router                 |
| カレンダー    | FullCalendar                 |
| ガントチャート  | gantt-task-react             |
| Markdown | react-markdown               |
| ビルド      | Vite                         |

### 3.3.2 Backend

| 項目          | 採用技術           |
| ----------- | -------------- |
| 言語          | Python 3.12    |
| Web フレームワーク | FastAPI        |
| ORM         | SQLAlchemy 2.x |
| マイグレーション    | Alembic        |
| バリデーション     | Pydantic v2    |
| 認証（フェーズ2）   | Authlib (OIDC) |

### 3.3.3 Database

| 項目    | 採用技術                            |
| ----- | ------------------------------- |
| RDBMS | MariaDB 10.6+                   |
| エンジン  | InnoDB                          |
| 文字コード | utf8mb4 / utf8mb4\_0900\_ai\_ci |

### 3.3.4 Infra

| 項目            | 採用技術                    |
| ------------- | ----------------------- |
| コンテナ          | Docker / Docker Compose |
| リバースプロキシ（拡張時） | Nginx / Traefik         |

***

# 4. データモデル

## 4.1 ER図（論理）

```text
users ────┬──── categories
          │
          ├──── milestones
          │
          ├──── tasks ─┬── work_logs
          │            │
          │            ├── task_dependencies (自己参照)
          │            │
          │            └── parent_task_id (自己参照)
          │
          └──── inbox_items ──── converted_task_id → tasks
```

## 4.2 DDL（MariaDB版）

### 4.2.1 前提設定

```sql
CREATE DATABASE IF NOT EXISTS task_scheduler
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE task_scheduler;
SET NAMES utf8mb4;
SET time_zone = '+00:00';
```

### 4.2.2 users

```sql
CREATE TABLE users (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email           VARCHAR(255)    NOT NULL,
    display_name    VARCHAR(100)    NOT NULL,
    timezone        VARCHAR(64)     NOT NULL DEFAULT 'Asia/Tokyo',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                    ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  ROW_FORMAT=DYNAMIC
  COMMENT='ユーザーマスタ';

INSERT INTO users (id, email, display_name)
VALUES (1, 'local@example.com', 'ローカルユーザー');
```

### 4.2.3 milestones

```sql
CREATE TABLE milestones (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id         BIGINT UNSIGNED NOT NULL,
    name            VARCHAR(200)    NOT NULL,
    due_date        DATE            NULL,
    description     TEXT            NULL,
    deleted_at      DATETIME(3)     NULL,
    created_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                    ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_milestones_user_due (user_id, due_date),
    KEY idx_milestones_deleted (deleted_at),
    CONSTRAINT fk_milestones_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  ROW_FORMAT=DYNAMIC COMMENT='マイルストーン';
```

### 4.2.4 categories

```sql
CREATE TABLE categories (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id         BIGINT UNSIGNED NOT NULL,
    name            VARCHAR(100)    NOT NULL,
    color           VARCHAR(7)      NULL COMMENT 'HEX #RRGGBB',
    sort_order      INT             NOT NULL DEFAULT 0,
    deleted_at      DATETIME(3)     NULL,
    created_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                    ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_categories_user_name (user_id, name),
    CONSTRAINT fk_categories_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_categories_color
        CHECK (color IS NULL OR color REGEXP '^#[0-9A-Fa-f]{6}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  ROW_FORMAT=DYNAMIC COMMENT='カテゴリマスタ';
```

### 4.2.5 tasks

```sql
CREATE TABLE tasks (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id             BIGINT UNSIGNED NOT NULL,
    title               VARCHAR(500)    NOT NULL,
    category_id         BIGINT UNSIGNED NULL,
    priority            TINYINT UNSIGNED NOT NULL DEFAULT 3
                        COMMENT '1=最低, 5=最高',
    urgency             TINYINT UNSIGNED NOT NULL DEFAULT 3
                        COMMENT '1=最低, 5=最高',
    status              ENUM('TODO','DOING','WAITING','DONE','CANCELLED')
                        NOT NULL DEFAULT 'TODO',
    start_date          DATE            NULL,
    due_date            DATE            NULL,
    estimated_hours     DECIMAL(6,2)    NULL,
    remaining_hours     DECIMAL(6,2)    NULL,
    memo                MEDIUMTEXT      NULL COMMENT 'Markdown',
    parent_task_id      BIGINT UNSIGNED NULL,
    milestone_id        BIGINT UNSIGNED NULL,
    completed_at        DATETIME(3)     NULL,
    deleted_at          DATETIME(3)     NULL,
    created_at          DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                        ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_tasks_user_status_due (user_id, status, due_date),
    KEY idx_tasks_user_due (user_id, due_date),
    KEY idx_tasks_user_start (user_id, start_date),
    KEY idx_tasks_parent (parent_task_id),
    KEY idx_tasks_milestone (milestone_id),
    KEY idx_tasks_category (category_id),
    KEY idx_tasks_deleted (deleted_at),
    CONSTRAINT fk_tasks_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_tasks_category
        FOREIGN KEY (category_id) REFERENCES categories(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_tasks_parent
        FOREIGN KEY (parent_task_id) REFERENCES tasks(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_tasks_milestone
        FOREIGN KEY (milestone_id) REFERENCES milestones(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT chk_tasks_priority CHECK (priority BETWEEN 1 AND 5),
    CONSTRAINT chk_tasks_urgency  CHECK (urgency  BETWEEN 1 AND 5),
    CONSTRAINT chk_tasks_hours_est CHECK (estimated_hours IS NULL OR estimated_hours >= 0),
    CONSTRAINT chk_tasks_hours_rem CHECK (remaining_hours IS NULL OR remaining_hours >= 0),
    CONSTRAINT chk_tasks_dates    CHECK (
        start_date IS NULL OR due_date IS NULL OR start_date <= due_date
    ),
    CONSTRAINT chk_tasks_self_parent CHECK (parent_task_id IS NULL OR parent_task_id <> id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  ROW_FORMAT=DYNAMIC COMMENT='タスク';
```

### 4.2.6 work\_logs

```sql
CREATE TABLE work_logs (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id         BIGINT UNSIGNED NOT NULL,
    task_id         BIGINT UNSIGNED NOT NULL,
    work_date       DATE            NOT NULL,
    hours           DECIMAL(5,2)    NOT NULL,
    memo            TEXT            NULL,
    deleted_at      DATETIME(3)     NULL,
    created_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                    ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_worklogs_task_date (task_id, work_date),
    KEY idx_worklogs_user_date (user_id, work_date),
    KEY idx_worklogs_deleted (deleted_at),
    CONSTRAINT fk_worklogs_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_worklogs_task
        FOREIGN KEY (task_id) REFERENCES tasks(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_worklogs_hours CHECK (hours > 0 AND hours <= 24)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  ROW_FORMAT=DYNAMIC COMMENT='作業ログ';
```

### 4.2.7 task\_dependencies

```sql
CREATE TABLE task_dependencies (
    predecessor_task_id BIGINT UNSIGNED NOT NULL,
    successor_task_id   BIGINT UNSIGNED NOT NULL,
    dependency_type     ENUM('FS','SS','FF','SF') NOT NULL DEFAULT 'FS',
    lag_days            INT             NOT NULL DEFAULT 0,
    created_at          DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (predecessor_task_id, successor_task_id),
    KEY idx_dep_successor (successor_task_id),
    CONSTRAINT fk_dep_predecessor
        FOREIGN KEY (predecessor_task_id) REFERENCES tasks(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_dep_successor
        FOREIGN KEY (successor_task_id) REFERENCES tasks(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_dep_not_self CHECK (predecessor_task_id <> successor_task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  ROW_FORMAT=DYNAMIC COMMENT='タスク依存関係';
```

### 4.2.8 inbox\_items

```sql
CREATE TABLE inbox_items (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id           BIGINT UNSIGNED NOT NULL,
    title             VARCHAR(500)    NOT NULL,
    memo              TEXT            NULL,
    converted_task_id BIGINT UNSIGNED NULL,
    converted_at      DATETIME(3)     NULL,
    deleted_at        DATETIME(3)     NULL,
    created_at        DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at        DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                      ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_inbox_user_created (user_id, created_at),
    KEY idx_inbox_converted (converted_task_id),
    CONSTRAINT fk_inbox_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_inbox_task
        FOREIGN KEY (converted_task_id) REFERENCES tasks(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  ROW_FORMAT=DYNAMIC COMMENT='Inbox';
```

## 4.3 ビュー

### 4.3.1 v\_task\_summary（進捗率つきタスク集計）

```sql
CREATE OR REPLACE VIEW v_task_summary AS
SELECT
    t.id AS task_id,
    t.user_id,
    t.title,
    t.status,
    t.priority,
    t.urgency,
    t.start_date,
    t.due_date,
    t.estimated_hours,
    t.remaining_hours,
    COALESCE(SUM(wl.hours), 0) AS actual_hours,
    CASE
        WHEN t.status = 'DONE' THEN 100.0
        WHEN COALESCE(SUM(wl.hours), 0) = 0
             AND COALESCE(t.remaining_hours, 0) = 0 THEN 0.0
        ELSE ROUND(
            COALESCE(SUM(wl.hours), 0) * 100.0
            / (COALESCE(SUM(wl.hours), 0) + COALESCE(t.remaining_hours, 0)),
            1
        )
    END AS progress_percent,
    CASE
        WHEN t.due_date IS NULL OR t.status IN ('DONE','CANCELLED') THEN 0
        WHEN t.due_date < CURRENT_DATE()
            THEN DATEDIFF(CURRENT_DATE(), t.due_date)
        ELSE 0
    END AS overdue_days
FROM tasks t
LEFT JOIN work_logs wl
    ON wl.task_id = t.id AND wl.deleted_at IS NULL
WHERE t.deleted_at IS NULL
GROUP BY t.id;
```

### 4.3.2 v\_today\_tasks（今日のタスク抽出）

```sql
CREATE OR REPLACE VIEW v_today_tasks AS
SELECT
    t.*,
    CASE
        WHEN t.due_date < CURRENT_DATE() THEN 'OVERDUE'
        WHEN t.due_date = CURRENT_DATE() THEN 'TODAY'
        WHEN t.due_date = DATE_ADD(CURRENT_DATE(), INTERVAL 1 DAY) THEN 'TOMORROW'
        WHEN t.status = 'DOING' THEN 'DOING'
        WHEN t.start_date <= CURRENT_DATE() THEN 'STARTED'
        ELSE 'OTHER'
    END AS bucket,
    (t.priority * 100
        + t.urgency * 80
        + LEAST(
            CASE
                WHEN t.due_date IS NOT NULL AND t.due_date < CURRENT_DATE()
                    THEN DATEDIFF(CURRENT_DATE(), t.due_date)
                ELSE 0
            END, 7) * 100
    ) AS score
FROM tasks t
WHERE t.deleted_at IS NULL
  AND t.status NOT IN ('DONE','CANCELLED')
  AND (
        (t.due_date IS NOT NULL AND t.due_date <= DATE_ADD(CURRENT_DATE(), INTERVAL 1 DAY))
        OR t.status = 'DOING'
        OR (t.start_date IS NOT NULL AND t.start_date <= CURRENT_DATE())
  );
```

## 4.4 トリガー

```sql
DELIMITER $$

CREATE TRIGGER trg_tasks_before_update
BEFORE UPDATE ON tasks
FOR EACH ROW
BEGIN
    IF NEW.status = 'DONE' AND OLD.status <> 'DONE' THEN
        SET NEW.completed_at = CURRENT_TIMESTAMP(3);
        SET NEW.remaining_hours = 0;
    END IF;
    IF NEW.status <> 'DONE' AND OLD.status = 'DONE' THEN
        SET NEW.completed_at = NULL;
    END IF;
END$$

DELIMITER ;
```

***

# 5. ビジネスロジック

## 5.1 進捗率

```text
DONE の場合                → 100%
実績=0 かつ 残=0 の場合    → 0%
それ以外                   → 実績 / (実績 + 残) × 100
```

**例：** 実績 20h、残 10h → 20 / (20 + 10) = **66.7%**

## 5.2 優先度スコア

```text
score = priority × 100
      + urgency × 80
      + min(overdue_days, 7) × 100
```

**設計意図：**

* overdue の重みが暴走しないよう **7日で上限**
* urgency の重みを 50 → 80 に引き上げ、priorityとのバランスを改善

**例：** 優先度=5、緊急度=5、2日遅延 → 500 + 400 + 200 = **1100**

## 5.3 今日のタスク抽出

**基本フィルタ：**

```text
deleted_at IS NULL
AND status NOT IN ('DONE', 'CANCELLED')
```

**カテゴリ分類（優先順位順、重複時は上位カテゴリ優先）：**

| # | カテゴリ | 条件                                      |
| - | ---- | --------------------------------------- |
| 1 | 期限超過 | `due_date < today`                      |
| 2 | 今日期限 | `due_date = today`                      |
| 3 | 明日期限 | `due_date = tomorrow`                   |
| 4 | 実施中  | `status = DOING`                        |
| 5 | 開始済み | `start_date <= today AND status = TODO` |

## 5.4 状態遷移

```text
TODO ──► DOING ──► DONE
  │        │
  │        └──► WAITING ──► DOING
  │
  └──► CANCELLED
```

* `DONE` 遷移時：`completed_at` 自動セット、`remaining_hours = 0`
* `DONE → 他` 遷移時：`completed_at` クリア

## 5.5 依存関係の循環検出

* **DB層**: 自己参照（自分→自分）のみ CHECK 制約でブロック
* **アプリ層**: 依存追加時にグラフ探索（DFS）で循環検出

***

# 6. 画面設計

## 6.1 画面一覧

| #    | 画面      | MVP | 説明             |
| ---- | ------- | :-: | -------------- |
| 6.2  | ダッシュボード |  ✅  | KPI + 今日のタスク要約 |
| 6.3  | 今日のタスク  |  ✅  | 今日集中すべきタスク     |
| 6.4  | タスク一覧   |  ✅  | 全タスクの検索・フィルタ   |
| 6.5  | タスク編集   |  ✅  | 新規作成・編集フォーム    |
| 6.6  | ガントチャート |  ✅  | WBS＋依存関係の可視化   |
| 6.7  | カレンダー   |  ✅  | 月表示            |
| 6.8  | Inbox   |  ✅  | 素早い着想メモ        |
| 6.9  | マイルストーン |  ✅  | 一覧・編集          |
| 6.10 | 週次レビュー  |  ✅  | 完了・遅延の振り返り     |

## 6.2 ダッシュボード

**KPI:**

* 総タスク数 / 未完了数 / 期限超過数
* 今週完了数 / 今週投入工数

**セクション:**

* 期限超過 / 今日期限 / 明日期限 / 実施中 / 待機中

## 6.3 今日のタスク

「今日やるべきことだけ」に集中する画面。5.3 の抽出条件でカテゴリ別に表示。

```text
【期限超過】
  認証設計レビュー  (2日遅延)
【今日期限】
  工数提出
【明日期限】
  見積レビュー
【実施中】
  移行設計
```

## 6.4 タスク一覧

* **フィルタ**: カテゴリ / ステータス / 優先度 / マイルストーン / 期間
* **ソート**: 優先度スコア / 期限 / 更新日
* **表示列**: タイトル / カテゴリ / 期限 / 進捗率 / ステータス

## 6.5 タスク編集

編集項目：

* タイトル / カテゴリ / 優先度 / 緊急度
* 開始日 / 期限
* 見積工数 / 残工数
* 親タスク / マイルストーン / 依存タスク
* メモ（Markdown）

## 6.6 ガントチャート

* 表示: WBS（親子）＋ 依存関係矢印
* 操作: ドラッグで期間変更、クリックで編集画面へ

## 6.7 カレンダー

* 月表示
* 表示対象: タスク（期限日）＋ マイルストーン

## 6.8 Inbox

* ワンクリックで素早く登録
* 一覧から選択して「タスク化」ボタンでタスクへ変換
* 変換元は `converted_task_id` で追跡

## 6.9 マイルストーン

* 一覧・編集
* 各マイルストーンに紐づくタスクを一覧表示

## 6.10 週次レビュー

**表示項目：**

* 完了件数 / 新規登録件数 / 期限超過件数
* 投入工数（合計・カテゴリ別）

***

# 7. 通知機能（フェーズ2）

MVP では**未実装**。将来的にデスクトップ通知を実装する。

## 7.1 想定通知チャネル

**Web Notifications API** によるブラウザ経由のデスクトップ通知。

* OS ネイティブ通知（Windows / macOS / Linux）
* 権限リクエスト（`Notification.requestPermission()`）が必要

## 7.2 想定通知種別

| #   | 種別        | タイミング          | 内容                                |
| --- | --------- | -------------- | --------------------------------- |
| N-1 | 朝通知       | 毎日 9:00        | 今日のタスク要約（期限超過n件 / 今日期限n件 / 実施中n件） |
| N-2 | 期限通知      | 3日前 / 1日前 / 当日 | タスクごとに通知                          |
| N-3 | マイルストーン通知 | 1週間前 / 3日前     | マイルストーン期日                         |

## 7.3 想定実装構成

```text
FastAPI + APScheduler
    ↓ 定期ジョブ（毎日9時ほか）
    ↓ 通知キューに登録
Notification Worker
    ↓ WebSocket / Server-Sent Events
Frontend (Service Worker)
    ↓ Web Notifications API
デスクトップ通知
```

## 7.4 通知テーブル（フェーズ2で追加予定）

```sql
-- 実装時に追加
CREATE TABLE notifications (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    kind ENUM('MORNING','DUE_DATE','MILESTONE') NOT NULL,
    task_id BIGINT UNSIGNED NULL,
    scheduled_at DATETIME(3) NOT NULL,
    sent_at DATETIME(3) NULL,
    payload JSON NULL,
    PRIMARY KEY (id)
    -- 詳細は実装時に確定
);
```

***

# 8. API設計

## 8.1 基本方針

* **REST + JSON**
* **OpenAPI 3.1**（FastAPI が自動生成）
* **エラー形式**: RFC 7807 (Problem Details for HTTP APIs)
* **ページング**: `?page=1&per_page=50` または `?cursor=xxx`
* **認証（MVP）**: なし（固定 user\_id=1）
* **認証（フェーズ2）**: Bearer Token (OIDC)

## 8.2 エンドポイント一覧（MVP）

### 8.2.1 タスク

| メソッド   | パス                | 説明                 |
| ------ | ----------------- | ------------------ |
| GET    | `/api/tasks`      | 一覧（フィルタ・ソート・ページング） |
| POST   | `/api/tasks`      | 作成                 |
| GET    | `/api/tasks/{id}` | 詳細取得               |
| PUT    | `/api/tasks/{id}` | 更新                 |
| PATCH  | `/api/tasks/{id}` | 部分更新（ステータス変更など）    |
| DELETE | `/api/tasks/{id}` | 論理削除               |

**クエリパラメータ例：**

```text
GET /api/tasks?status=TODO&category_id=3&sort=-priority,due_date&page=1&per_page=50
```

### 8.2.2 ダッシュボード

| メソッド | パス                     | 説明            |
| ---- | ---------------------- | ------------- |
| GET  | `/api/dashboard/today` | 今日のタスク（カテゴリ別） |
| GET  | `/api/dashboard/kpi`   | KPI 集計        |

### 8.2.3 作業ログ

| メソッド   | パス                   | 説明 |
| ------ | -------------------- | -- |
| GET    | `/api/worklogs`      | 一覧 |
| POST   | `/api/worklogs`      | 登録 |
| PUT    | `/api/worklogs/{id}` | 更新 |
| DELETE | `/api/worklogs/{id}` | 削除 |

### 8.2.4 マイルストーン

| メソッド   | パス                     | 説明 |
| ------ | ---------------------- | -- |
| GET    | `/api/milestones`      | 一覧 |
| POST   | `/api/milestones`      | 作成 |
| PUT    | `/api/milestones/{id}` | 更新 |
| DELETE | `/api/milestones/{id}` | 削除 |

### 8.2.5 カテゴリ

| メソッド   | パス                     | 説明 |
| ------ | ---------------------- | -- |
| GET    | `/api/categories`      | 一覧 |
| POST   | `/api/categories`      | 作成 |
| PUT    | `/api/categories/{id}` | 更新 |
| DELETE | `/api/categories/{id}` | 削除 |

### 8.2.6 依存関係

| メソッド   | パス                                              | 説明           |
| ------ | ----------------------------------------------- | ------------ |
| GET    | `/api/tasks/{id}/dependencies`                  | 依存タスク取得      |
| POST   | `/api/tasks/{id}/dependencies`                  | 依存追加（循環チェック） |
| DELETE | `/api/tasks/{id}/dependencies/{predecessor_id}` | 依存削除         |

### 8.2.7 Inbox

| メソッド   | パス                        | 説明   |
| ------ | ------------------------- | ---- |
| GET    | `/api/inbox`              | 一覧   |
| POST   | `/api/inbox`              | 登録   |
| POST   | `/api/inbox/{id}/convert` | タスク化 |
| DELETE | `/api/inbox/{id}`         | 削除   |

### 8.2.8 ガント / レビュー

| メソッド | パス                                  | 説明        |
| ---- | ----------------------------------- | --------- |
| GET  | `/api/gantt`                        | ガント表示用データ |
| GET  | `/api/reviews/weekly?week=2026-W27` | 週次レビュー集計  |

## 8.3 エラーレスポンス例（RFC 7807）

```json
{
  "type": "https://example.com/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "due_date must be on or after start_date",
  "instance": "/api/tasks",
  "errors": [
    { "field": "due_date", "message": "start_date より後である必要があります" }
  ]
}
```

***

# 9. セキュリティ・運用

## 9.1 セキュリティ

| 項目          | MVP                             | フェーズ2                  |
| ----------- | ------------------------------- | ---------------------- |
| 認証          | なし（ローカル起動）                      | OIDC (Entra ID)        |
| CSRF        | 同一オリジンのみ                        | SameSite Cookie + トークン |
| SQLインジェクション | SQLAlchemy でパラメータ化              | 同左                     |
| XSS         | React の自動エスケープ + Markdown サニタイズ | 同左                     |
| CORS        | 開発用のみ許可                         | 明示許可                   |

## 9.2 ログ

* **アプリログ**: JSON 形式でファイル出力
* **アクセスログ**: FastAPI ミドルウェアで記録
* **監査ログ**（フェーズ2）: `audit_logs` テーブル追加

## 9.3 バックアップ

* **フェーズ2**: `mysqldump` を日次 cron で実行、7世代保持

***

# 10. MVPスコープまとめ

## 10.1 MVPで実装するもの

### テーブル

* `users` / `categories` / `milestones` / `tasks` / `work_logs` / `task_dependencies` / `inbox_items`

### ビュー・トリガー

* `v_task_summary` / `v_today_tasks`
* `trg_tasks_before_update`

### 画面

* ダッシュボード / 今日のタスク / タスク一覧 / タスク編集 / ガントチャート / カレンダー / Inbox / マイルストーン / 週次レビュー

### 機能

* タスク CRUD（階層・依存対応）
* 工数管理（見積・実績・残）
* 進捗率・優先度スコアの自動計算
* 今日のタスク抽出
* マイルストーン管理
* Inbox（タスク化変換フロー含む）

## 10.2 MVPで実装しないもの（フェーズ2以降）

* デスクトップ通知（Web Notifications API）
* 認証・マルチユーザー
* Microsoft To Do / Outlook / Google Calendar 連携
* AI による優先度・WBS 生成
* チーム共有機能
