.PHONY: install install-backend install-frontend backend frontend db-up migrate seed test lint fmt clean

install: install-backend install-frontend ## 백엔드+프론트 의존성 설치

install-backend: ## 백엔드 의존성 설치 (uv)
	cd backend && uv sync

install-frontend: ## 프론트엔드 의존성 설치 (npm)
	cd frontend && npm install

backend: ## 백엔드 개발 서버 (http://localhost:8000)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend: ## 프론트엔드 개발 서버 (http://localhost:5173)
	cd frontend && npm run dev

db-up: ## pgvector DB 기동 (docker, 호스트 5433)
	docker compose up -d --wait db

migrate: ## DB 마이그레이션 적용 (alembic)
	cd backend && uv run alembic upgrade head

seed: ## FAQ를 pgvector에 적재
	cd backend && uv run python -c "from app.services.rag_service import seed_faq; print('적재:', seed_faq(), '건')"

test: ## 백엔드 테스트
	cd backend && uv run pytest

lint: ## 린트 (ruff)
	cd backend && uv run ruff check app tests

fmt: ## 포맷 (ruff)
	cd backend && uv run ruff format app tests

clean: ## 캐시/빌드 산출물 정리
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.pytest_cache backend/.ruff_cache frontend/dist
