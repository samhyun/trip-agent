"""Geoapify Places provider — 해외 명소.

해외 도시의 대표 명소(큐레이션)를 Geoapify 지오코딩으로 조회해 실좌표·주소를 붙인다.
반환은 mock(`destinations.json`)과 동일한 attraction 스키마.
`GEOAPIFY_API_KEY`(.env)가 없거나 실패하면 None → 호출부가 mock 폴백.

엔드포인트: https://api.geoapify.com/v1/geocode/search (apiKey 쿼리 파라미터)
"""

from concurrent.futures import ThreadPoolExecutor

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger, redact
from app.providers import photos
from app.providers.intl import INTL_CITIES, supports_intl

logger = get_logger(__name__)

GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
PLACES_URL = "https://api.geoapify.com/v2/places"
TIMEOUT = 5.0  # 명소 6개 직렬 조회 → 최악 지연 억제

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
        logger.warning("Geoapify geocode 실패(%s): %s", query, redact(exc))
        return None


def _photos_parallel(names: list[str]) -> dict[str, str | None]:
    """명소명 목록 → {이름: 사진URL}. Wikipedia 조회를 병렬화(직렬 타임아웃 누적 방지)."""
    if not names:
        return {}
    with ThreadPoolExecutor(max_workers=min(6, len(names))) as ex:
        return dict(zip(names, ex.map(photos.photo_for, names)))


def _one_spot(city: str, meta: dict, api_key: str, i: int, spot: str) -> dict | None:
    """명소 하나를 지오코딩 + Wikipedia 사진으로 정형화. 좌표 못 얻으면 None."""
    r0 = _geocode(f"{spot}, {meta['en']}", api_key, meta.get("country"))
    if not r0 or "lat" not in r0:
        return None
    return {
        "id": r0.get("place_id") or f"{city}-geo-{i}",
        "name": spot,
        "area": r0.get("city") or r0.get("county") or meta["en"],
        "tags": ["관광"],
        "desc": r0.get("formatted", ""),
        "gradient": i % 6,
        "lat": r0["lat"],
        "lng": r0["lon"],
        "image": photos.photo_for(spot),  # Wikipedia 대표 사진(없으면 None→그라디언트)
    }


def _curated_spots(city: str, meta: dict, spots: list[str], api_key: str, limit: int) -> list[dict]:
    """큐레이션 명소들을 병렬 지오코딩+사진으로 붙인다(직렬 타임아웃 누적 방지). 순서 유지."""
    targets = list(enumerate(spots))
    with ThreadPoolExecutor(max_workers=min(6, len(targets) or 1)) as ex:
        rows = ex.map(lambda t: _one_spot(city, meta, api_key, t[0], t[1]), targets)
    return [r for r in rows if r][:limit]


def _places_near(city: str, lat, lng, api_key: str, limit: int) -> list[dict]:
    """큐레이션 명소가 없는 도시(자동 해석): 좌표 주변 관광지(tourism.sights)를 조회."""
    if lat is None or lng is None:
        return []
    try:
        r = httpx.get(
            PLACES_URL,
            params={
                "categories": "tourism.sights",  # 랜드마크·명소(카페·상점 등 제외)
                "conditions": "named",  # 이름 있는 곳만
                "filter": f"circle:{lng},{lat},20000",  # 반경 20km
                "bias": f"proximity:{lng},{lat}",
                "limit": limit * 4,  # 잡음 걸러낼 여유
                "apiKey": api_key,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        feats = r.json().get("features", [])
    except Exception as exc:  # noqa: BLE001 - 실패는 mock 폴백
        logger.warning("Geoapify places 실패(%s): %s", city, redact(exc))
        return []
    named = [p for f in feats if (p := f.get("properties") or {}).get("name")][:limit]
    imgs = _photos_parallel([p["name"] for p in named])  # 사진 병렬 조회(직렬 지연 방지)
    result: list[dict] = []
    for p in named:
        result.append(
            {
                "id": p.get("place_id") or f"{city}-near-{len(result)}",
                "name": p["name"],
                "area": p.get("city") or p.get("suburb") or city,
                "tags": ["관광"],
                "desc": p.get("formatted", ""),
                "gradient": len(result) % 6,
                "lat": p.get("lat"),
                "lng": p.get("lon"),
                "image": imgs.get(p["name"]),  # Wikipedia 대표 사진(없으면 None→그라디언트)
            }
        )
    return result


def search_attractions(city: str, limit: int = 6) -> list[dict] | None:
    """해외 도시의 대표 명소를 attraction 스키마로 반환.

    큐레이션 명소가 있으면 지오코딩(정확), 없으면(자동 해석 도시) 좌표 주변 관광지로 대체.
    """
    meta = INTL_CITIES.get(city)
    if not meta or not get_settings().has_geoapify:
        return None
    if (city, limit) in _CACHE:
        return _CACHE[(city, limit)]

    api_key = get_settings().geoapify_api_key
    spots = meta.get("spots") or []
    if spots:
        result = _curated_spots(city, meta, spots, api_key, limit)
    else:
        result = _places_near(city, meta.get("lat"), meta.get("lng"), api_key, limit)
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
