"""LangChain 툴 (@tool).

워커 에이전트가 호출한다. 각 툴은 `travel_service`를 감싸 조회 결과를 LLM이 읽기 좋은
문자열로 반환한다. 데이터 출처(mock/실 API)는 서비스 레이어가 결정하므로 툴은 알지 못한다.
"""

from langchain_core.tools import tool

from app.services import travel_service as ts


@tool
def search_destination_info(query: str) -> str:
    """여행지·명소 정보를 조회한다. query에 도시명(제주·부산·세부·보홀 등)을 포함하면
    해당 도시의 요약과 대표 명소를 돌려준다. 멀티 목적지도 함께 조회된다."""
    cities = ts.find_cities(query)
    if not cities:
        return "알려진 여행지를 찾지 못했어요. 도시명을 알려주세요."
    parts = []
    for city in cities:
        dest = ts.get_destination(city)
        names = ", ".join(a["name"] for a in dest["attractions"][:5])
        parts.append(f"[{city}] {dest['summary']}\n  대표 명소: {names}")
    return "\n".join(parts)


@tool
def search_flights(city: str) -> str:
    """도시행 왕복 항공권(가는 편+오는 편)을 조회한다."""
    flight = ts.search_flights(city)
    if not flight:
        return f"'{city}' 노선 항공권을 찾지 못했어요."
    lines = [f"{flight.get('route', '항공')} 왕복 ({flight.get('depDate')}~{flight.get('returnDate')})"]
    for f in flight.get("flights", []):
        inb = f" / 오는 {f['inDep']}" if f.get("inDep") else ""
        lines.append(f"  {f['air']} · 가는 {f['outDep']}{inb} · {f['price']:,}원")
    return "\n".join(lines)


@tool
def search_hotels(city: str, area: str = "") -> str:
    """도시(+선택 지역)의 숙소 목록을 가격·평점과 함께 조회한다."""
    hotels = ts.search_hotels(city, area or None)
    if not hotels:
        return f"'{city}' 숙소를 찾지 못했어요."
    return "\n".join(
        f"{h['name']} ({h['area']}) · {h['price_per_night']:,}원/박 · ★{h['rating']} · {', '.join(h['tags'])}"
        for h in hotels
    )


@tool
def search_activities(city: str) -> str:
    """도시의 액티비티·투어를 조회한다."""
    acts = ts.search_activities(city)
    if not acts:
        return f"'{city}' 액티비티를 찾지 못했어요."
    return "\n".join(f"{a['name']} · {a['price']:,}원 · {a['duration']}" for a in acts)


@tool
def process_payment(amount: int, item: str = "여행 예약") -> str:
    """더미 결제를 처리하고 예약 확정번호를 발급한다. amount는 총 결제 금액."""
    confirmation = ts.make_confirmation()
    return f"결제 완료 · {item} · {amount:,}원 · 확정번호 {confirmation}"
