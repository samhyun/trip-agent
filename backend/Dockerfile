FROM python:3.12-slim

WORKDIR /app

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 의존성 먼저 설치 (레이어 캐시)
COPY pyproject.toml ./
RUN uv sync --no-dev || uv pip install --system fastapi uvicorn[standard]

# 앱 소스
COPY . .

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
