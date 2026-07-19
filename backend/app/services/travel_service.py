"""여행 도메인 조회 로직.

현재는 mock 데이터(`data_loader`)를 조회한다. 실 provider는 이후 각 함수에서
"실 API 시도 → 실패/키없음 → 아래 mock" 순으로 폴백하도록 확장한다.
"""

from datetime import datetime

from app.core.config import get_settings
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
    """도시의 명소 목록."""
    dest = get_destination(city)
    return dest["attractions"] if dest else []


# ----- 항공 -----

def search_flights(query_or_city: str) -> dict | None:
    """도시명이 포함된 노선의 날짜별 가격을 반환."""
    flights = load("flights")
    for route_key, info in flights.items():
        cities = route_key.split("-")
        if any(city in query_or_city for city in cities):
            return {"route_key": route_key, **info}
    return None


# ----- 숙소 -----

def search_hotels(city: str, area: str | None = None) -> list[dict]:
    """도시(+지역 필터)의 숙소 목록."""
    hotels = load("hotels").get(city, [])
    if area:
        hotels = [h for h in hotels if area in h["area"]]
    return hotels


# ----- 액티비티 -----

def search_activities(city: str) -> list[dict]:
    """도시의 액티비티 목록."""
    return load("activities").get(city, [])


# ----- 결제(더미) -----

def make_confirmation(prefix: str = "TA") -> str:
    """더미 예약 확정번호 생성 (예: TA-20260725-0007)."""
    now = datetime.now()
    seq = now.microsecond % 10000
    return f"{prefix}-{now:%Y%m%d}-{seq:04d}"


def mock_only() -> bool:
    """실 provider를 무시하고 mock만 쓸지 여부."""
    return get_settings().use_mock_only
