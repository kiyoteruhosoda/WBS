# ADR-0044: WinTrack の更新の置き場は、WBS が配布面を読んで中継する

- 状態: 承認
- 日付: 2026-10-13
- 関連: task #384（WBS 側）・#377（WinTrack）、ADR-0018（Bearer の口）、
  fastapitemplate の ADR-0048（配布面の読み方の元）

## 背景

WinTrack は Velopack で更新する。Velopack は更新の置き場（版の一覧 `releases.win.json` とパッケージ `*.nupkg`）を
URL で読む。置き場の中身は forge の CI が配布面（Garage の `artifacts` バケットの `wintrack/`）に置くが、
配布面は SSO の後ろにあり PC から直接は読めない。

## 決定

1. `GET /api/wintrack/releases/{file}` で配布面の `wintrack/{file}` を読んで返す。WinTrack は
   `SimpleWebSource("https://wbs.nolumia.com/api/wintrack/releases/")` に Bearer を付けて読む（`AppOrWebUserDep`）。
2. 渡す名前は `releases.win.json`・`RELEASES`・`*.nupkg`（英数字と `._-` だけ、`..` を含まない）に限る。
   それ以外は置き場にあっても 404（配布面のほかのものへ届かせない）。
3. 読み方は fastapitemplate の ADR-0048 と同じ: boto3・パスに載せる番地・短い待ち時間・再試行なし。
   鍵は `artifacts` の読み取りだけ。秘密は値ではなく**ファイルの場所**（`WINTRACK_RELEASES_S3_SECRET_ACCESS_KEY_FILE`）で持ち、
   読むたびにファイルから取る。設定は `WINTRACK_RELEASES_S3_*`（ENDPOINT_URL・REGION・BUCKET・PREFIX・ACCESS_KEY_ID・
   SECRET_ACCESS_KEY_FILE。PREFIX の既定は `wintrack/`）。
4. **設定が空でも起動し、404 を返す。** 配布面が読めない・置き場に無いときも 404（WinTrack は「更新を確かめられない」として静かに扱う）。
   読めなかったときだけログに `wintrack.releases.unavailable` を残す。
5. 版の一覧はプロセスの中で 60 秒覚える（読めなかったことは 30 秒）。読みに行くのは同時に 1 本だけ。
   パッケージは覚えずに 1 MB ずつ流す（`Content-Length` 付き）。応答の `Cache-Control` は一覧が `no-store`、
   パッケージは名前ごとに中身が変わらないので `private, max-age=86400, immutable`。

## 理由

- 配布面を PC へ公開する（SSO の外に出す）案は、配布面のほかのものまで外に出る。WBS は既に WinTrack の
  Bearer を確かめているので、本人を確かめてから渡すのが最も小さい。
- WBS を通すとパッケージ（数十 MB）が WBS の帯域を通るが、利用者は少なく、更新は版を出したときだけ。
  パッケージを覚えないのは、プロセスのメモリを大きく食うため。
- 署名付き URL へ転送する案は、Garage の内側の番地（クラスタの中）が PC から届かないので採らない。

## 影響

- 依存に `boto3` が増えた。
- deploy-repo に `WINTRACK_RELEASES_S3_*` と鍵のファイルを足すまで、中継は 404 のまま（配布の設定）。
- 新しい版は出してから最大 60 秒（とプロセスの数）遅れて PC に見える。
