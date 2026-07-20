"""여행 도메인 조회 로직.

현재는 mock 데이터(`data_loader`)를 조회한다. 실 provider는 이후 각 함수에서
"실 API 시도 → 실패/키없음 → 아래 mock" 순으로 폴백하도록 확장한다.
"""

import re
from datetime import datetime

from app.core.config import get_settings
from app.providers import registry
from app.services.data_loader import load


# ----- 여행지 / 명소 -----

def find_cities(text: str) -> list[str]:
    """입력 문장에서 알려진 도시명을 모두 찾는다 (멀티 목적지 지원)."""
    destinations = load("destinations")
    return [city for city in destinations if city in text]


def get_destination(city: str) -> dict | None:
    """도시 정보(요약·명소)를 반환."""
    return load("destinations").get(city)


def get_attractions(city: str) -> list[dict]:
    """도시의 명소 목록. provider(국내 TourAPI 등) 우선, 실패/빈결과 시 mock 폴백."""
    if not mock_only():
        live = registry.attractions(city)
        if live:
            return live
    dest = get_destination(city)
    return dest["attractions"] if dest else []


# ----- 항공 -----

def search_flights(query_or_city: str) -> dict | None:
    """도시행 날짜별 항공권. 해외는 provider(Duffel) 우선, 국내/실패 시 mock 폴백."""
    if not mock_only():
        for city in find_cities(query_or_city):
            live = registry.flights(city)
            if live:
                return live
    flights = load("flights")
    for route_key, info in flights.items():
        cities = route_key.split("-")
        if any(city in query_or_city for city in cities):
            return {"route_key": route_key, **info}
    return None


# ----- 숙소 -----

def search_hotels(city: str, area: str | None = None) -> list[dict]:
    """도시(+지역 필터)의 숙소 목록. provider(국내 TourAPI 등) 우선, 실패/빈결과 시 mock 폴백."""
    hotels = None
    if not mock_only():
        hotels = registry.stays(city)
    if not hotels:
        hotels = load("hotels").get(city, [])
    if area:
        hotels = [h for h in hotels if area in h["area"]]
    return hotels


# ----- 액티비티 -----

def search_activities(city: str) -> list[dict]:
    """도시의 액티비티 목록."""
    return load("activities").get(city, [])


# ----- 프론트 카드 페이로드 변환 -----
# 프론트 리치카드 컴포넌트(frontend/src/components/messages/*)가 기대하는 스키마에
# 맞춰 조회 결과를 정형화한다. (계약: docs/design.md 프론트 연동)

_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def _date_key(iso: str) -> tuple[str, str]:
    """'2026-07-24' → ('7.24', '금'). 프론트 date-pill 표기용."""
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.month}.{d.day}", _WEEKDAYS[d.weekday()]


def build_destination_payload(city: str, attractions: list[dict]) -> dict:
    """destination_carousel 카드 페이로드 (프론트 DestinationCarousel 계약).

    item = {id, name, tags(#접두), gradient, area, desc}
    """
    items = [
        {
            "id": a.get("id") or f"{city}-spot-{i}",
            "name": a["name"],
            "tags": [f"#{t}" for t in a.get("tags", [])],
            "gradient": a.get("gradient", i),
            "area": a.get("area"),
            "desc": a.get("desc", ""),
            "image": a.get("image"),
        }
        for i, a in enumerate(attractions)
    ]
    return {"city": city, "items": items}


def build_flight_payload(flights: dict) -> dict:
    """flight_results 카드 페이로드 (프론트 FlightResults byDate 계약).

    {mode:'byDate', route, dates:[{key,wd,price,low}], flightsByDate:{key:[{air,dep,arr,dur,price,tag,route}]}}
    """
    date_prices = flights.get("date_prices", [])
    duration = flights.get("duration", "")
    route = flights.get("route", flights.get("route_key", ""))
    lowest_overall = min((dp["lowest"] for dp in date_prices), default=None)

    dates: list[dict] = []
    flights_by_date: dict[str, list[dict]] = {}
    for dp in date_prices:
        key, wd = _date_key(dp["date"])
        # key/label 은 표시용, isoDate 는 프론트의 식별·날짜 계산용(월말 오버플로 방지)
        dates.append(
            {
                "key": key,
                "isoDate": dp["date"],
                "wd": wd,
                "price": dp["lowest"],
                "low": dp["lowest"] == lowest_overall,
            }
        )
        cheapest = min((f["price"] for f in dp["flights"]), default=None)
        cards = []
        for f in dp["flights"]:
            card = {
                "air": f["airline"],
                "dep": f["dep"],
                "arr": f["arr"],
                "dur": duration,
                "price": f["price"],
                "route": route,
            }
            if f["price"] == cheapest and dp["lowest"] == lowest_overall:
                card["tag"] = "최저가"
            cards.append(card)
        flights_by_date[key] = cards

    return {"mode": "byDate", "route": route, "dates": dates, "flightsByDate": flights_by_date}


