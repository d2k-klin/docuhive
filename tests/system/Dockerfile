FROM ghcr.io/astral-sh/uv:0.11.13@sha256:841c8e6fe30a8b07b4478d12d0c608cba6de66102d29d65d1cc423af86051563 AS uv
FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY services/docuhive/ services/docuhive/
COPY evals/ evals/
COPY config/ config/
COPY LICENSE ./
RUN uv sync --frozen --all-packages --all-extras --no-dev
COPY tests/mocks/ tests/mocks/
COPY services/docuhive/tests/intel/fixtures/ services/docuhive/tests/intel/fixtures/
COPY tests/system/tools/seed.py tests/system/tools/seed.py
RUN mkdir -p /srv/vault /srv/staging /srv/captures && chown -R 10001:10001 /srv
ENV PATH="/app/.venv/bin:$PATH"
USER 10001:10001
CMD ["docuhive", "api", "--host", "0.0.0.0"]
