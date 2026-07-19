"""해외 provider 공통 메타 (도시 매핑·환율).

해외 도시(한글명) → 영문명·국가코드·공항코드·대표 명소. 해외 명소(Geoapify)·항공(Duffel)·
호텔(LiteAPI) provider가 공유한다. 국내 출발지는 인천(ICN) 고정.
"""

ORIGIN_AIRPORT = "ICN"  # 국내 출발 공항 (인천)
USD_KRW = 1350  # 데모용 고정 환율 (실서비스는 환율 API로 대체)

# 해외 도시 메타. 여기 없는 도시는 해외 provider가 커버하지 않음(→ 국내 provider/mock).
INTL_CITIES: dict[str, dict] = {
    "세부": {
        "en": "Cebu",
        "country": "PH",
        "airport": "CEB",
        "spots": [
            "Magellan's Cross", "Basilica del Santo Niño", "Fort San Pedro",
            "Temple of Leah", "Sirao Flower Garden", "Tops Lookout",
        ],
    },
    "보홀": {
        "en": "Bohol",
        "country": "PH",
        "airport": "TAG",
        "stay_city": "Panglao",  # 호텔 조회용(리조트 밀집지 팡라오). 섬명 Bohol은 결과가 적음
        "spots": [
            "Chocolate Hills", "Alona Beach", "Loboc River Cruise",
            "Tarsier Sanctuary", "Hinagdanan Cave", "Blood Compact Shrine",
        ],
    },
}


def supports_intl(city: str) -> bool:
    """해외 provider 커버 도시인지."""
    return city in INTL_CITIES


def to_krw(usd, unit: int = 1000) -> int:
    """USD → KRW (unit 단위 반올림). 데모 표시용."""
    return int(round(float(usd) * USD_KRW / unit) * unit)
