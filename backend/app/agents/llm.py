"""LLM 팩토리 (역할별 티어).

에이전트 역할(`AGENT_LLM_MAP`) → 티어(reasoning/standard/fast) → (base_url, api_key, model).
티어별 전용 엔드포인트가 있으면 그것을, 없으면 공용(llm_*), 그것도 없으면 OpenAI 직접으로 폴백.
모두 OpenAI 호환이라 `ChatOpenAI` 하나로 처리한다.

주의: temperature는 지정하지 않는다(모델 기본값 사용). GPT-5·o 계열 등 일부 모델은
temperature 커스텀을 막고 default만 허용하므로, 호환성을 위해 넘기지 않는다.
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import AGENT_LLM_MAP, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _build(model: str, base_url: str, api_key: str) -> ChatOpenAI:
    """(model, base_url, key) 조합별로 캐시된 ChatOpenAI 생성."""
    kwargs: dict = {"model": model, "api_key": api_key or "sk-missing"}
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def get_llm(role: str = "coordinator") -> ChatOpenAI:
    """역할에 맞는 LLM을 반환한다 (티어별 엔드포인트/모델)."""
    settings = get_settings()
    tier = AGENT_LLM_MAP.get(role, "standard")
    base_url, api_key, model = settings.resolve_tier(tier)

    if base_url and api_key:
        logger.debug("get_llm[%s] → %s (%s)", role, tier, model)
        return _build(model, base_url, api_key)

    # 최종 폴백: OpenAI 직접
    logger.debug("get_llm[%s] → openai (%s)", role, settings.openai_model)
    return _build(settings.openai_model, "", settings.openai_api_key)
