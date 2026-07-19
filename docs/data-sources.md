# 데이터 소스 · 외부 API 조사와 선정

> 여행 데이터를 어디서 가져올지에 대한 조사·비교·결정 기록.
> 관련 설계: [`design.md`](design.md) 4장 데이터 계층

## 1. 전략 요약

- **하이브리드**: 국내는 국내 특화 API, 해외는 해외 API, 명소는 전세계 공통 API.
- **mock 폴백 필수**: 모든 실 API 위에 JSON mock을 폴백으로 깔아 시연 안정성을 보장한다.
- **예약·결제는 더미**: 실제 발권/결제는 하지 않는다(테스트/샌드박스 또는 mock).

## 2. 선택 기준 (가중치 순)

1. **무료 + 신용카드 불필요** — 해커톤 4일, 마찰 최소화
2. **키 즉시 발급** — 승인 대기 있는 API는 후순위
3. **ROI(투자 대비 데이터 효과)** — 붙이자마자 화면이 풍부해지는가
4. **한국 데이터 커버리지**
5. **에이전트/예약 플로우 적합성**

## 3. 도메인별 최종 선정

| 도메인 | 선택 | 상태 | 폴백 | 비고 |
|---|---|---|---|---|
| 해외 명소 (POI) | **Geoapify** | ✅ 연동 | mock | OpenTripMap 인증 불안정 → 대체. OSM 기반, 무료 3k/day·카드X |
| 국내 관광·숙박 | **TourAPI** (한국관광공사) | ✅ 연동 | mock | 국내 실데이터 방대 |
| 해외 항공 검색 | **Duffel** | ✅ 연동 | mock | 실항공사 혼재(China Eastern 등), USD→KRW 환산 |
| 해외 호텔 검색 | **LiteAPI** (Nuitée) | ✅ 연동 | mock | 실호텔+실요금, 에이전트용 설계 |
| 날씨 (선택) | OpenWeatherMap | 키 검증 | mock | nice-to-have, provider 미구현 |
| 결제 | **더미(mock)** | — | — | 통일된 결제 UX |

> **명소 provider 변경**: OpenTripMap(`opentripmap.io`/`dev.opentripmap.org`)은 가입·키 발급이 불안정해 **Geoapify로 교체**. provider 추상화 덕에 `registry`의 `ATTRACTIONS` 목록만 수정.

## 4. 후보 API 상세 조사

### 4.1 명소 / POI

| API | 무료·카드 | 커버리지 | 판정 |
|---|---|---|---|
| **OpenTripMap** | 무료, 카드X, 즉시 키 | 관광명소 1,000만+ (OSM·Wikidata·Wikipedia), 전세계+한국 | ✅ **1순위** — 여행지 특화 |
| **Geoapify Places** | 무료, 카드X, 3,000 req/day | OSM 기반 POI, 카테고리 검색 | ✅ 2순위 (백업) |
| OpenStreetMap Overpass/Nominatim | 완전 무료, 키조차 불필요 | 러프하지만 강력 | 보조 |
| Google Places (New) | **카드 필수**, SKU별 무료한도(2025.3~) | 데이터 최상(사진·리뷰·평점) | ❌ 카드 마찰 |

### 4.2 국내 관광 — ✅ 연동 완료 (2026-07-19)

| API | 무료·카드 | 커버리지 | 판정 |
|---|---|---|---|
| **한국관광공사 TourAPI** | 무료(공공데이터포털 인증키), 카드X | 관광지·숙박·행사·이미지 등 15종 약 26만 건, 국문 | ✅ **국내 1순위** |

**연동 상세** (`providers/tour_api.py`)

- 상품: "한국관광공사_국문 관광정보 서비스_GW" · **End Point** `https://apis.data.go.kr/B551011/KorService2`
- 포맷 `_type=json` · 인증키는 `.env`의 `TOUR_API_KEY`. **Encoding/Decoding 키 모두 허용**
  (코드가 `%` 포함 시 자동 `unquote` → httpx가 한 번만 인코딩, 이중 인코딩 방지).
- 사용 오퍼레이션:
  - `searchKeyword2` — 명소 조회. 도시별 **큐레이션 유명 명소 키워드**(성산일출봉·해운대해수욕장 등)로 검색.
  - `searchStay2` — 국내 숙박 목록.
  - (`areaBasedList2` — 큐레이션 없는 도시의 명소 폴백, 제목순.)
- 반환은 mock(`destinations.json`/`hotels.json`)과 **동일 스키마**로 정규화(id·name·area·tags·desc·gradient, +lat/lng 동선용).
- **요금·평점 없음** → 숙박 카드의 가격·평점은 contentid 기반 결정적 데모값 부여.

**⚠️ TourAPI 특성 메모** (연동 중 발견)

- `searchKeyword2`에 `areaCode`/`contentTypeId`를 **파라미터로 같이 주면** 정확한 명소명("해운대해수욕장" 등)이 0건으로 나온다 → 필터는 빼고 키워드만 주고, **콘텐츠 타입은 응답의 `contenttypeid`로 클라이언트에서 필터**(음식점·쇼핑 제외).
- 명소 제목에 공백/부가어가 붙는다("해운대 해수욕장", "부산 감천문화마을") → 공백 무시 + "관광 타입 우선 · 키워드에 가장 근접(군더더기 최소)" 규칙으로 본 명소 선택.
- `totalCount=0`이면 `items`가 빈 문자열 → dict 아닐 때 None 처리.

### 4.3 해외 항공 (검색+예약)

