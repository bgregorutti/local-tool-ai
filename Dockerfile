FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production deps only, into the system Python (no virtualenv)
RUN uv sync --frozen --no-dev --no-install-project

# Copy the rest of the source
COPY agent.py main.py server.py ./
COPY tools/ tools/
COPY static/ static/

ENV PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local

EXPOSE 7860

CMD ["uv", "run", "server.py"]
