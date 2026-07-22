.PHONY: install install-backend install-frontend backend frontend db-up migrate seed test test-backend test-frontend e2e golden lint fmt clean

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

test: test-backend test-frontend ## 백엔드+프론트 유닛 테스트

test-backend: ## 백엔드 유닛 테스트 (pytest)
	cd backend && uv run --extra dev pytest tests/unit

test-frontend: ## 프론트 유닛 테스트 (vitest)
	cd frontend && npm test

e2e: ## 라이브 E2E 시나리오 (실행 중 백엔드 + LLM·API 키 필요)
	cd backend && uv run python tests/e2e/scenarios.py

golden: ## 골든셋 회귀 (에이전트 실호출·LLM judge — LLM 키(elice/OpenAI) 필요, 비용 발생)
	cd backend && uv run python tests/golden/run.py

lint: ## 린트 (ruff)
	cd backend && uv run ruff check app tests

fmt: ## 포맷 (ruff)
	cd backend && uv run ruff format app tests

clean: ## 캐시/빌드 산출물 정리
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.pytest_cache backend/.ruff_cache frontend/dist
