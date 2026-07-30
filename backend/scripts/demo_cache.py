"""FAQ 시맨틱 캐시가 언제 히트하고 언제 미스인지 확인한다.

캐시는 프로세스 메모리라 같은 실행 안에서 연달아 물어야 한다.
어미만 바꾸면 히트하고, 문장을 줄이면 임계(0.95)를 넘지 못해 다시 검색한다.

    uv run python scripts/demo_cache.py
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
for noisy in ("httpx", "httpcore", "openai"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from langchain_core.messages import HumanMessage  # noqa: E402

from app.agents.nodes.faq import faq_node  # noqa: E402


def ask(text: str) -> None:
    print(f"\n$ 사용자: {text}")
    faq_node({"messages": [HumanMessage(content=text)], "trip": {}})


ask("예약 취소하면 환불 수수료는 어떻게 돼?")
ask("예약 취소하면 환불 수수료는 어떻게 되나요?")
ask("환불 수수료 어떻게 돼?")
