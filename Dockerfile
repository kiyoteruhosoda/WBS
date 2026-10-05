FROM python:3.14-slim@sha256:c3e521df8b2b498a7a682e7e18676771cb80c6b75b8699af886b2d554ce40151

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# 版（src/infrastructure/version.json）は **ビルドの前に生成してコンテキストへ入れる**。
# deck の build の「版を刻む」段（build-matrix の pre_build）が scripts/generate_version.sh を
# 実行し、その出力が上の COPY で入ってくる（ADR-0011）。この RUN は「無かったときに dev と
# 印を付ける」だけで、既にある内容は書き換えない。イメージには .git が入らない（.dockerignore）。
# ⚠ **ビルド情報を受け取る ARG を足さない。** 渡す側と名前がずれて、本番の git_sha が
#   unknown のままになった（task #168）。
RUN bash scripts/generate_version.sh

# Structured logs written here – mount as a volume in production
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["/app/scripts/entrypoint.sh", "app"]
