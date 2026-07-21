"""Coordinator 노드 (+ chat_reply).

coordinator는 사용자 의도를 구조화 출력으로 판단해 결정론적으로 라우팅한다:
- chat : 정보 부족/일반 대화 → chat_reply 노드가 답변을 **토큰 스트리밍**으로 생성(END)
- faq  : 서비스 이용·정책 질문 → faq 노드(RAG)
- plan : 정보 충분 → planner 로 handoff

라우팅 판단(구조화)과 답변 생성(스트리밍)을 분리해, 채팅 답변도 한 글자씩 흐르게 한다.
LLM이 없으면 mock, 구조화 출력이 실패하면 chat 으로 폴백한다.
"""

from datetime import date, datetime
from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command
from typing_extensions import TypedDict

from app.agents.llm import get_llm
from app.agents.prompts import render
from app.agents.state import State
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Intent(TypedDict):
    """coordinator의 의도 분류 + 여행 슬롯 추출 (답변 텍스트는 chat_reply가 생성)."""

    intent: Literal["chat", "faq", "plan", "recommend"]
    destination: str  # 주 목적지 도시/지역(한국어). 아직 안 정해졌으면 ""
    destination_en: str  # 주 목적지 영문 표기(항공·지도 조회용). 예: 랑카위→Langkawi. 없으면 ""
    destinations: list[str]  # 여러 도시를 방문하면 전체 목록(한국어). 단일이면 1개 또는 []
    destinations_en: list[str]  # destinations 대응 영문명(같은 순서·길이)
    travelers: int  # 여행 인원 (모르면 0)
    nights: int  # 숙박 박수 (모르면 0)
    start_date: str  # 여행 시작일 YYYY-MM-DD (사용자가 날짜를 말했을 때만, 아니면 "")
    sort: Literal["price", "rating", ""]  # 정렬 선호: price(더 싼·가성비) | rating(평점·고급) | ""
    focus: Literal["flight", "hotel", ""]  # 이번 요청이 항공만/숙소만 관한 것이면 표시, 둘 다·불명확이면 ""


MOCK_REPLY = "여행 계획을 도와드릴게요! 🧳 (지금은 mock 모드예요) 어디로, 며칠 동안, 몇 분이서 떠나세요?"


def _valid_date(value: str) -> bool:
    """YYYY-MM-DD 형식의 오늘 이후 날짜인지 검증. 과거·오형식이면 무시(기본 날짜 사용)."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() >= date.today()
    except (TypeError, ValueError):
        return False


def coordinator_node(state: State) -> Command:
    """의도 판단 + 슬롯 추출. chat→chat_reply, faq→faq, plan→planner."""
    settings = get_settings()

    if not settings.llm_enabled:
        logger.info("coordinator: LLM 미설정 → mock")
        return Command(update={"messages": [AIMessage(content=MOCK_REPLY, name="coordinator")]}, goto=END)

    trip: dict = {}
    try:
        # 프롬프트의 <<CURRENT_TIME>> 이 오늘 날짜로 치환돼 "8월 14일" 같은 상대 표현을 미래 날짜로 변환하게 한다
        result = get_llm("coordinator").with_structured_output(Intent).invoke(
            [{"role": "system", "content": render("coordinator_router")}, *state["messages"]]
        )
        intent = result.get("intent", "chat")
        dest = (result.get("destination") or "").strip()
        if dest:
            trip["destination"] = dest
            en = (result.get("destination_en") or "").strip()
            prev_dest = (state.get("trip") or {}).get("destination", "").strip()
            # 유효한 영문명이거나 목적지가 바뀐 경우에만 갱신(기존 영문명 유실 방지)
            if en or dest != prev_dest:
                trip["destination_en"] = en
        # 멀티 목적지(2곳 이상)면 목록 저장 → route 워커가 동선 A/B안 생성
        dests = [d.strip() for d in (result.get("destinations") or []) if isinstance(d, str) and d.strip()]
        if len(dests) >= 2:
            trip["destinations"] = dests
            trip["destinations_en"] = [
                (e or "").strip() for e in (result.get("destinations_en") or [])[: len(dests)]
            ]
        elif dest:  # 단일 도시로 확정(dests가 0~1개) → 이전 멀티 목록 제거(잘못된 route 방지)
            trip["destinations"] = []
            trip["destinations_en"] = []
        if result.get("travelers"):
            trip["travelers"] = result["travelers"]
        if result.get("nights"):
            trip["nights"] = result["nights"]
        start_date = (result.get("start_date") or "").strip()
        if _valid_date(start_date):  # 사용자가 말한 여행 시작일(항공 날짜에 사용)
            trip["start_date"] = start_date
        sort = (result.get("sort") or "").strip()
        trip["sort"] = sort if sort in ("price", "rating") else ""  # 예상 밖 값 방어
        focus = (result.get("focus") or "").strip()
        trip["focus"] = focus if focus in ("flight", "hotel") else ""
    except Exception as exc:  # 구조화 미지원 등 → 대화 유지
        logger.warning("coordinator: 구조화 출력 실패 → chat 폴백 (%s)", exc)
        intent = "chat"

    merged_trip = {**(state.get("trip") or {}), **trip}
    logger.info("coordinator: intent=%s destination=%r", intent, merged_trip.get("destination"))

    if intent == "plan":
        # 선행 조회: 목적지를 알아낸 '지금' 명소 조회를 백그라운드로 시작 —
        # planner·워커 LLM이 도는 동안 API가 겹쳐 돌아 뒤 단계 대기가 줄어든다(실패해도 본전).
        from app.services import travel_service as ts  # 지연 임포트(노드→서비스 결합 최소화)

        targets = list(merged_trip.get("destinations") or []) or [merged_trip.get("destination", "")]
        ts.prefetch_attractions([t for t in targets if t])

    if intent == "faq":
        return Command(update={"trip": merged_trip}, goto="faq")
    if intent == "recommend":  # 목적지 미정 + 조건 있음 → 후보 여행지 카드
        return Command(update={"trip": merged_trip}, goto="recommend")
    if intent == "plan":
        # 고정 멘트("계획을 세워볼게요")를 매번 붙이지 않는다 — 각 워커가 맥락에 맞는 응답을 낸다
        return Command(update={"trip": merged_trip}, goto="planner")
    # chat: 답변은 chat_reply 가 토큰 스트리밍으로 생성
    return Command(update={"trip": merged_trip}, goto="chat_reply")


def chat_reply_node(state: State) -> Command:
    """일반 대화/되묻기 답변을 생성(토큰 스트리밍 대상). END로 종료."""
    if not get_settings().llm_enabled:
        return Command(update={"messages": [AIMessage(content=MOCK_REPLY, name="chat_reply")]}, goto=END)
    response = get_llm("coordinator").invoke(
        [{"role": "system", "content": render("coordinator_chat")}, *state["messages"]]
    )
    content = (response.content or "").strip() or "조금 더 알려주세요. (목적지·기간·인원)"
    return Command(update={"messages": [AIMessage(content=content, name="chat_reply")]}, goto=END)
