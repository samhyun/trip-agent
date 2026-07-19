"""FAQ 노드 (RAG).

사용자 질문에 대해 FAQ를 검색(`rag_service`)해 그 결과를 근거로 답변한다.
LLM이 없으면 가장 관련 있는 FAQ 답변을 그대로 돌려주는 폴백을 쓴다.
"""

from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command

from app.agents.llm import get_llm
from app.agents.state import State
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import rag_service

logger = get_logger(__name__)

FAQ_SYSTEM = (
    "너는 여행 서비스 'Trip Agent'의 FAQ 상담원이야. 아래 '관련 FAQ'에 담긴 내용만 근거로 답해. "
    "FAQ에 없는 내용은 절대 지어내지 말고 '해당 내용은 확인이 어려워요'라고 안내해. "
    "수수료·환불률·수하물·체크인 시간 같은 정책성 답변은 데모 기준이며, 실제 예약 상품·항공사·숙소 규정이 "
    "우선함을 필요할 때 한 줄로 덧붙여. 읽기 좋게 간결한 한국어 마크다운으로 답해."
)

# 관련 FAQ가 없을 때 안내 (근거 없이 LLM에 지어내게 하지 않는다)
_NO_FAQ_MSG = (
    "그 질문은 제가 아는 FAQ에서 정확한 답을 찾지 못했어요. 🙏\n\n"
    "**취소·환불 / 결제 / 예약변경 / 항공 / 숙소 / 준비물 / 예약확인** 관련이면 다시 여쭤봐 주세요."
)


def _citation(results: list[dict]) -> str:
    """답변에 붙일 근거 FAQ 출처 표기 (실제 근거로 쓴 FAQ만 전달할 것)."""
    if not results:
        return ""
    refs = " · ".join(f"[{f.get('category', 'FAQ')}] {f['question']}" for f in results)
    return f"\n\n---\n📎 참고 FAQ: {refs}"


def _last_user_text(messages) -> str:
    """대화에서 마지막 사용자 발화 텍스트를 찾는다."""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            return msg.content
        if isinstance(msg, dict) and msg.get("role") == "user":
            return msg.get("content", "")
    last = messages[-1] if messages else None
    return getattr(last, "content", "") if last else ""


def faq_node(state: State) -> Command:
    """FAQ를 검색해 근거로 삼아 답변한다."""
    query = _last_user_text(state["messages"])
    results = rag_service.search_faq(query, top_k=3)
    logger.info("faq: '%s' → 관련 FAQ %d개", query[:30], len(results))

    # 임계값 통과 FAQ가 없음(무관 질문) → 근거 없이 지어내지 않고 안내만
    if not results:
        return Command(
            update={"messages": [AIMessage(content=_NO_FAQ_MSG, name="faq")]},
            goto=END,
        )

    context = "\n\n".join(f"Q: {f['question']}\nA: {f['answer']}" for f in results)

    if not get_settings().llm_enabled:
        # 폴백: 가장 관련 있는 FAQ 답변만 사용 → 그 1건만 출처 표기
        answer = results[0]["answer"] + _citation(results[:1])
        return Command(update={"messages": [AIMessage(content=answer, name="faq")]}, goto=END)

    response = get_llm("standard").invoke(
        [
            {"role": "system", "content": FAQ_SYSTEM},
            {"role": "user", "content": f"관련 FAQ:\n{context}\n\n질문: {query}"},
        ]
    )
    # LLM 빈 응답이면 최상위 FAQ 답변으로 폴백(출처만 남지 않게). 근거로 준 FAQ 전체를 출처 표기.
    content = (response.content or "").strip() or results[0]["answer"]
    answer = content + _citation(results)
    return Command(update={"messages": [AIMessage(content=answer, name="faq")]}, goto=END)
