"""한국관광공사 TourAPI (KorService2) provider — 국내 관광지·숙박.

공공데이터포털 "한국관광공사_국문 관광정보 서비스_GW".
엔드포인트: https://apis.data.go.kr/B551011/KorService2
- searchKeyword2  : 키워드 관광지 검색
- areaBasedList2  : 지역기반 관광지 목록 (contentTypeId=12 관광지)
- searchStay2     : 숙박정보

반환값은 mock 데이터(`data/destinations.json`·`hotels.json`)와 **같은 스키마**로
정규화한다. `TOUR_API_KEY`(.env)가 없거나 호출이 실패하면 None/[]을 돌려주고,
호출부(travel_service)가 mock으로 폴백한다.

인증키 주의: 포털의 Decoding 키(`/`,`+`,`=` 포함)를 `.env`에 넣는다. 코드가 httpx
params로 한 번 인코딩하므로, 이미 인코딩된(Encoding) 키가 들어와도 자동 감지해 unquote 한다.
"""

from urllib.parse import unquote

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://apis.data.go.kr/B551011/KorService2"
TIMEOUT = 6.0

# 도시명 → 관광공사 지역코드(areaCode). 국내 도시만 등록(없으면 TourAPI 미대상 → mock).
AREA_CODES: dict[str, str] = {
    "서울": "1",
    "인천": "2",
    "대전": "3",
    "대구": "4",
    "광주": "5",
    "부산": "6",
    "울산": "7",
    "세종": "8",
    "경기": "31",
    "강원": "32",
    "충북": "33",
    "충남": "34",
    "경북": "35",
    "경남": "36",
    "전북": "37",
    "전남": "38",
    "제주": "39",
}

# 도시별 큐레이션된 대표 명소 키워드. areaBasedList는 인기순 정렬이 없어 무명 항목이
# 먼저 나오므로, 유명 명소는 searchKeyword2로 조회한다(주소·좌표는 실데이터). 목록이 없는
# 도시는 areaBasedList2(제목순)로 폴백.
FAMOUS_SPOTS: dict[str, list[str]] = {
    "제주": ["성산일출봉", "한라산", "우도", "천지연폭포", "협재해수욕장", "만장굴", "카멜리아힐", "정방폭포"],
    "부산": ["해운대해수욕장", "광안리해수욕장", "감천문화마을", "태종대", "자갈치시장", "국제시장", "해동용궁사", "송도해상케이블카"],
}

# cat1(대분류) → 카드용 한 줄 태그.
_CAT1_TAG: dict[str, str] = {
    "A01": "자연",
    "A02": "인문",
    "A03": "레포츠",
    "A04": "쇼핑",
    "A05": "맛집",
    "B02": "숙박",
    "C01": "추천코스",
}

# 세션 내 반복 호출 방지용 캐시 (성공 결과만 저장). 키=(종류, 도시, limit).
_CACHE: dict[tuple, list[dict]] = {}


def supports(city: str) -> bool:
    """TourAPI로 조회 가능한 국내 도시인지."""
    return city in AREA_CODES


def _service_key() -> str:
    """Decoding 키를 반환. Encoding 키가 들어오면 unquote 해 이중 인코딩을 막는다."""
    key = get_settings().tour_api_key
    return unquote(key) if "%" in key else key


