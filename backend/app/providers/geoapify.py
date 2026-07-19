"""Geoapify Places provider — 해외 명소.

해외 도시의 대표 명소(큐레이션)를 Geoapify 지오코딩으로 조회해 실좌표·주소를 붙인다.
반환은 mock(`destinations.json`)과 동일한 attraction 스키마.
`GEOAPIFY_API_KEY`(.env)가 없거나 실패하면 None → 호출부가 mock 폴백.

엔드포인트: https://api.geoapify.com/v1/geocode/search (apiKey 쿼리 파라미터)
"""

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.intl import INTL_CITIES, supports_intl

logger = get_logger(__name__)

GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
TIMEOUT = 8.0

_CACHE: dict[tuple[str, int], list[dict]] = {}


def _geocode(query: str, api_key: str, country: str | None = None) -> dict | None:
    """지명/명소명 → 첫 지오코딩 결과(lat/lon/주소). country 지정 시 해당 국가로 한정. 실패 시 None."""
    params = {"text": query, "format": "json", "limit": 1, "apiKey": api_key}
    if country:
        params["filter"] = f"countrycode:{country.lower()}"  # 동명이지(예: 미국) 오매칭 방지
    try:
        r = httpx.get(GEOCODE_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0] if results else None
    except Exception as exc:  # noqa: BLE001 - 실패는 mock 폴백
        logger.warning("Geoapify geocode 실패(%s): %s", query, exc)
        return None


def search_attractions(city: str, limit: int = 6) -> list[dict] | None:
    """해외 도시의 대표 명소를 attraction 스키마로 반환."""
    meta = INTL_CITIES.get(city)
    if not meta or not get_settings().has_geoapify:
        return None
    if (city, limit) in _CACHE:
        return _CACHE[(city, limit)]

    api_key = get_settings().geoapify_api_key
    result: list[dict] = []
    for i, spot in enumerate(meta["spots"]):
        if len(result) >= limit:
            break
        r0 = _geocode(f"{spot}, {meta['en']}", api_key, meta.get("country"))
        if not r0 or "lat" not in r0:
            continue
        result.append(
            {
                "id": r0.get("place_id") or f"{city}-geo-{i}",
                "name": spot,
                "area": r0.get("city") or r0.get("county") or meta["en"],
                "tags": ["관광"],
                "desc": r0.get("formatted", ""),
                "gradient": i % 6,
                "lat": r0["lat"],
                "lng": r0["lon"],
            }
        )
    if not result:
        return None
    logger.info("Geoapify attractions[%s] %d개", city, len(result))
    _CACHE[(city, limit)] = result
    return result


class GeoapifyAttractions:
    """해외 명소 provider (base.Provider 규약)."""

    name = "geoapify.attractions"

    def supports(self, city: str) -> bool:
        return supports_intl(city) and get_settings().has_geoapify

    def fetch(self, city: str, limit: int = 6) -> list[dict] | None:
        return search_attractions(city, limit)
