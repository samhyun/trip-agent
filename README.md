# Trip Agent 🧳

대화로 여행지를 좁히고, 실데이터로 명소·항공·숙소를 보여주고, 동선·일정까지 짜서
예약과 (더미) 결제로 잇는 **멀티턴 여행 에이전트**. LangGraph supervisor 멀티에이전트 구조에,
워커들은 검색 조건(시간대·정렬·지역)을 스스로 판단해 툴로 외부 API를 호출한다.

> 이어드림스쿨 8주차 개인 프로젝트 · 설계: [`docs/design.md`](docs/design.md)

## 주요 기능

- 💬 **멀티턴 계획 흐름** — "제주도 갈까 하는데" → 기간·인원 되묻기 → 명소·일정 → 항공 → 숙소 → 결제. 턴마다 슬롯(목적지·날짜·인원)이 누적되고 정정("제주 말고 부산")도 반영
- 🤖 **툴 쓰는 워커 에이전트** — "저녁 비행기로 제일 싼 거" → 에이전트가 `search_flights(depart_time, sort)` 파라미터를 판단, 코드가 실제 필터·정렬 적용
- 🌏 **미등록 해외 도시 자동 해석** — 큐레이션(제주·부산·세부·보홀) 밖 도시("랑카위", "이시가키")도 영문명→좌표·공항 자동 조회 후 실데이터
- ✈️🏨 **항공/숙소 턴 분리 + 스플릿 스테이** — 예약은 항공권부터 한 턴에 하나씩. "제주시 2일, 서귀포 2일"이면 지역별 숙소 카드로 각각 선택
- 🖱️ **화면 선택 연결** — 카드에서 고른 항공·숙소를 매 발화에 첨부해 "이렇게 해서 예약하고싶어"가 통함
- 🗺️ **멀티 도시 동선** — 두 도시 방문 순서 A/B안 비교 (숙박 배분·이동수단·출국 공항)
- 📸 **실데이터 리치 카드** — 명소(대표 사진), 왕복 항공, 숙소(정렬·지역 필터·상세 모달)
- ⚡ **하이브리드 스트리밍** — 일정·대화 텍스트는 토큰 단위로 흐르듯, 카드는 완성 후 한 번에
- 🔐 **계정·예약 영속화** — 회원가입/로그인(JWT), 결제 내역을 내 계정에 저장 (소유권 검증)
- ❓ **FAQ (RAG)** — pgvector 유사도 검색 + 출처 표시

## 기술 스택

| 구분 | 스택 |
|---|---|
| 백엔드 | Python 3.12 · FastAPI · **LangGraph** · SQLAlchemy · httpx |
| 프론트엔드 | Vite + React (리치 카드 · SSE 스트리밍) |
| LLM | **elice AI Cloud** 티어별(reasoning·standard·fast) · OpenAI 폴백 |
| DB | PostgreSQL + **pgvector** (RAG) · Alembic |
| 외부 데이터 | 국내 **TourAPI**(이미지 포함) · 해외 명소 **Geoapify** · 항공 **Duffel**(왕복) · 호텔 **LiteAPI** · 해외 명소 사진 **Wikipedia** |

> 외부 **데이터** API는 무료 티어/테스트 모드로 사용(카드 불필요, Duffel은 테스트 모드 — 항공사·요금에 샌드박스 값 포함).
> **데이터 API 키는 선택** — 없으면 핵심 데이터(명소·항공·호텔)는 mock JSON으로 폴백하고, 해외 명소 사진은 그라디언트로 대체된다(대화·계획 흐름은 그대로). 국내 숙소의 가격·평점은 TourAPI가 제공하지 않아 데모 값이다. 단 **에이전트 구동에는 LLM 키가 필수**.
> `USE_MOCK_ONLY=true`는 LLM과 실 데이터를 모두 끄는 순수 mock 모드(인사 응답만, 오프라인 확인용).

## 아키텍처 한눈에