def _call(operation: str, **params) -> list[dict] | None:
    """KorService2 오퍼레이션 호출 → item 리스트. 실패/빈결과는 None."""
    query = {
        "serviceKey": _service_key(),
        "MobileOS": "ETC",
        "MobileApp": "TripAgent",
        "_type": "json",
        "numOfRows": params.pop("numOfRows", 20),
        "pageNo": 1,
        **params,
    }
    try:
        resp = httpx.get(f"{BASE_URL}/{operation}", params=query, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()  # 오류 시 XML이면 JSONDecodeError → except
    except Exception as exc:  # noqa: BLE001 - 모든 실패는 mock 폴백으로 흡수
        logger.warning("TourAPI %s 실패: %s", operation, exc)
        return None

    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") not in ("0000", "00", None):
        logger.warning("TourAPI %s 응답코드=%s (%s)", operation, header.get("resultCode"), header.get("resultMsg"))
        return None

    body = data.get("response", {}).get("body", {})
    items = body.get("items")
    if not items or not isinstance(items, dict):  # totalCount=0 이면 items=""(빈 문자열)
        return None
    item = items.get("item", [])
    return item if isinstance(item, list) else [item]


def _sigungu(addr1: str | None, fallback: str) -> str:
    """주소에서 시/군/구 토큰 추출. '제주특별자치도 서귀포시 …' → '서귀포시'."""
    if not addr1:
        return fallback
    parts = addr1.split()
    return parts[1] if len(parts) > 1 else parts[0]


def _https(url: str | None) -> str | None:
    """관광공사 이미지가 http로 오면 https로 승격(https 배포 시 mixed-content 차단 방지)."""
    return url.replace("http://", "https://", 1) if url and url.startswith("http://") else url


def _coords(item: dict) -> dict:
    """mapx(경도)·mapy(위도) → lat/lng (동선 최적화용). 없으면 빈 dict."""
    try:
        return {"lat": float(item["mapy"]), "lng": float(item["mapx"])}
    except (KeyError, ValueError, TypeError):
        return {}


# 관광 성격 콘텐츠 타입(관광지·문화시설·축제·여행코스·레포츠). 음식점(39)·쇼핑(38)·숙박(32) 제외.
_SIGHT_TYPES = {"12", "14", "15", "25", "28"}


def _best_match(items: list[dict], keyword: str) -> dict | None:
    """키워드를 제목에 포함하는 항목 중 최적 명소를 고른다(공백 무시).

    우선순위: ① 관광 타입(음식점·쇼핑 등 제외) → ② 제목이 키워드에 가장 근접(군더더기 최소).
    예) '성산일출봉' → 음식점 '성산흑돼지…성산일출봉점'이 아니라 관광지 '성산일출봉…'을,
        '감천문화마을' → '어린왕자 전시관'·'기념품숍'이 아니라 '부산 감천문화마을'을 고른다.
    포함 항목이 없으면 None.
    """
    kw = keyword.replace(" ", "")
    matches = [it for it in items if kw in it.get("title", "").replace(" ", "")]
    if not matches:
        return None

    def rank(it: dict) -> tuple[int, int]:
        title = it.get("title", "").replace(" ", "")
        not_sight = 0 if str(it.get("contenttypeid")) in _SIGHT_TYPES else 1
        extra = len(title) - len(kw)  # 키워드 외 군더더기 글자 수(0=정확 일치)
        return (not_sight, extra)

    return min(matches, key=rank)


def _to_attraction(it: dict, city: str, i: int) -> dict:
    """TourAPI item → destination attraction 스키마."""
    cat1 = it.get("cat1", "")
    tags = [_CAT1_TAG[cat1]] if cat1 in _CAT1_TAG else []
    return {
        "id": it.get("contentid") or f"{city}-tour-{i}",
        "name": it.get("title", "").strip(),
        "area": _sigungu(it.get("addr1"), city),
        "tags": tags,
        "desc": (it.get("addr1") or "").strip(),
        "gradient": i % 6,
        "image": _https(it.get("firstimage") or it.get("firstimage2")),
        **_coords(it),
    }


def search_attractions(city: str, limit: int = 8) -> list[dict] | None:
    """국내 도시의 관광지를 destination attraction 스키마로 반환.

    큐레이션된 유명 명소가 있으면 searchKeyword2로 조회하고(실주소·좌표),
    없으면 areaBasedList2(제목순)로 폴백. attraction = {id, name, area, tags, desc, gradient, (lat, lng)}
    """
    area_code = AREA_CODES.get(city)
    if not area_code or not get_settings().has_tour_api:
        return None
    cache_key = ("attractions", city, limit)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    result: list[dict] = []
    for kw in FAMOUS_SPOTS.get(city, []):
        if len(result) >= limit:
            break
        # areaCode·contentTypeId 미지정(둘 다 걸면 정확한 명소명이 0건 나오는 TourAPI 특성).
        # 큐레이션 키워드가 도시별로 명확해 필터 없이도 안전하며, 여러 후보 중 제목 최적매칭.
        items = _call("searchKeyword2", keyword=kw, numOfRows=10)
        best = _best_match(items, kw) if items else None
        if best:
            result.append(_to_attraction(best, city, len(result)))

    if not result:  # 큐레이션 없음/전부 실패 → 지역기반 목록(제목순)
        items = _call("areaBasedList2", areaCode=area_code, contentTypeId=12, arrange="O", numOfRows=limit)
        if not items:
            return None
        result = [_to_attraction(it, city, i) for i, it in enumerate(items[:limit])]

    logger.info("TourAPI attractions[%s] %d개", city, len(result))
    _CACHE[cache_key] = result
    return result


def search_stays(city: str, limit: int = 6) -> list[dict] | None:
    """국내 도시의 숙박을 hotel 스키마로 반환.

    hotel = {id, name, area, price_per_night, rating, tags, gradient, (lat, lng)}
    ※ TourAPI는 요금·평점을 제공하지 않아, 데모 표시용으로 contentid 기반 결정적 값을 부여한다.
    """
    area_code = AREA_CODES.get(city)
    if not area_code or not get_settings().has_tour_api:
        return None
    cache_key = ("stays", city, limit)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    items = _call("searchStay2", areaCode=area_code, arrange="O", numOfRows=limit)
    if not items:
        return None

    result = []
    for i, it in enumerate(items[:limit]):
        cid = it.get("contentid") or f"{city}-stay-{i}"
        tags = _stay_tags(it)
        result.append(
            {
                "id": cid,
                "name": it.get("title", "").strip(),
                "area": _sigungu(it.get("addr1"), city),
                "price_per_night": _demo_price(cid),
                "rating": _demo_rating(cid),
                "tags": tags,
                "gradient": i % 6,
                "image": _https(it.get("firstimage") or it.get("firstimage2")),
                **_coords(it),
            }
        )
    logger.info("TourAPI stays[%s] %d개", city, len(result))
    _CACHE[cache_key] = result
    return result


def _stay_tags(item: dict) -> list[str]:
    """숙박 부가정보 플래그 → 태그. 없으면 지역 태그."""
    tags = []
    if item.get("hanok") == "1":
        tags.append("한옥")
    if item.get("benikia") == "1":
        tags.append("베니키아")
    if item.get("goodstay") == "1":
        tags.append("굿스테이")
    return tags or [_sigungu(item.get("addr1"), "숙소")]


def _demo_price(cid: str) -> int:
    """contentid 기반 결정적 1박 요금(80,000~220,000, 천원 단위). 데모 표시용."""
    h = sum(ord(c) for c in str(cid))
    return 80000 + (h % 141) * 1000


def _demo_rating(cid: str) -> float:
    """contentid 기반 결정적 평점(4.0~4.9). 데모 표시용."""
    h = sum(ord(c) for c in str(cid))
    return round(4.0 + (h % 10) / 10, 1)


# ----- Provider 인터페이스 구현 (registry 등록용) -----

def _enabled(city: str) -> bool:
    """국내 커버 도시이고 키가 설정됐을 때만 provider 활성."""
    return supports(city) and get_settings().has_tour_api


class TourApiAttractions:
    """국내 관광지 provider (base.Provider 규약)."""

    name = "tour_api.attractions"

    def supports(self, city: str) -> bool:
        return _enabled(city)

    def fetch(self, city: str, limit: int = 8) -> list[dict] | None:
        return search_attractions(city, limit)


class TourApiStays:
    """국내 숙박 provider (base.Provider 규약)."""

    name = "tour_api.stays"

    def supports(self, city: str) -> bool:
        return _enabled(city)

    def fetch(self, city: str, limit: int = 6) -> list[dict] | None:
        return search_stays(city, limit)
