# Trip Agent — 여행 플래닝 & 예약 챗봇 설계 문서

> 이어드림스쿨 8주차 개인 프로젝트 (2026-07-16 ~ 2026-07-22)
> 참고 프로젝트: `50_AgenticAI` (lang-manus, LangGraph supervisor 멀티에이전트)
> 데이터 소스 상세: [`data-sources.md`](data-sources.md)

## 1. 개요

사용자와 대화하며 여행지 정보를 조회하고, 일정에 맞춰 일자별 플랜을 짜주고,
항공·숙소·액티비티 예약과 (더미) 결제까지 이어주는 대화형 에이전트.

- **입력**: 자연어 대화 ("다음 달에 제주 3박 4일 가고 싶어", "파리 5일 일정 짜줘")
- **출력**: 여행지 추천, 일자별 일정표, 예약 후보, 예약 확정서(더미 결제)

## 2. 목표와 범위

### 포함 (In scope)
- 대화로 여행 요청 파악 (목적지·기간·인원·예산·선호)
- 여행지/명소/숙박/액티비티 정보 조회
- 사용자 일정에 맞춘 일자별 플랜 생성
- 항공·숙소·액티비티 검색 및 예약(주문 생성)
- 더미 결제 처리 + 예약 확정서 발급

### 제외 (Out of scope)
- 실제 결제/발권 (테스트·더미로 시뮬레이션만)
- 회원/인증 시스템 (데모 세션 단위로 관리)
- 다국어 (한국어 우선)

## 3. 아키텍처

LangGraph `StateGraph` 기반 supervisor 멀티에이전트. 참고 프로젝트의
`coordinator → planner → supervisor → workers` 패턴을 여행 도메인으로 재구성.

```
        ┌─────────────┐
START → │ coordinator │  대화, 의도 파악, 필수 정보 수집/되묻기
        └──────┬──────┘
               │ handoff
        ┌──────▼──────┐
        │   planner   │  실행 계획(JSON) 수립: 어떤 워커를 어떤 순서로
        └──────┬──────┘
        ┌──────▼──────┐
   ┌───▶│ supervisor  │  계획에 따라 다음 워커 라우팅 (구조화 출력 Router)
   │    └──────┬──────┘
   │           │ goto
   │   ┌───────┼───────────┬───────────┬───────────┐
   │   ▼       ▼           ▼           ▼           │
   │ destination  itinerary  booking    payment     │
   │ (정보조회)   (일정구성)  (예약)     (더미결제)   │
   │   │       │           │           │           │
   └───┴───────┴───────────┴───────────┘           │
                    완료 시 ─────────────────────▶ END
```

### 노드별 책임

| 노드 | 역할 | 주요 툴 |
|---|---|---|
| `coordinator` | 사용자와 대화. 여행 요청 여부 판단, 필수 정보 부족 시 되묻기, 충분하면 planner로 handoff | — |
| `planner` | 요청 분석 → 실행 계획(JSON) 수립 | — |
| `supervisor` | 계획에 따라 다음 워커 결정, 완료 판단 | — |
| `destination_agent` | 여행지·명소·날씨·액티비티 정보 + **지역 간 이동수단·소요시간**(세부↔보홀 페리 2h 등) 조회 | `search_destinations`, `get_attractions`, `get_transfers`, `get_weather` |
| `itinerary_agent` | 일자별 일정 구성 + **멀티 목적지 방문순서·기간배분·동선 설계**(옵션 비교·트레이드오프) | `plan_route`, `build_itinerary` |
| `booking_agent` | 항공·숙소·액티비티 **검색 및 예약**. **순차 예약**(항공→숙소처럼 앞 예약 결과를 다음 검색 조건으로) 및 일괄 예약 모두 지원 | `search_flights`, `search_hotels`, `create_booking` |
| `payment_agent` | **더미 결제** + 확정서 발급 | `process_payment`, `issue_confirmation` |

## 4. 데이터 계층 (provider 추상화 + 폴백)

