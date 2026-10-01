# ADR-0011: 版はビルドの前に version.json へ刻み、build-arg では受け取らない

- 状態: 承認
- 日付: 2026-10-01

## 背景

本番の `/info` の `git_sha` が `unknown` のままで、配った版を確かめられなかった（task #168）。
`Dockerfile` は `ARG APP_VERSION / GIT_SHA / BUILD_TIME` で受け取る形だったが、本番を作る
deck の build はこの名前で渡さない（渡すのは `COMMIT_HASH` などの別の名前）。受け口の名前が
渡す側ごとにずれると、**ビルドは緑のまま版だけが消える**。

fastapitemplate は同じ問題を ADR-0044 で「ARG を持たず、build の『版を刻む』段が
`scripts/generate_version.sh` を走らせ、出力の `version.json` をビルドコンテキストへ入れる」
形で解いている。deck はこの段を、deploy-repo の `resources/build-matrix.json` の
`pre_build: true` を見て、**クローンしたリポジトリの根で `bash scripts/generate_version.sh`**
として走らせる（`BRANCH_OVERRIDE` 付き）。

## 決定

1. **版の出どころは `src/infrastructure/version.json` 1 つ。** `scripts/generate_version.sh`
   が作る。優先順位は **git > 既にある version.json > dev**（fastapitemplate と同じ）。
   生成物はコミットしない（`.gitignore`）。
2. **`Dockerfile` は ARG を持たない。** `COPY . .` のあとで `RUN bash scripts/generate_version.sh`
   を走らせ、無かったときだけ `dev` と刻む（イメージに `.git` は入らないので既存は潰さない）。
3. **`BuildInfo`（`/info`・`/healthz`）は `version.json` を読む。** 応答の形
   （`version` / `git_sha` / `build_time` / `environment`）は変えない。`git_sha` は短縮ハッシュ、
   `build_time` は UTC の `Z` 付き。環境変数 `APP_VERSION` / `GIT_SHA` / `BUILD_TIME` は
   手元で名乗りを変えるための口として残す（イメージは設定しない）。
4. **web（`frontend/Dockerfile`）には版を刻まない。** 画面の設定ページは api の `/api/info`
   を表示している。web の像は静的ファイルと nginx だけで、自分の版を答える口を持たない。

## 理由

- 名前を合わせて ARG を足す直し方は、次に渡す側が変わったときに同じ壊れ方をする。
  ファイルにしておけば、イメージの中を見れば版が分かり、渡し方の約束が要らない。
- deck の「版を刻む」段は宣言（build-matrix の `pre_build`）で決まり、どのリポジトリでも
  同じスクリプト名を走らせる。fastapitemplate と同じ形にすれば deck 側の作りを変えずに済む。
- web に刻まないのは、刻んでも読む口が無く、確かめる手段が増えないため。web と api の
  版のずれが問題になったら、そのとき web に `/version.json` を置く形で足す。

## 影響

- ⚠ **deploy-repo の `resources/build-matrix.json` で `wbs-api` の `pre_build` を `true` に
  しないと、本番は `git_sha: "dev"` を名乗る**（`unknown` からは変わるが、版は分からないまま）。
  ビルドは緑のままなので、配ったあと `/info` で確かめる。
- `scripts/build.py`（手元の compose 経路）は docker build の前に同じスクリプトを走らせる。
- `scripts/deploy.sh` の「Deployed version」はイメージの中の `version.json` を表示する。
