"""planner.py 결제 게이트(_wants_payment) 유닛 테스트."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.nodes import planner


class TestWantsPayment:
    def test_keyword_present(self):
        assert planner._wants_payment([HumanMessage(content="이걸로 결제할게")]) is True

    def test_keyword_absent(self):
        assert planner._wants_payment([HumanMessage(content="숙소 더 보여줘")]) is False

    def test_uses_latest_human_message(self):
        # 최신 사용자 발화 기준 — 과거에 '결제'가 있어도 최신이 아니면 False
        msgs = [
            HumanMessage(content="결제할게"),
            AIMessage(content="확정할까요?"),
            HumanMessage(content="아니 숙소 더 볼래"),
        ]
        assert planner._wants_payment(msgs) is False

    def test_no_human_message(self):
        assert planner._wants_payment([AIMessage(content="결제 안내")]) is False

    @pytest.mark.parametrize("keyword", ["결제", "구매", "예약 확정", "결제까지", "카드로"])
    def test_all_pay_keywords(self, keyword):
        assert planner._wants_payment([HumanMessage(content=f"{keyword} 진행해줘")]) is True
