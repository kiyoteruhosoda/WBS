# ADR-0006: スキーマを Alembic で管理する（create_all と手書きの列補完をやめる）

- 状態: 承認
- 日付: 2026-10-01

## 背景

これまで表は起動のたびに `Base.metadata.create_all` で作り、`create_all` が既存の表を
変えないぶんを `session.py` の手書きの列補完（`users.language` を足す・
`auth_sessions.idp_session_id` を足す・`tasks.remaining_hours` を落とす）で埋めていた。
`migrations/versions/` は空で、CLAUDE.md の「Alembic で upgrade / downgrade」と合っていない。
これから表を 5〜6 本足す（task #151）ので、その前に今の形を Alembic の起点にする（task #153）。

本番は SQLite 1 ファイル（k8s の PV、`Recreate`・1 台）。その DB は列補完で後から列を
足された古い DB で、`create_all` が新規に作る形と完全には同じでない可能性がある。
実際、列補完は `idp_session_id` の列だけを足し、モデルが持つ索引
`ix_auth_sessions_idp_session_id` は作っていなかった。

## 決定

1. **baseline（`0001`）は今の `create_all` の形をそのまま写す。** 名前の付いた索引・制約まで同じ。
   以後このファイルは書き換えず、形を変えるときはリビジョンを足す（足し方は `migrations/README`）。
2. **DB を上げるのはコンテナの entrypoint（`scripts/run_db_migrations.py` → `init_db()`）だけ。**
   uvicorn の前に流れる。アプリの lifespan は表を作らず、DB が head でなければ
   `SchemaNotCurrentError` で起動しない。
3. **`alembic_version` の無い既存の DB は、旧経路を 1 回なぞってから stamp する。**
   無い表を作る（`create_all` 相当）→ 列補完 3 つ（文面は旧コードのまま）→ 無い索引を作る。
   表と索引の DDL は、空の DB に baseline を当てた結果から写す。そのあと baseline と形を
   比べ（列の型・NULL 可否・主キー・一意制約・外部キー・索引）、**揃ったときだけ** baseline へ
   stamp して `upgrade head` する。
4. **補完・stamp・upgrade は 1 つの transaction。** pysqlite は DDL の前に BEGIN を出さない
   （自動で確定する）ので、移行用の接続だけは BEGIN を自分で出す。形が揃わなければ例外で
   全部を巻き戻し、entrypoint が非 0 で終わる（壊れた形のまま stamp もされない、手も入らない）。
5. 唯一許す差は `users.language` の `DEFAULT 'ja'`。SQLite は NOT NULL の列を既定値なしに
   足せないので、列補完で足された DB だけが持つ。アプリは常に値を入れて書くので害は無い。

## 理由

- **lifespan でなく entrypoint にした**: k8s（`/config/deploy-repo/k8s/wbs-prod/30-api.yaml`）も
  compose も既に `entrypoint.sh app` で起動し、`deploy.sh` は `entrypoint.sh migrate` を呼ぶ。
  入口が既にここに 1 本ある。lifespan で流すと、ワーカーを複数にしたときに同時に走る。
  試験の DB も同じ `init_db()` で作る（session 単位で 1 回作って写す）。
- **「無ければ stamp」にしなかった**: 古い DB をそのまま stamp すると、列補完で欠けた索引の
  ような差が永久に残り、後のリビジョンが前提を外す。旧経路は「無ければ足す」だけなので、
  もう 1 回なぞっても既に揃っている DB には何もしない。
- **比較を必須にした**: 列補完の手が届かない差（手で足した列など）があると、なぞっても
  揃わない。揃わないまま stamp するより、起動を止めて人が見る方を選んだ。
- **baseline を `metadata.create_all` で書かなかった**: モデルを参照するとモデルの変更で
  baseline が動いてしまう。`op.create_table` で凍結した。

## 影響

- `init_engine()` は表を作らなくなった。DB を用意するのは `init_db()`（移行 + 既定の利用者）。
  `uvicorn main:app` を素で起こす前に `scripts/run_db_migrations.py` が要る。
- 試験 `tests/integration/test_migration_model_consistency.py` が「head = `create_all`（旧経路）」
  を、`tests/integration/test_schema_migration.py` が上げ下げ・古い DB の引き取り・巻き戻しを見る。
  CI でも `alembic upgrade/downgrade/check` を流す。
- ⚠ 本番の DB が baseline と揃わなかった場合、配った版の Pod は起動に失敗する（`Recreate` なので
  旧版も止まっている）。DB は巻き戻っているので、前の版へ戻せばそのまま動く。
- 引き取りの処理は SQLite だけ。ほかの DB で `alembic_version` の無いものは断る。
