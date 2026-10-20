# ADR-0057: WBS のアイコンをガントチャートの絵にする

- 状態: 承認
- 日付: 2026-10-20
- 関連: task #548、ADR-0028（アイコンの正本は scripts/generate_pwa_icons.py）・ADR-0040（画面の像は favicon.svg）、
  Tracker（forge `kyon/nolumiatracker`）の ADR-0061・Scheduler（forge `kyon/nolumiascheduler-server`）の ADR-0057

## 文脈

WBS から Tracker と Scheduler を分けた（WBS の ADR-0053・0054）ので、3 つともアイコンが WBS の木、色が `#0017C1` で見分けがつかなかった。
持ち主（2026-10-20）:「tracker と WBS サイトがほぼ一緒なので違いをつけてほしい、せめてアイコンは変えて」。
見本を並べて選んでもらい、木は「組織図に見える。ガントチャートのイメージがいい」と言われた。

## 決定（持ち主が見本から選んだ）

1. **WBS の図柄はガントチャート**: 上に日付の目盛り、その下に段々に右へずれる帯 3 本（白）。
2. **色は今の青（`#0017C1`）のまま。** Tracker は緑青 `#00695C` のストップウォッチ、Scheduler は紫 `#6A1B9A` のカレンダー。
3. 図柄の部品に「両端の丸い棒」と「輪」を足した（3 つのリポジトリの生成スクリプトで同じ作り）。正本は今までどおり
   `scripts/generate_pwa_icons.py` の 1 本で、画面の像（`AppMark`）は favicon.svg を読む。

## 影響

- タブ・ホーム画面・ログイン画面とメニューの像が変わる。画面の並びや機能は変わらない。
- 帯の絵は WBS のものなので、Tracker のストップウォッチの文字盤は帯から針に替えた（Tracker の ADR-0061）。
