# syntax=docker/dockerfile:1
# mdview — full image (convert + process extras). Multi-stage: build ParmEd's
# sdist in the builder, ship a slim runtime without compilers.

# Full python image (buildpack-deps) ships gcc/make, so ParmEd's sdist compiles
# without any apt step — keeps the build off the Debian mirrors entirely.
FROM python:3.13 AS builder
# uv binary from the official image (pinned)
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /bin/uv

ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# dependency layer (cached unless pyproject/lock change), then the source
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra convert --extra process


FROM python:3.13-slim AS runtime
# No apt needed in the runtime layer — just the venv + source. (The healthcheck
# uses Python, already present, so we avoid a network-dependent apt step.)
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
# bind 0.0.0.0 so the published port reaches the server; the host maps it to
# 127.0.0.1 only (see docker-compose.yml). /data and /renders are bind mounts.
ENTRYPOINT ["mdview"]
CMD ["serve", "--host", "0.0.0.0", "--root", "/data", "--render-dir", "/renders"]
