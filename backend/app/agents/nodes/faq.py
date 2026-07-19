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
    "너는 여행 서비스 FAQ 상담원이야. 아래 '관련 FAQ'를 근거로 사용자 질문에 정확히 답해. "
    "FAQ에 없는 내용은 지어내지 말고 '해당 내용은 확인이 어려워요'라고 안내해. 간결한 한국어로."
)


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
    logger.info("faq: '%s' → FAQ %d개", query[:30], len(results))

    if not results:
        return Command(
            update={"messages": [AIMessage(content="관련 FAQ를 찾지 못했어요.", name="faq")]},
            goto=END,
        )

    context = "\n\n".join(f"Q: {f['question']}\nA: {f['answer']}" for f in results)

    if not get_settings().llm_enabled:
        # 폴백: 가장 관련 있는 FAQ 답변 그대로
        return Command(
            update={"messages": [AIMessage(content=results[0]["answer"], name="faq")]},
            goto=END,
        )

    llm = get_llm("standard")
    response = llm.invoke(
        [
            {"role": "system", "content": FAQ_SYSTEM},
            {"role": "user", "content": f"관련 FAQ:\n{context}\n\n질문: {query}"},
        ]
    )
    return Command(
        update={"messages": [AIMessage(content=response.content, name="faq")]},
        goto=END,
    )