| API | 무료·카드 | 예약 플로우 | 데이터 현실성 | 판정 |
|---|---|---|---|---|
| **Duffel** | 무료, 카드X, 1분 가입 | ✅ 우수(offer→order, 가상잔액 결제), 해커톤 스타터킷 | ❌ 가짜(Duffel Airways만) | ✅ **선택** |
| Amadeus Self-Service | 무료 테스트, 카드X | △ 다단계, 실패 잦음 | 진짜 항공사명(단 캐시 빈약) | 대안 |

### 4.4 해외 호텔 (검색+예약)

| API | 무료·카드 | 예약 플로우 | 데이터 | 판정 |
|---|---|---|---|---|
| **LiteAPI (Nuitée)** | 무료 샌드박스, 카드X | ✅ 구조화 응답, 에이전트 자율예약 설계 | ✅ 실호텔 3M+ | ✅ **선택** |
| Amadeus Self-Service | 무료 테스트, 카드X | △ | 빈약 | 대안 |
| Hotelbeds | 무료 Evaluation 키 | ✅ 2스텝 예약 | 실데이터 | 대안 |

### 4.5 날씨 (선택)

| API | 무료·카드 | 판정 |
|---|---|---|
| OpenWeatherMap | 무료 티어 | 여행 일정 보강용, 우선순위 낮음 |

## 5. Amadeus vs (Duffel + LiteAPI) — 결정 근거

항공·호텔을 Amadeus 하나로 통합할지, Duffel(항공)+LiteAPI(호텔)로 나눌지의 판단.

| 기준 | Amadeus | Duffel + LiteAPI |
|---|---|---|
| 예약→결제 플로우 | △ 복잡·불안정 | ✅ 깔끔·안정 |
| 데이터 현실성 | 항공 진짜(빈약)/호텔 빈약 | 항공 가짜/호텔 실데이터 |
| 개발자 경험 | OAuth+다단계 | ✅ 단순, 해커톤 스타터킷 |
| 에이전트 적합성 | 보통 | ✅ LiteAPI 에이전트용 설계 |

**결정**: 완성도(예약 플로우 안정성 + 에이전트 스토리) 기준으로 **Duffel + LiteAPI 채택.**
- 호텔은 LiteAPI가 데이터·예약·에이전트 설계 모두 우위 → 확실한 선택.
- 항공은 Duffel의 예약 플로우가 최고지만 데이터가 가짜인 점이 유일한 약점 → 아래 보완책.
- Amadeus를 중간 단계로 끼우는 것은 ROI가 낮아 제외 (mock 폴백이 그 자리를 대신함).

## 6. Provider 추상화 + 폴백 전략 (구현됨)

핵심 원칙: **호출부는 데이터 출처를 모른다.** `travel_service`는 구체 provider를 직접 알지 않고
`registry` 파사드만 부른다. provider는 공통 인터페이스(`base.Provider`: `name`·`supports`·`fetch`)를
따르고, `first_available`이 도메인 목록을 우선순위대로 시도한다. **provider 교체·추가는 registry 목록만 수정.**

```
travel_service  →  registry(도메인 파사드)  →  base.first_available(list, city)  ─┐
   get_attractions   ATTRACTIONS=[TourApi…]     for p in list:                    ├→ 첫 유효결과: 실데이터
   search_hotels     STAYS=[TourApi…]             if p.supports(city):            │
                                                     r = p.fetch(city) → 성공/None │
                     실패/전부 None ───────────────────────────────────────────────┴→ data/*.json (mock)
```

- 각 provider의 `supports(city)`가 국내/해외 등 커버리지를 판단 → 같은 도메인에 국내·해외 provider를 함께 등록 가능.
- `fetch`는 mock과 동일 스키마를 반환 → 카드 변환·프론트 재사용, 새 provider도 세 멤버만 구현.
- `USE_MOCK_ONLY=true`로 실 API를 전부 무시하고 mock만 쓰는 모드 지원(시연 대비).
- 키가 하나도 없어도 mock으로 전체 기능이 동작한다.

## 7. 항공 데이터 보완책 (Duffel 약점 대응)

Duffel 테스트는 실제 항공사가 아니라 가상 항공사(Duffel Airways)만 반환한다. 시연에서 어색할 수 있어 둘 중 택일(추후 결정):

- **(a) 감수** — "샌드박스라 항공편은 예시"로 넘기고 예약 플로우 완성도로 승부
- **(b) mock 병행** — 항공 검색 결과는 진짜 같은 한국 항공편 mock JSON으로 보여주고, 예약 단계 UX만 Duffel식으로

호텔(LiteAPI)은 실데이터라 이 이슈 없음.

## 8. 키 발급 · 링크 요약

| API | 발급처 | 카드 |
|---|---|---|
| OpenTripMap | https://dev.opentripmap.org/product | ❌ |
| Geoapify | https://www.geoapify.com/places-api/ | ❌ |
| TourAPI | https://www.data.go.kr/data/15101578/openapi.do | ❌ |

> **주의**: OpenTripMap 개발자 포털은 `dev.opentripmap.org`(키 발급·문서). `opentripmap.io`는 별개(구 소개 페이지)로 키 발급 경로가 아니다.
| Duffel | https://app.duffel.com/join | ❌ |
| LiteAPI | https://liteapi.travel/ | ❌ |
| OpenWeatherMap | https://openweathermap.org/api | ❌ |

## 9. 미결정 / 추후 확정

- 항공 데이터 보완책 (a) vs (b) — 실 연동 단계에서 결정
- Geoapify를 OpenTripMap 대신/병행으로 쓸지 — 실제 응답 품질 보고 결정
- 날씨(OpenWeatherMap) 포함 여부 — 시간 여유 보고 결정
