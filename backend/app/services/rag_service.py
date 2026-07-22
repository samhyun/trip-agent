"""FAQ RAG 검색 (Postgres + pgvector).

FAQ를 임베딩해 pgvector 컬렉션에 저장하고, 질문과 유사도로 관련 FAQ를 찾는다.
임베딩 엔드포인트가 없으면(키 미설정) 간단한 키워드 겹침 검색으로 폴백한다(mock-first).

- `seed_faq()`   : FAQ를 pgvector에 (재)적재 (id 기준 upsert)
- `search_faq()` : 질문과 관련 있는 FAQ top_k 반환
"""

import math
import threading
from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.data_loader import load

logger = get_logger(__name__)

COLLECTION = "faq"

# 코사인 거리 임계값 — 이보다 멀면 '관련 없음'으로 보고 결과에서 제외한다.
# (진단: 관련 질문 0.3~0.4, 무관 질문 0.7+ → 0.55에서 명확히 갈림)
FAQ_MAX_DISTANCE = 0.55
# 키워드 폴백(임베딩 미설정 시) 최소 문자 겹침 수
KEYWORD_MIN_OVERLAP = 2


def _embeddings():
    """elice(OpenAI 호환) 임베딩 클라이언트."""
    from langchain_openai import OpenAIEmbeddings

    base_url, api_key, model = get_settings().embedding_config()
    return OpenAIEmbeddings(model=model, base_url=base_url or None, api_key=api_key or "sk-missing")


@lru_cache
def _store():
    """pgvector 벡터스토어 (프로세스당 1회 생성)."""
    from langchain_postgres import PGVector

    return PGVector(
        embeddings=_embeddings(),
        collection_name=COLLECTION,
        connection=get_settings().database_url,
        use_jsonb=True,
    )


def seed_faq() -> int:
    """FAQ를 pgvector에 (재)적재한다 (id 기준 upsert). 반환: 적재 건수."""
    from langchain_core.documents import Document

    faqs = load("faq")
    docs = [Document(page_content=f"{f['question']} {f['answer']}", metadata=f) for f in faqs]
    ids = [f["id"] for f in faqs]
    _store().add_documents(docs, ids=ids)
    cache_clear()  # 재시드 → 오래된 답변 캐시 무효화(바뀐 규정이 반영되도록)
    logger.info("rag: FAQ %d개 pgvector 적재", len(faqs))
    return len(faqs)


def _keyword_search(query: str, top_k: int) -> list[dict]:
    """임베딩 미설정 시 폴백: 한글 문자 겹침 기반 러프 검색(관련도 낮으면 제외)."""
    faqs = load("faq")
    q = set(query.replace(" ", ""))

    def score(faq: dict) -> int:
        text = (faq["question"] + faq["answer"]).replace(" ", "")
        return len(q & set(text))

    # 문자 교집합만으론 느슨하므로 질문 고유문자의 절반 이상 겹칠 때만 관련으로 간주
    min_overlap = max(KEYWORD_MIN_OVERLAP, len(q) // 2)
    ranked = sorted(faqs, key=lambda f: -score(f))
    return [{**f, "score": score(f)} for f in ranked[:top_k] if score(f) >= min_overlap]


# ----- 시맨틱 응답 캐시 -----
# 의미가 비슷한 반복 FAQ 질문("환불 수수료?" ≈ "환불 어떻게 돼?")에 이전 답변을 재사용해
# 검색·LLM 답변 생성을 건너뛴다. 잘못된 답 재사용을 막기 위해 임계값을 보수적으로(코사인 0.95) 둔다.
# 프로세스 메모리 캐시(재시작 시 소멸) — 데모 스코프. 영속·다중 워커면 pgvector로 확장.
# 같은 질문이 동시에 미스로 들어오면 각자 계산·저장한다(정합성 아닌 비용). 다중 워커면 캐시 독립.
# FAQ 데이터가 바뀌면 seed_faq()가 캐시를 비운다(오래된 답 재사용 방지).
ANSWER_CACHE_MAX = 128
ANSWER_CACHE_MIN_SIM = 0.95  # 코사인 유사도 이 이상이면 같은 질문으로 보고 이전 답변 재사용
_answer_cache: list[tuple[list[float], str]] = []  # (query_embedding, answer) FIFO
_answer_cache_lock = threading.Lock()
_cache_generation = 0  # 재시드 때마다 증가 — in-flight 요청이 오래된 답을 되쓰는 걸 막는다


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):  # 차원 불일치(모델 변경·손상 벡터) → 미스 처리(잘못된 히트 방지)
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def embed_query(text: str) -> list[float]:
    """질문 1건을 임베딩(시맨틱 캐시 조회·저장 키)."""
    return _embeddings().embed_query(text)


def cache_lookup(embedding: list[float]) -> str | None:
    """가장 유사한 캐시 항목이 임계 이상이면 그 답변을 반환, 아니면 None."""
    with _answer_cache_lock:
        best_ans, best_sim = None, 0.0
        for emb, ans in _answer_cache:
            sim = _cosine(embedding, emb)
            if sim > best_sim:
                best_sim, best_ans = sim, ans
        return best_ans if best_sim >= ANSWER_CACHE_MIN_SIM else None


def current_generation() -> int:
    """지금 캐시 세대. 요청 시작 시 캡처해 cache_store에 넘기면 재시드와의 경합을 막는다."""
    with _answer_cache_lock:
        return _cache_generation


def cache_store(embedding: list[float], answer: str, generation: int | None = None) -> None:
    """답변을 임베딩과 함께 캐시(초과분은 FIFO 축출).

    generation을 주면 그 사이 재시드(cache_clear)가 있었는지 확인해, 있었으면 저장하지 않는다.
    """
    with _answer_cache_lock:
        if generation is not None and generation != _cache_generation:
            return  # 저장 전 재시드가 끼어듦 → 오래된 답 저장 안 함
        _answer_cache.append((embedding, answer))
        if len(_answer_cache) > ANSWER_CACHE_MAX:
            _answer_cache.pop(0)


def cache_clear() -> None:
    """캐시 비우기(FAQ 재시드·테스트용). 세대를 올려 진행 중 요청의 stale 저장을 무효화한다."""
    global _cache_generation
    with _answer_cache_lock:
        _answer_cache.clear()
        _cache_generation += 1


def search_faq(query: str, top_k: int = 3, max_distance: float = FAQ_MAX_DISTANCE) -> list[dict]:
    """질문과 관련 있는 FAQ만 반환한다(유사도 임계값 게이트). 관련 없으면 빈 리스트."""
    if not get_settings().has_embedding:
        logger.info("rag: 임베딩 미설정 → 키워드 폴백 모드")
        return _keyword_search(query, top_k)

    results = _store().similarity_search_with_score(query, k=top_k)
    # 거리 임계값 초과(무관)는 제외 → 엉뚱한 FAQ 근거 답변 방지
    relevant = [
        {**doc.metadata, "score": round(float(dist), 3)}
        for doc, dist in results
        if float(dist) <= max_distance
    ]
    logger.info("rag: '%s' 검색 %d개 중 관련 %d개(임계 %.2f)", query[:20], len(results), len(relevant), max_distance)
    return relevant
