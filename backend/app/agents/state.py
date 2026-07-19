"""에이전트 그래프의 공유 상태와 팀 구성.

LangGraph `MessagesState`(대화 메시지 누적)를 확장한다.
- `next`: supervisor가 라우팅할 다음 노드 이름
- `trip`: 현재 여행 상태(목적지·날짜·인원·선택·합계) — 프론트 우측 "내 여행" 패널용
- `full_plan`: planner가 세운 실행 계획
- `visited`: 이번 실행에서 이미 거친 워커 목록 (supervisor 순회 추적)
"""

from typing import Literal

from langgraph.graph import MessagesState

# supervisor가 라우팅할 워커 팀
TEAM_MEMBERS = ["destination", "itinerary", "booking", "payment"]

# Router 결정 옵션 (워커 + 종료)
RouteOption = Literal["destination", "itinerary", "booking", "payment", "FINISH"]


class State(MessagesState):
    """대화 메시지 + 라우팅/여행 상태."""

    next: str
    trip: dict
    full_plan: str
    visited: list
    plan: list  # planner가 정한 실행 워커 순서 (선택적 라우팅)
