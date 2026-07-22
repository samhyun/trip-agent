"""rag_service 시맨틱 응답 캐시 유닛 테스트 (임베딩 없이 벡터 직접 주입)."""

import math

import pytest

from app.services import rag_service


@pytest.fixture(autouse=True)
def _clear_cache():
    rag_service.cache_clear()
    yield
    rag_service.cache_clear()


class TestCosine:
    def test_identical(self):
        assert rag_service._cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal(self):
        assert rag_service._cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_safe(self):
        assert rag_service._cosine([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_dimension_mismatch_is_zero(self):
        # 차원이 다르면(모델 변경·손상) 0 → 미스 처리
        assert rag_service._cosine([1.0, 0.0, 0.0], [1.0, 0.0]) == 0.0


class TestAnswerCache:
    def test_hit_above_threshold(self):
        emb = [1.0, 0.0, 0.0]
        rag_service.cache_store(emb, "환불은 3일 전 100%")
        # 거의 동일한 벡터(유사도 ~1.0) → 히트
        assert rag_service.cache_lookup([0.999, 0.001, 0.0]) == "환불은 3일 전 100%"

    def test_miss_below_threshold(self):
        rag_service.cache_store([1.0, 0.0, 0.0], "환불 답변")
        # 직교(유사도 0) → 임계 미달로 미스
        assert rag_service.cache_lookup([0.0, 1.0, 0.0]) is None

    def test_returns_most_similar(self):
        rag_service.cache_store([1.0, 0.0, 0.0], "A답변")
        rag_service.cache_store([0.0, 1.0, 0.0], "B답변")
        assert rag_service.cache_lookup([0.99, 0.14, 0.0]) == "A답변"

    def test_fifo_eviction(self, monkeypatch):
        monkeypatch.setattr(rag_service, "ANSWER_CACHE_MAX", 2)
        rag_service.cache_store([1.0, 0.0], "first")
        rag_service.cache_store([0.0, 1.0], "second")
        rag_service.cache_store([1.0, 1.0], "third")  # first 축출
        assert rag_service.cache_lookup([1.0, 0.0]) is None  # first 사라짐
        assert rag_service.cache_lookup([0.0, 1.0]) == "second"

    def test_threshold_boundary(self):
        # cosine([cosθ, sinθ], [1,0]) = cosθ 로 임계(0.95) 경계를 정확히 만든다
        rag_service.cache_store([1.0, 0.0], "answer")
        hit = [0.95, math.sqrt(1 - 0.95**2)]  # cosine = 0.95 (>= 임계) → 히트
        assert rag_service.cache_lookup(hit) == "answer"
        miss = [0.94, math.sqrt(1 - 0.94**2)]  # cosine = 0.94 (< 임계) → 미스
        assert rag_service.cache_lookup(miss) is None

    def test_dimension_mismatch_lookup_is_miss(self):
        rag_service.cache_store([1.0, 0.0, 0.0], "x")
        assert rag_service.cache_lookup([1.0, 0.0]) is None  # 차원 다르면 미스

    def test_store_skipped_on_stale_generation(self):
        # 재시드(cache_clear)가 저장 전에 끼어들면 오래된 세대의 답은 저장되지 않는다
        gen = rag_service.current_generation()
        rag_service.cache_clear()  # 세대 증가(재시드 시뮬레이션)
        rag_service.cache_store([1.0, 0.0], "stale", generation=gen)
        assert rag_service.cache_lookup([1.0, 0.0]) is None

    def test_store_with_current_generation(self):
        gen = rag_service.current_generation()
        rag_service.cache_store([1.0, 0.0], "fresh", generation=gen)
        assert rag_service.cache_lookup([1.0, 0.0]) == "fresh"

    def test_clear(self):
        rag_service.cache_store([1.0, 0.0], "x")
        rag_service.cache_clear()
        assert rag_service.cache_lookup([1.0, 0.0]) is None
