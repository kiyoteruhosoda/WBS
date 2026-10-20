# ADR-0056: Tracker のサーバーは機械として名乗り、利用者の担当タスクを読む

- 状態: 承認
- 日付: 2026-10-20
- 関連: task #539（親 #538・目的 #522）、ADR-0055（メンバー・担当者）、Tracker の ADR-0053 決定 4（タスクの写し）・
  ADR-0059（担当タスクの写し）、Scheduler の ADR-0056（同じ形の口。task #541）

## 背景

#522 で決めた線のうち「WBS → Tracker 担当タスク」。Tracker はタスクを管理せず、打刻の行き先として WBS のタスクの写しを持つ
（Tracker の ADR-0053 決定 4）。写しは段 1 で 1 度写したきりで、その後に WBS で作った・担当になったタスクは手で足すしかない。
Tracker のサーバーが、利用者の代わりに WBS から「自分の担当タスク」を読めるようにする。

## 決定（2026-10-20 に持ち主が「機械の名乗りで話す」を選んだ）

1. **Tracker のサーバーは assay の機械のクライアント（`tracker-{prod,stg}-machine`、`client_credentials`・`private_key_jwt`）で、
   宛名 `api://wbs`（stg も同じ綴り。assay の WBS のアプリに結んだ resource）のトークンを取って呼ぶ。** 利用者は
   `issuer` と `subject`（assay の `iss`・`sub`）で渡す。WBS は
   - 署名・`typ`・発行者・宛名（`MACHINE_AUDIENCE`）・期限を確かめ
   - 機械のトークンであること（`sub_type` がある）と、`client_id` が `MACHINE_READER_CLIENT_IDS` に入っていることを見る
   - 利用者は `federated_identities` の `(iss, sub)` で引く。**作らない**（居なければ 404、止めた人は 403）
   宛名か許可リストが空なら、機械の口は 1 本も通さない（既定）。`AUTH_MODE=single_user` でも閉じる。
   口は `/api/machine/...` に置く（Scheduler の ADR-0056 と同じ形・同じ設定の名前）。
2. **`GET /api/machine/assigned-tasks`** は、担当が本人で、本人に見えて（ADR-0055）、まだ作業できる
   （完了・中止・アーカイブでない）タスクを返す（id・題名・プロジェクトの道筋）。**絞るのは渡す側（WBS）**。
   ここに無いものは、Tracker が写しを閉じてよい（担当が外れた・終わった・見えなくなった）。

## 理由

- 利用者のトークンを Tracker に預ける案は、寿命が 5 分で更新の仕組みと保管が要る。機械の名乗りなら人の操作が要らない。
- Scheduler の口と同じ形にしたのは、Tracker 側のトークンの取り方（宛名つき `AdminApiTokenSource`）を共用するため。
- 完了したものも返して Tracker 側で絞る案は、何を出すかの決まりが 2 か所に分かれる。

## 影響

- 配備には `MACHINE_AUDIENCE=api://wbs` と `MACHINE_READER_CLIENT_IDS=<tracker の機械の client_id>` が要る
  （deploy-repo）。assay では `api://wbs` を WBS のアプリ（wbs-prod / wbs-stg）に resource として結び、Tracker の機械の
  クライアントをサービスアカウントとして割り当てる。k8s の隔離に tracker → wbs の穴を開ける。
- #540（Tracker → WBS 締めた時間）も同じ口・同じ名乗りで書き込む（この ADR を広げる）。
