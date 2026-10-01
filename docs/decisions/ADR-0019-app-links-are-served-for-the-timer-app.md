# ADR-0019: 打刻アプリのログインの戻り先を WBS のホストの App Link にする

- 状態: 承認
- 日付: 2026-10-01
- 関連: task #167（打刻アプリ）、ADR-0018（アプリのトークン）、fastapitemplate の ADR-0045 / ADR-0046、
  flutterbase の ADR-0007 / ADR-0008（Auth Tab）、nolumiadeck の ADR-0118

## 背景

打刻アプリ（flutterbase 型）は assay に public client（PKCE）で直接ログインする。assay は http(s) の
redirect URI しか登録できないので、戻り先は**どこかの https のホスト上の App Link** になる。
flutterbase は「対の Web」のホスト（`APP_LINK_HOST`）の `https://<host>/app/oauth2redirect` を戻り先にし、
Chrome の Auth Tab と Android はそのホストの `/.well-known/assetlinks.json` でアプリの署名を確かめてから
アプリへ渡す。

deck の作成は対の Web に「deck で作った web 型」しか選べない（nolumiadeck ADR-0118）。WBS は作成の記録が
無いので、deck は WBS に App Links の設定を足せない。WBS が自分で出す。

今の WBS では `/.well-known/assetlinks.json` も `/app/oauth2redirect` も画面の nginx が SPA の
`index.html`（200・text/html）を返す。⚠ これだと検証が**黙って**落ち、Auth Tab がすぐ閉じてサインインが
「失敗」になる。

## 決定

1. **`GET /.well-known/assetlinks.json` を api が出す。** 中身は環境変数 `ANDROID_APP_PACKAGE` と
   `ANDROID_APP_CERT_FINGERPRINTS`（カンマ区切りか JSON の配列）だけで決める。**どちらかが空なら 404**
   （既定。配っただけでは何も変わらない）。未ログインで読める。
2. **画面の nginx はこの 1 本だけを裏へ渡す**（`location = /.well-known/assetlinks.json`）。`/api/` の外を
   裏へ渡すのはここだけ。
3. **戻り先の案内画面 `/app/oauth2redirect` を SPA に置く。ログインの外**（`AuthProvider` の外）に置き、
   未ログインの PC で開いてもログイン画面へ飛ばさない。認可コードが付いていれば「アプリに戻る」
   （同じ URL を開き直す）ボタンを出す。⚠ ここではログインを続けない（認可コードはアプリしか引き換えられない）。

## 理由

- **雛形（fastapitemplate ADR-0045 / ADR-0046）と同じ形**にした。値の出所が同じ（deploy-repo の
  `20-config.yaml`）なので、deck が雛形の派生に書くのと同じ鍵の名前を使う。
- **環境変数だけにした**のは、書き換えられると別のアプリに認可コードを渡す宣言になるため（ADR-0018 と同じ線）。
- **nginx は完全一致の 1 本だけ**。`/.well-known/` を丸ごと裏へ渡すと、api が答えない名前まで 404 の JSON に
  変わり、何を出しているかが読みにくくなる。

## 影響

- 配る側に要るもの: `ANDROID_APP_PACKAGE` / `ANDROID_APP_CERT_FINGERPRINTS`（ADR-0018 の `APP_CLIENT_IDS` と組）。
  指紋は deploy-repo の `resources/flutter-apps.json` の `cert_sha256`。⚠ 署名鍵を替えたら指紋も直す。
- 1 つのホストで結べるアプリは、この 2 つの値が表す組（パッケージ 1 つ）。別のアプリを足すときは配列の形を
  見直す。
