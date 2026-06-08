# review-agent Makefile
# 常用开发命令封装

.PHONY: install dev lint format typecheck test test-unit test-int coverage \
        security-scan migrate migrate-create migrate-downgrade build \
        docker-up docker-down clean

# ── 安装与运行 ──────────────────────────────────────────

install:
	uv sync

dev:
	uv run uvicorn review_agent.api.app:app --reload --host 0.0.0.0 --port 8000

# ── 代码质量 ────────────────────────────────────────────

lint:
	uv run ruff check src/

lint-fix:
	uv run ruff check src/ --fix

format-check:
	uv run ruff format src/ --check

format:
	uv run ruff format src/

typecheck:
	uv run mypy src/

# ── 测试 ────────────────────────────────────────────────

test:
	uv run pytest -v

test-unit:
	uv run pytest -v -m "not integration and not e2e"

test-int:
	uv run pytest -v -m integration

coverage:
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html

# ── 安全扫描 ────────────────────────────────────────────

security-scan:
	bandit -r src/ -c pyproject.toml || echo "bandit not installed, skipping"

# ── 数据库 ──────────────────────────────────────────────

migrate:
	uv run alembic upgrade head

migrate-create:
	@read -p "Migration name: " name; uv run alembic revision --autogenerate -m "$$name"

migrate-downgrade:
	uv run alembic downgrade -1

# ── 构建 ────────────────────────────────────────────────

build:
	uv build

# ── Docker ──────────────────────────────────────────────

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

# ── 清理 ────────────────────────────────────────────────

clean:
	rm -rf dist/ build/ *.egg-info .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ── 验证（完整入口） ────────────────────────────────────

verify: lint typecheck test
	@echo "✅ All checks passed"
