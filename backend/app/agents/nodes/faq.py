"""FAQ 노드 (RAG).

사용자 질문에 대해 FAQ를 검색(`rag_service`)해 그 결과를 근거로 답변한다.
LLM이 없으면 가장 관련 있는 FAQ 답변을 그대로 돌려주는 폴백을 쓴다.
"""

from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command

from app.agents.llm import get_llm
from app.agents.prompts import render
from app.agents.state import State
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import rag_service

logger = get_logger(__name__)

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


def _reply(answer: str) -> Command:
    return Command(update={"messages": [AIMessage(content=answer, name="faq")]}, goto=END)


def faq_node(state: State) -> Command:
    """FAQ를 검색해 근거로 삼아 답변한다. 의미가 비슷한 반복 질문은 시맨틱 캐시로 재사용한다."""
    query = _last_user_text(state["messages"])
    settings = get_settings()

    # 시맨틱 캐시: 비슷한 질문에 이전 답변 재사용 → 검색·LLM 생성 스킵 (캐시는 best-effort)
    q_emb = None
    if settings.has_embedding:
        try:
            q_emb = rag_service.embed_query(query)
            cached = rag_service.cache_lookup(q_emb)
            if cached is not None:
                logger.info("faq: 시맨틱 캐시 히트 → '%s'", query[:30])
                return _reply(cached)
        except Exception as exc:  # noqa: BLE001 - 캐시 실패해도 정상 경로로 진행
            logger.warning("faq 시맨틱 캐시 스킵: %s", exc)
            q_emb = None

    gen = rag_service.current_generation()  # search가 볼 FAQ 세대 (저장 때 대조 → 재시드 경합 방지)
    results = rag_service.search_faq(query, top_k=3)
    logger.info("faq: '%s' → 관련 FAQ %d개", query[:30], len(results))

    # 임계값 통과 FAQ가 없음(무관 질문) → 근거 없이 지어내지 않고 안내만
    # 부정 결과는 캐시하지 않는다(임계 근처 질문이 나중에 FAQ에 걸릴 수 있어 검색을 막지 않음)
    if not results:
        return _reply(_NO_FAQ_MSG)

    context = "\n\n".join(f"Q: {f['question']}\nA: {f['answer']}" for f in results)

    if not settings.llm_enabled:
        # 폴백: 가장 관련 있는 FAQ 답변만 사용 → 그 1건만 출처 표기 (LLM 미설정이라 캐시 안 함)
        return _reply(results[0]["answer"] + _citation(results[:1]))

    response = get_llm("standard").invoke(
        [
            {"role": "system", "content": render("faq")},
            {"role": "user", "content": f"관련 FAQ:\n{context}\n\n질문: {query}"},
        ]
    )
    # LLM 빈 응답이면 최상위 FAQ 답변으로 폴백(출처만 남지 않게). 근거로 준 FAQ 전체를 출처 표기.
    content = (response.content or "").strip() or results[0]["answer"]
    answer = content + _citation(results)
    if q_emb is not None:
        try:
            rag_service.cache_store(q_emb, answer, gen)
        except Exception as exc:  # noqa: BLE001 - 저장 실패해도 답변은 반환(best-effort)
            logger.warning("faq 시맨틱 캐시 저장 스킵: %s", exc)
    return _reply(answer)
