# Trip Agent 🧳

대화로 여행지를 좁히고, 실데이터로 명소·항공·숙소를 보여주고, 멀티 도시 동선까지 짜서
예약과 (더미) 결제로 잇는 대화형 여행 에이전트. LangGraph supervisor 멀티에이전트 구조.

> 이어드림스쿨 8주차 개인 프로젝트 · 설계: [`docs/design.md`](docs/design.md) · 발표자료: [`docs/presentation.md`](docs/presentation.md)

## 주요 기능

- 💬 **대화로 목적지 확정** — 오타·정정도 LLM 의미 추출로 이해 ("제주 말고 부산")
- 🌏 **미등록 해외 도시 자동 해석** — 큐레이션 안 한 해외 도시("랑카위")도 영문명→좌표·공항 자동 조회 후 실데이터 (국내는 TourAPI가 담당)
- 🗺️ **멀티 목적지 동선** — 두 도시 방문 순서 A/B안 비교 (이동수단·출국 공항까지)
- 📸 **실데이터 리치 카드** — 명소(대표 사진·마커 지도·현재 날씨), 날짜별 항공 최저가, 숙소(정렬·상세보기)
- ⚡ **하이브리드 스트리밍** — 설명 텍스트는 토큰 단위, 카드는 완성 후 한 번에
- 🔐 **계정·예약 영속화** — 회원가입/로그인(JWT), 결제 내역을 내 계정에 저장
- ❓ **FAQ (RAG)** — pgvector 유사도 검색 + 출처 표시

## 기술 스택

| 구분 | 스택 |
|---|---|
| 백엔드 | Python 3.12 · FastAPI · **LangGraph** · SQLAlchemy · httpx |
| 프론트엔드 | Vite + React (리치 카드 · SSE 스트리밍) |
| LLM | **elice AI Cloud** 티어별(reasoning·standard·fast) · OpenAI 폴백 |
| DB | PostgreSQL + **pgvector** (RAG) · Alembic |
| 외부 데이터 | 국내 **TourAPI**(이미지 포함) · 해외 명소 **Geoapify** · 항공 **Duffel** · 호텔 **LiteAPI** · 날씨 **OpenWeather** · 해외 명소 사진 **Wikipedia** |

> 외부 **데이터** API는 무료 티어/테스트 모드로 사용(카드불필요, Duffel은 테스트 모드·라이브 발권은 유료).
> **데이터 API 키는 선택** — 없으면 핵심 데이터(명소·항공·호텔)는 mock JSON으로 폴백하고, 보강 데이터는 날씨=생략·사진=그라디언트로 대체된다(대화·계획 흐름은 그대로). 단 **에이전트 구동에는 LLM 키가 필수**.
> `USE_MOCK_ONLY=true`는 LLM과 실 데이터를 모두 끄는 순수 mock 모드(인사 응답만, 오프라인 확인용).

## 빠른 시작

### 1. 환경변수
```bash
cp .env.example .env
# .env 편집: LLM 키(elice 티어 또는 OPENAI_API_KEY) 필수, DATABASE_URL은 기본값=로컬 Docker DB,
# 외부 데이터 키(TOUR_API_KEY·GEOAPIFY_API_KEY·DUFFEL_API_KEY·LITEAPI_API_KEY·OPENWEATHER_API_KEY)는 있으면 실데이터
```

### 2. 데이터베이스 (Postgres + pgvector)
```bash
docker compose up -d db        # pgvector 포함 Postgres 기동
cd backend && uv run alembic upgrade head   # 스키마 마이그레이션
```

### 3. 백엔드
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### 4. 프론트엔드
```bash
cd frontend
npm install
npm run dev             # http://localhost:5173
```

### Makefile 단축
```bash
make install    # 백엔드+프론트 의존성
make backend    # 백엔드 개발 서버
make frontend   # 프론트 개발 서버
```

### E2E 시나리오 테스트
```bash
# 백엔드가 기동된 상태에서
cd backend && .venv/bin/python tests/e2e/scenarios.py    # 36개 항목 검증
```

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/chat` | 사용자 메시지 → 에이전트 응답 (턴별 카드 포함) |
| `POST` | `/chat/stream` | 위와 동일하되 **SSE 토큰 스트리밍** |
| `POST` | `/auth/register` · `/auth/login` | 회원가입 · 로그인 (JWT 발급) |
| `GET` | `/auth/me` | 내 정보 |
| `GET` | `/me/trips` | 내 예약(여행) 목록 |
| `GET` | `/details/hotel` · `/details/map` | 호텔 상세 · 명소 마커 지도(프록시) |
| `GET` | `/health` | 헬스 체크 |

## 프로젝트 구조

```
backend/app/
├── main.py                 # FastAPI 진입점 (라우터 등록)
├── api/routes/             # chat · auth · trips · details
├── core/                   # config, logging(키 마스킹)
├── agents/
│   ├── graph.py            # 그래프 조립 + 스트리밍 실행
│   ├── state.py            # 공유 상태 + 팀 구성
│   └── nodes/              # coordinator · planner · supervisor · faq
│       └── workers.py      # destination · route · itinerary · booking · payment
├── services/               # travel_service(도메인) · rag_service · auth_service …
├── providers/              # base·registry(파사드) + tour_api·geoapify·duffel·liteapi·weather·photos·place
├── db/                     # models(User·Conversation·Trip·Booking·Payment)
└── data/                   # mock JSON (폴백) + faq.json
frontend/src/               # React 챗 UI (components/messages 리치카드, context/AuthContext)
backend/tests/e2e/          # scenarios.py (라이브 서버 E2E)
```

자세한 아키텍처는 [`docs/design.md`](docs/design.md), 문서 목록은 [`docs/index.md`](docs/index.md) 참고.