핵심 설계 원칙: **호출부는 데이터 출처를 모른다.** `travel_service`는 구체 provider를 직접
알지 않고 `registry` 파사드만 부른다. provider는 공통 인터페이스(`base.Provider`)를 따르며,
`first_available`이 도메인별 목록을 우선순위대로 시도해 첫 유효 결과를 반환한다. 모두 실패하면
`travel_service`가 mock으로 폴백한다. **provider 교체·추가는 registry 목록만 수정**하면 된다.
(조사·비교 상세는 [`data-sources.md`](data-sources.md))

```
travel_service (도메인 로직)              data/  (mock 폴백)
    │  registry.attractions("제주")       ├─ destinations.json
    ▼                                     ├─ hotels.json
providers/registry.py  (도메인별 파사드)   ├─ flights.json
    │  ATTRACTIONS = [TourApi…, Geoapify…] └─ activities.json
    │  STAYS       = [TourApi…, LiteApi…]
    │  FLIGHTS     = [Duffel…]
    ▼
providers/base.py : first_available(list, city, limit)
    │  각 provider.supports(city) → fetch(city) 순서대로 시도 (국내 우선 → 해외)
    ▼
providers/{tour_api, geoapify, liteapi, duffel}.py  ← base.Provider 규약
    · supports=커버 도시+키 있을 때  · 실패/빈결과=None → 다음 provider/mock
    · 국내(제주·부산)=TourAPI, 해외(세부·보홀)=Geoapify/LiteAPI/Duffel
```

### provider 인터페이스 (`base.Provider`)

| 멤버 | 역할 |
|---|---|
| `name` | 로깅·식별용 이름 |
| `supports(city)` | 이 provider가 해당 도시를 커버하는지 (국내/해외 구분) |
| `fetch(city, limit)` | mock과 **동일 스키마**의 결과 리스트, 또는 None(미커버·실패·빈결과) |

새 provider는 이 세 멤버만 구현해 registry 목록에 추가하면 끝. 반환 스키마가 mock과 같으므로
카드 페이로드 변환(`build_*_payload`)·프론트는 그대로 재사용된다.

### 도메인별 provider (구현 현황)

| 도메인 | provider | 상태 | 폴백 |
|---|---|---|---|
| 국내 관광지(명소) | **TourAPI** (KorService2 `searchKeyword2`) | ✅ **연동** | mock |
| 국내 숙박 | **TourAPI** (KorService2 `searchStay2`) | ✅ **연동** | mock |
| 해외 명소 (POI) | **Geoapify** (지오코딩+Places, 대표명소 큐레이션) | ✅ **연동** | mock |
| 해외 호텔 | **LiteAPI** (`/data/hotels` + `/hotels/rates`) | ✅ **연동** | mock |
| 해외 항공 | **Duffel** (offer_requests, 날짜별 조회) | ✅ **연동** | mock |
| 국내 항공·결제 | mock / 더미 | mock 사용 | — |

> 모든 API는 무료·카드불필요. 키가 하나도 없어도 mock으로 전체 동작한다.
> `USE_MOCK_ONLY=true`로 실 API를 전부 끄고 mock만 쓰는 시연 모드 지원.
> 국내(제주·부산)는 TourAPI, 해외(세부·보홀)는 Geoapify/LiteAPI/Duffel로 `supports`가 자동 분기.
> **환율**: Duffel/LiteAPI 요금(USD)은 고정 환율(₩1,350)로 KRW 환산. TourAPI 숙박 요금은 결정적 데모값.

## 5. 디렉토리 구조

