"""해외 임의 도시 자동 해석 (place resolver).

coordinator가 뽑은 목적지 영문명(예: 'Langkawi')을 Geoapify 지오코딩(좌표·국가)과
Duffel Places(대표 공항 IATA)로 해석해 INTL_CITIES에 런타임 등록한다. 이후 명소(Geoapify)·
호텔(LiteAPI)·항공(Duffel) provider가 등록된 메타로 조회하므로, 큐레이션되지 않은 도시도 커버한다.

한글 도시명은 각 API 인식률이 낮아, LLM이 뽑은 영문명(destination_en)을 조회 키로 쓴다.
등록된 도시는 INTL_CITIES에 남아 다음 조회부터 재해석 없이 재사용된다(프로세스 내 캐시).
"""

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger, redact
from app.providers.intl import INTL_CITIES

logger = get_logger(__name__)

GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
DUFFEL_PLACES_URL = "https://api.duffel.com/places/suggestions"
TIMEOUT = 6.0


def _geocode(name_en: str, api_key: str) -> dict | None:
    """영문 도시명 → 첫 지오코딩 결과(lat/lon/country_code/city). 실패 시 None."""
    try:
        r = httpx.get(
            GEOCODE_URL,
            params={"text": name_en, "format": "json", "limit": 1, "apiKey": api_key},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0] if results else None
    except Exception as exc:  # noqa: BLE001 - 실패는 미지원 처리
        logger.warning("place geocode 실패(%s): %s", name_en, redact(exc))
        return None


def _airport(name_en: str, api_key: str) -> str | None:
    """영문 도시명 → 대표 공항 IATA (Duffel Places). 실패 시 None(항공만 미커버)."""
    try:
        r = httpx.get(
            DUFFEL_PLACES_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Duffel-Version": "v2",
                "Accept": "application/json",
            },
            params={"query": name_en},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("place airport 실패(%s): %s", name_en, redact(exc))
        return None
    for p in data:  # 공항 타입 우선
        if p.get("type") == "airport" and p.get("iata_code"):
            return p["iata_code"]
    for p in data:  # 도시에 딸린 대표 공항
        for a in p.get("airports") or []:
            if a.get("iata_code"):
                return a["iata_code"]
    return None


def resolve(ko: str, en: str) -> dict | None:
    """한글 목적지(ko)+영문명(en)을 좌표·국가·공항으로 해석해 INTL_CITIES에 등록. 실패 시 None.

    이미 등록/큐레이션된 도시면 재조회 없이 그대로 반환. 영문명이 없거나 좌표 해석 실패면 None.
    """
    if ko in INTL_CITIES:
        return INTL_CITIES[ko]
    en = (en or "").strip()
    if not en:
        return None
    s = get_settings()
    if not s.has_geoapify:  # 좌표·국가 해석 불가 → 지원 불가
        return None
    geo = _geocode(en, s.geoapify_api_key)
    if not geo or "lat" not in geo:
        return None
    # 신뢰도 낮은 결과는 등록하지 않음(오역·동명지역 캐시 고착 방지).
    country = (geo.get("country_code") or "").upper()
    result_type = geo.get("result_type") or ""
    if not country:
        logger.info("place resolve[%s→%s] 국가 불명 → 미등록", ko, en)
        return None
    if country == "KR":
        # 국내는 TourAPI가 담당(현재 제주·부산만 지원). 해외 provider로 오라우팅 방지
        logger.info("place resolve[%s→%s] 국내(KR) → 미등록", ko, en)
        return None
    # 도시명이 국가·도로·건물 등 도시 아닌 지점으로 잘못 매칭되면 거른다
    # (도시/카운티/주/구 등 지역 유형은 정상 — 랑카위=county, 세부=state).
    if result_type in ("street", "amenity", "building", "country"):
        logger.info("place resolve[%s→%s] 도시 아님(type=%s) → 미등록", ko, en, result_type)
        return None
    # postcode는 일본 등에서 정상 도시도 이 유형으로 매칭된다(이시가키 등).
    # 결과의 city가 검색 영문명과 실질 일치할 때만 도시로 인정한다(무관한 도시의 우편번호 오매칭 방지).
    if result_type == "postcode":
        city_name = (geo.get("city") or "").strip().lower()
        query = en.lower()
        if not city_name or (city_name not in query and query not in city_name):
            logger.info("place resolve[%s→%s] 우편번호 매칭(city=%r 불일치) → 미등록", ko, en, geo.get("city"))
            return None
    conf = (geo.get("rank") or {}).get("confidence")  # 매칭 신뢰도(정상 도시=1.0)
    if isinstance(conf, (int, float)) and conf < 0.5:
        logger.info("place resolve[%s→%s] 신뢰도 낮음(conf=%.2f) → 미등록", ko, en, conf)
        return None
    airport = _airport(en, s.duffel_api_key) if s.has_duffel else None
    meta = {
        "en": en,
        "country": country,
        "airport": airport,
        "spots": [],  # 큐레이션 명소 없음 → Geoapify 좌표 주변 명소로 대체
        "stay_city": geo.get("city") or en,
        "lat": geo.get("lat"),
        "lng": geo.get("lon"),
    }
    INTL_CITIES[ko] = meta  # 런타임 등록 → 이후 provider가 이 도시를 인식
    logger.info("place resolve[%s→%s] country=%s airport=%s", ko, en, country or "?", airport or "-")
    return meta
