# =============================================================================
# review-agent — 多阶段 Docker 构建
# =============================================================================
# 构建:          docker build -t review-agent .
# 运行 API:      docker run -p 8000:8000 --env-file .env review-agent
# 运行 Worker:   docker run --env-file .env review-agent worker
# =============================================================================


# -- Stage 1: Builder ---------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# 只复制依赖文件，利用 Docker 层缓存
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project


# -- Stage 2: Development (默认) ----------------------------------------------
FROM python:3.12-slim AS development

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# 安装所有依赖（含 dev）
COPY pyproject.toml .
RUN uv sync --all-extras

# 复制源码（开发模式挂载 volume 覆盖此层）
COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import http.client; c=http.client.HTTPConnection('localhost:8000'); c.request('GET','/healthz'); assert c.getresponse().status==200"

CMD ["uv", "run", "uvicorn", "review_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]


# -- Stage 3: Production -----------------------------------------------------
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd -r app && useradd -r -g app app

WORKDIR /app

# 从 builder 复制预装好的依赖
COPY --from=builder /app/.venv/ ./.venv/
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/

# 复制应用代码
COPY src/ ./src/

RUN chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import http.client; c=http.client.HTTPConnection('localhost:8000'); c.request('GET','/healthz'); assert c.getresponse().status==200"

CMD ["python", "-m", "uvicorn", "review_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
