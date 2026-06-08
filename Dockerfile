FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace/services/activity-bot

RUN pip install --no-cache-dir uv

COPY shared/ /workspace/shared/
COPY services/activity-bot/pyproject.toml services/activity-bot/uv.lock ./

RUN uv sync --frozen --no-dev

COPY services/activity-bot/src ./src

CMD ["uv", "run", "python", "-m", "src"]