```
START → coordinator ─┬─ chat_reply  (정보 부족 → 되묻기, 토큰 스트리밍)
 (의도 분류·슬롯 추출) ├─ recommend   (목적지 미정 + 조건 → 후보 추천)
                     ├─ faq         (정책·이용 질문 → pgvector RAG)
                     └─ planner → supervisor ⇄ 워커 에이전트
                        (워커 선정)   (결정론 순회)   ├ destination  명소 (관심사 필터)
                                                    ├ route        멀티도시 동선 A/B
                                                    ├ itinerary    일자별 일정 (ReAct + 명소 선주입)
                                                    ├ booking      항공·숙소 검색 툴
                                                    └ payment      선택 내역 추출·확정
```

- **멀티턴**: 대화를 DB에 저장하고 매 턴 전체 히스토리를 재주입. 슬롯은 매턴 대화 전체에서 재추출
- **프롬프트**: `app/agents/prompts/*.md` — 에이전트별 파일 + 로더(`<<PERSONA>>`·`<<CURRENT_TIME>>` 주입), 수정 즉시 반영(핫리로드)
- **판단 vs 실행**: 검색 조건·지역·확정 내역은 LLM이 판단, API 호출·필터·정렬·카드 변환은 코드가 보장
- **지연 관리**: 명소 API 병렬 조회·캐시·프리워밍, 목적지 파악 즉시 백그라운드 선행 조회, 목록은 평문+파싱 (실측 스크립트: `backend/scripts/measure_latency.py`)

## 빠른 시작

### 1. 환경변수
```bash
cp .env.example .env
# .env 편집: LLM 키(elice 티어 또는 OPENAI_API_KEY) 필수, DATABASE_URL은 기본값=로컬 Docker DB,
# 외부 데이터 키(TOUR_API_KEY·GEOAPIFY_API_KEY·DUFFEL_API_KEY·LITEAPI_API_KEY)는 있으면 실데이터
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
cd backend && .venv/bin/python tests/e2e/scenarios.py
# ※ 워커 에이전트화 개편 이전에 작성된 시나리오라 일부 항목은 기대값 갱신이 필요할 수 있다
```

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/chat` | 사용자 메시지 → 에이전트 응답 (턴별 카드 포함) |
| `POST` | `/chat/stream` | 위와 동일하되 **SSE 토큰 스트리밍** |
| `POST` | `/auth/register` · `/auth/login` | 회원가입 · 로그인 (JWT 발급) |
| `GET` | `/auth/me` | 내 정보 |
| `GET` | `/me/trips` | 내 예약(여행) 목록 |
| `GET` | `/details/hotel` | 호텔 상세 (사진·편의시설·체크인아웃) |
| `GET` | `/health` | 헬스 체크 |

## 프로젝트 구조

```
backend/app/
├── main.py                 # FastAPI 진입점 (라우터 등록 · 명소 캐시 프리워밍)
├── api/routes/             # chat · auth · trips · details
├── core/                   # config(LLM 티어·키), logging(키 마스킹)
├── agents/
│   ├── graph.py            # 그래프 조립 + 스트리밍 실행(subgraphs 토큰 복원)
│   ├── state.py            # 공유 상태(trip 슬롯·plan·visited) + 팀 구성
│   ├── llm.py              # 역할별 LLM 티어 팩토리
│   ├── prompts/            # 에이전트별 프롬프트 .md + template.py 로더 (핫리로드)
│   └── nodes/              # coordinator · planner · supervisor · faq · recommend
│       └── workers.py      # destination · route · itinerary · booking · payment (툴 정의 포함)
├── services/               # travel_service(도메인·선행조회) · trip_service · rag_service · auth_service …
├── providers/              # base·registry(파사드) + tour_api·geoapify·duffel·liteapi·photos·place·intl
├── db/                     # models(User·Conversation·Message·Trip·Booking·Payment)
└── data/                   # mock JSON (폴백) + faq.json
backend/scripts/            # measure_latency.py (플로우 지연 실측)
frontend/src/               # React 챗 UI (components/messages 리치카드, lib/conversationReducer)
backend/tests/e2e/          # scenarios.py (라이브 서버 E2E)
```

자세한 아키텍처는 [`docs/design.md`](docs/design.md), 문서 목록은 [`docs/index.md`](docs/index.md) 참고.
