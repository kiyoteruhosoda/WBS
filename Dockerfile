FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Build-time metadata injected by GitHub Actions (defaults for local builds)
ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

# Structured logs written here – mount as a volume in production
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["/app/scripts/entrypoint.sh", "app"]
