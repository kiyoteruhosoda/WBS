# CHANGELOG

完了した重要な変更の要約（新しいものを上に）。詳しい経緯は `history/` を参照。

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
