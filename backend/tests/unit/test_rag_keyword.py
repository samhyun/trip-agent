"""rag_service.py 키워드 폴백 게이트(_keyword_search) 유닛 테스트.

임베딩 미설정 시 폴백 경로. FAQ 데이터를 고정 세트로 주입해 결정론적으로 검증한다.
"""

from app.services import rag_service

FAKE_FAQ = [
    {
        "id": "f1",
        "category": "환불",
        "question": "환불 어떻게 되나요",
        "answer": "출발 3일 전까지 100퍼센트 환불됩니다",
    },
    {
        "id": "f2",
        "category": "수하물",
        "question": "수하물 규정 알려주세요",
        "answer": "기내 반입은 10킬로까지 가능합니다",
    },
]


class TestKeywordSearch:
    def test_relevant_faq_passes_gate(self, monkeypatch):
        monkeypatch.setattr(rag_service, "load", lambda kind: FAKE_FAQ if kind == "faq" else {})
        hits = rag_service._keyword_search("환불 어떻게 되나요", top_k=3)
        assert any(h["id"] == "f1" for h in hits)
        # 통과한 결과에는 score가 붙는다
        for h in hits:
            assert "score" in h

    def test_unrelated_query_returns_empty(self, monkeypatch):
        # 질문 고유문자의 절반 이상 겹쳐야 관련으로 인정 → 무관 질문은 제외
        monkeypatch.setattr(rag_service, "load", lambda kind: FAKE_FAQ if kind == "faq" else {})
        assert rag_service._keyword_search("XYZ외계어질문블라블라", top_k=3) == []

    def test_respects_top_k(self, monkeypatch):
        monkeypatch.setattr(rag_service, "load", lambda kind: FAKE_FAQ if kind == "faq" else {})
        hits = rag_service._keyword_search("환불 수하물 규정 알려주세요", top_k=1)
        assert len(hits) <= 1