def build_hotel_payload(city: str, hotels: list[dict], sort: str | None = None) -> dict:
    """hotel_results 카드 페이로드 (프론트 HotelResults 계약).

    sort="price"면 가격 낮은순, 그 외엔 평점 높은순으로 정렬한다.
    {city, cityLabel, banner, regions?, hotels:[{id,name,region,meta,price,rating,gradient,image}]}
    """
    def _price(h):
        p = h.get("price", h.get("price_per_night"))
        return p if isinstance(p, (int, float)) and p > 0 else float("inf")  # 가격 미확인은 맨 뒤로

    if sort == "price":
        hotels = sorted(hotels, key=_price)
        label = "가격 낮은순"
    else:
        hotels = sorted(hotels, key=lambda h: -(h.get("rating") or 0))
        label = "평점 높은순"

    areas: list[str] = []
    cards = []
    for i, h in enumerate(hotels):
        area = h.get("area", city)
        if area not in areas:
            areas.append(area)
        # id·gradient는 정렬 순서와 무관하게 숙소 고유값 기준(선택 상태·렌더 키 안정)
        stable = sum(ord(c) for c in h.get("name", ""))
        cards.append(
            {
                "id": h.get("id") or f"{city}-{h.get('name', 'hotel')}",
                "name": h["name"],
                "region": area,
                "meta": " · ".join(h.get("tags", [])),
                "price": h.get("price", h.get("price_per_night", 0)),
                "rating": h.get("rating"),
                "gradient": h.get("gradient", stable % 6),
                "image": h.get("image"),
            }
        )
    payload = {
        "city": city,
        "cityLabel": city,
        "banner": f"{city} 숙소 · {label}",
        "hotels": cards,
    }
    if len(areas) > 1:
        payload["regions"] = ["전체", *areas]
    return payload


def parse_people(text: str, default: int = 2) -> int:
    """대화 텍스트에서 인원 추출. 못 얻으면 기본값(2)."""
    m = re.search(r"(\d+)\s*(명|인|사람)", text)
    if m:
        return int(m.group(1))
    if "혼자" in text:
        return 1
    if "둘이" in text or "두 명" in text or "두명" in text:
        return 2
    return default


def parse_nights(text: str, default: int = 3) -> int:
    """대화 텍스트에서 숙박 박수 추출. 못 얻으면 기본값(3)."""
    m = re.search(r"(\d+)\s*박", text)
    return int(m.group(1)) if m else default


def estimate_total(cities: list[str], travelers: int = 2, nights: int = 3) -> int:
    """확정서용 개략 합계 = 최저가 항공×인원 + 최저가 숙소×박수. 프론트가 실제 선택가로 덮어쓴다."""
    total = 0
    for city in cities:
        flights = search_flights(city)
        if flights and flights.get("date_prices"):
            cheapest_flight = min(dp["lowest"] for dp in flights["date_prices"])
            total += cheapest_flight * travelers
        hotels = load("hotels").get(city, [])
        if hotels:
            cheapest_hotel = min(h.get("price_per_night", 0) for h in hotels)
            total += cheapest_hotel * nights
    return total


# ----- 결제(더미) -----

def make_confirmation(prefix: str = "TA") -> str:
    """더미 예약 확정번호 생성 (예: TA-20260725-0007)."""
    now = datetime.now()
    seq = now.microsecond % 10000
    return f"{prefix}-{now:%Y%m%d}-{seq:04d}"


def mock_only() -> bool:
    """실 provider를 무시하고 mock만 쓸지 여부."""
    return get_settings().use_mock_only
