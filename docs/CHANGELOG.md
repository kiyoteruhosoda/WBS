# CHANGELOG

完了した重要な変更の要約（新しいものを上に）。詳しい経緯は `history/` を参照。

## 2026-07-13

- DB 方針を MariaDB に確定（`decisions/ADR-0001-database-mariadb.md`）。
- 雛形のサンプル `Item` 一式（Domain / Application / Infrastructure / Presentation の
  各層とテスト）を撤去。`main.py` の `/items` ルーター登録と関連 DI・SQLite テーブル
  定義も削除。ドメイン語彙を Task Scheduler へ寄せるための前処理。
