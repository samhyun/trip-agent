"""목적지 추천 노드.

사용자가 뚜렷한 목적지 없이 예산·시기·날씨·취향 등 조건을 말하면, 어울리는 여행지 후보를
카드(destination_reco)로 추천한다. 후보를 고르면 일반 계획 흐름(자동해석 포함)으로 이어진다.

구조화 출력은 elice에서 지연이 커, 파이프(|) 구분 평문으로 받아 파싱한다.
"""

from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command

from app.agents.llm import get_llm
from app.agents.prompts import render
from app.agents.state import State
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# LLM 미설정 시 안내
_NO_LLM_MSG = (
    "어디로 갈지 아직 안 정하셨군요! 예산·시기·분위기(예: \"7월에 100만원으로 따뜻한 해외\")를 "
    "알려주시면 어울리는 여행지를 추천해 드릴게요."
)


def _parse_reco(text: str) -> list[dict]:
    """파이프 구분 평문 → 후보 목록. 필드 6개 미만 줄은 건너뜀."""
    items: list[dict] = []
    for line in (text or "").splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 6 and parts[0] and not parts[0].startswith(("도시", "-", "#")):
            items.append(
                {
                    "city": parts[0],
                    "cityEn": parts[1],
                    "reason": parts[2],
                    "budget": parts[3],
                    "weather": parts[4],
                    "highlight": parts[5],
                }
            )
        if len(items) >= 4:
            break
    return items


def recommend_node(state: State) -> Command:
    """조건에 맞는 여행지 후보를 카드로 추천 (목적지 미정 시). END로 종료."""
    if not get_settings().llm_enabled:
        return Command(update={"messages": [AIMessage(content=_NO_LLM_MSG, name="recommend")]}, goto=END)

    response = get_llm("recommend").invoke(
        [{"role": "system", "content": render("recommend")}, *state["messages"]]
    )
    items = _parse_reco(response.content or "")
    if not items:  # 파싱 실패 → 원문 텍스트라도 전달(빈손 방지)
        fallback = (response.content or "").strip() or _NO_LLM_MSG
        return Command(update={"messages": [AIMessage(content=fallback, name="recommend")]}, goto=END)

    # 후보 도시명을 본문에도 담는다 → 히스토리에 남아 다음 턴에 "두 번째로 해줘" 같은 지칭이 가능
    cities = ", ".join(i["city"] for i in items)
    content = f"정한 곳이 없으시군요! 조건에 맞는 여행지를 골라봤어요: {cities}. 마음에 드는 곳으로 계획을 시작해 보세요."
    msg = AIMessage(
        content=content,
        name="recommend",
        additional_kwargs={"card_type": "destination_reco", "payload": {"candidates": items}},
    )
    logger.info("recommend: 후보 %d곳 (%s)", len(items), ", ".join(i["city"] for i in items))
    return Command(update={"messages": [msg]}, goto=END)
