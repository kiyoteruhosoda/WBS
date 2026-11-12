FROM python:3.15-slim@sha256:f786b2e19cf9bb54e96bfcd4c1b40c4c56336c22e60607ffd4b080ae5b5dee83

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# The version (src/infrastructure/version.json) is **generated before the build and put in the context**.
# The "stamp the version" step of deck's build (build-matrix pre_build) runs scripts/generate_version.sh,
# and its output comes in via the COPY above (ADR-0011). This RUN only "marks it as dev when
# missing" and never rewrites existing content. .git is not in the image (.dockerignore).
# ⚠ **Do not add ARGs that receive build info.** The names drifted from the sender, and the prod git_sha
#   stayed unknown (task #168).
RUN bash scripts/generate_version.sh

# Structured logs written here – mount as a volume in production
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["/app/scripts/entrypoint.sh", "app"]
