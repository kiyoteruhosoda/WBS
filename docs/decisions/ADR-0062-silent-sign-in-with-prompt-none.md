# ADR-0062: ログイン画面を描く前に、Assay で入っているかを黙って確かめる

- 状態: 承認
- 日付: 2026-10-22
- 関連: task #644（全アプリ共通の形）・#647（このアプリ）

## 文脈

Assay で認証済みでも、WBS はログイン画面で「Assay でログイン」を押させていた。
持ち主の依頼は「SSO で認証が通っていたら、そのまま画面を出したい」。形は #644 で全アプリ共通に決めてある。

## 決定

1. 入っていないと分かったら、ログイン画面を**描く前に** `GET /api/auth/login?silent=1&next=…` へ画面遷移する
   （`location.replace`）。サーバは認可要求に **`prompt=none`** を付けて Assay へ送り出す（iframe は使わない）。
2. Assay で入っていれば code が返り、ふつうのログインと同じ道で `next` の画面へ入る。
3. 入っていなければ Assay は `error=login_required`（ほかに `consent_required`・`interaction_required`・
   `account_selection_required`）で戻す。往復の控え（`auth_login_transactions`）に**黙って確かめた往復**の印
   （列 `silent`。移行 0029）があり、このブラウザが始めた往復（`sso_login_state` の Cookie）なら、
   エラーを付けずに `/login?sso_silent=1&next=<戻り先>` へ返す。
4. 試さないとき:
   - このタブで一度試した後（sessionStorage の印。入れたら消す）
   - このアプリでサインアウトした後（localStorage の印。次に入れたら消す）
   - `/login` に `next` 以外のクエリが付いているとき（`error`・`sso_silent` など）
   - 使っている途中で切れたとき（`sessionExpired`）。画面が勝手に移ると、打っていたものが消える
   - オフライン・SSO を使わない配備・印を置けないとき
5. Assay では通ったがアプリで断られたときと、ほかの IdP のエラーは、今まで通りエラーを出す。

## 理由

- 印を往復の控えに入れるのは、`login_required` を「失敗ではない」と扱う範囲を、こちらが黙って始めた往復だけに絞るため。
- サインアウトは IdP のセッションも切る（`end_session_url`）ので、黙って確かめても入り直さないはずだが、
  IdP に end_session が無い構成もあるので印でも止める。
- 印を置けないときは試さない。1 回だけの印が無いと、戻ってくるたびに試してループになる。

## 影響

- Assay から出ている人は、ログイン画面が出るまでに Assay への往復が 1 回増える（タブごとに 1 回）。
- `/login?next=…` の `next` を、ボタンで入るときの戻り先に使うようにした（それまでは `/login` からは常に `/`）。