```
trip-agent/
├── README.md  .env.example  .gitignore  Makefile  docker-compose.yml
├── docs/                          # 설계·산출물 (index/design/data-sources)
├── backend/
│   ├── pyproject.toml  Dockerfile
│   ├── app/
│   │   ├── main.py                # FastAPI 진입점
│   │   ├── api/                   # routes/chat.py, schemas.py
│   │   ├── core/                  # config.py, logging.py
│   │   ├── agents/
│   │   │   ├── graph.py  state.py  llm.py
│   │   │   ├── nodes/             # coordinator, planner, supervisor, 워커 4종
│   │   │   └── prompts/           # *.md 템플릿 + 로더
│   │   ├── tools/                 # LangChain @tool 모음
│   │   ├── services/              # 여행 도메인 로직 (registry 파사드 호출)
│   │   ├── providers/             # base.py(Provider 규약)·registry.py(파사드)·tour_api.py
│   │   └── data/                  # mock JSON (폴백)
│   └── tests/
└── frontend/                      # Vite + React 챗 UI
    ├── package.json  vite.config.js  index.html
    └── src/                       # App.jsx, components/, lib/api.js
```

## 6. 기술 스택

- **백엔드**: Python 3.12, FastAPI, uvicorn, LangGraph, langchain-openai, pydantic-settings, httpx
- **프론트엔드**: Vite + React, fetch 기반 API 클라이언트
- **LLM**: OpenAI (gpt-4o-mini 기본), env로 교체 가능
- **패키지 관리**: uv (backend), npm (frontend)

## 7. API 설계

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/chat` | 사용자 메시지 → 에이전트 응답 (conversation_id로 세션 유지) |
| `GET` | `/health` | 헬스 체크 |

요청/응답은 `app/api/schemas.py`의 Pydantic 모델로 정의.

## 8. 개발 접근 & 기능 우선순위

**전략**: mock 데이터로 전체 흐름을 먼저 완성하고, 그 위에 실 API를 provider 단위로 얹는다.
mock이 항상 폴백으로 받치므로 어느 시점에 멈춰도 데모 가능하다.

**마감(7/22)이 촉박하므로 기능을 우선순위로 나눈다.** 위 티어부터 완성하고 시간이 남으면 아래로.

| 티어 | 기능 | 판단 |
|---|---|---|
| **T1 (MVP·필수)** | 레이아웃 B(채팅+패널) · **단일 목적지 기본 흐름**(상담→일자별 일정→예약→더미결제→확정) · 핵심 리치 카드 · 전 구간 mock | 이것만으로 완결된 데모 |
| **T2 (완성도)** | **순차 예약**(항공→숙소, 앞 예약이 뒤 검색 조건) · **날짜별 항공 가격 목록** · **지역/날짜별 숙소 목록** · 버튼+채팅 병행 · 국내 실 API(TourAPI·OpenTripMap) | 실사용감 크게 상승 |
| **T3 (킬러·욕심)** | **멀티 목적지 동선·여정 설계**(옵션 비교) · 해외 실 API(Duffel·LiteAPI) · 반응형/다크모드 디테일 | 데모 임팩트 포인트, 시간 남으면 |

> 동선 설계(T3)는 매력적이지만 멀티 목적지 상태·추론 복잡도가 있어 뒤로. 단 LLM 추론 위주라
> 실 API 없이 mock만으로도 구현 가능하므로, T2가 빨리 끝나면 앞당길 수 있다.

### 개발 순서
1. **[초기 설정]** 디렉토리 골격 + 설정파일 + 모듈 스텁 ← *현재 단계*
2. 그래프 뼈대 + coordinator/planner/supervisor 라우팅 (mock 응답)
3. **T1**: 4워커 + mock으로 기본 흐름 완성 + 프론트 챗 UI 연결
4. **T2**: 순차 예약·날짜별/지역별 목록 + 국내 실 API 연결
5. **T3**: 동선 설계 + 해외 실 API + 마감 다듬기

## 9. 위험과 대응

| 위험 | 대응 |
|---|---|
| 4일 일정 촉박 | mock-first로 항상 데모 가능 상태 유지, 실 API는 얹기 |
| Duffel 항공 데이터가 가짜(Duffel Airways) | 감수 or 항공 검색만 mock 병행 ([data-sources.md](data-sources.md) 7장) |
| 데이터 소스 여러 개 통합 복잡도 | provider 추상화로 툴/에이전트 코드 단일화 |
| API 키 발급 지연/누락 | 키 없이도 mock으로 완전 동작, `USE_MOCK_ONLY` 모드 |
