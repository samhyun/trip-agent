"""Provider registry — 도메인별 provider 목록과 파사드.

provider 교체·추가는 여기 목록만 바꾸면 된다. 각 provider의 `supports(city)`가 국내/해외를
구분하므로, 같은 도메인에 국내·해외 provider를 함께 등록하면 `first_available`이 도시에 맞는
것을 순서대로 시도한다. (국내 TourAPI → 해외 Geoapify/LiteAPI/Duffel, 모두 실패 시 mock)
"""

from app.providers import geoapify, liteapi, tour_api
from app.providers.base import Provider, Result, first_available

# 도메인별 provider (리스트 순서 = 우선순위). 국내 우선, 없으면 해외 provider가 커버.
# 항공은 왕복 조회라 단일 provider 함수(duffel.roundtrip)를 travel_service가 직접 부른다.
ATTRACTIONS: list[Provider] = [tour_api.TourApiAttractions(), geoapify.GeoapifyAttractions()]
STAYS: list[Provider] = [tour_api.TourApiStays(), liteapi.LiteApiStays()]


def attractions(city: str, limit: int = 8) -> Result | None:
    """명소 provider 파사드 (국내 TourAPI · 해외 Geoapify). 실패 시 None."""
    return first_available(ATTRACTIONS, city, limit)


def stays(city: str, limit: int = 6) -> Result | None:
    """숙박 provider 파사드 (국내 TourAPI · 해외 LiteAPI). 실패 시 None."""
    return first_available(STAYS, city, limit)
