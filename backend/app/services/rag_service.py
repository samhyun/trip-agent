"""FAQ RAG 검색 (Postgres + pgvector).

FAQ를 임베딩해 pgvector 컬렉션에 저장하고, 질문과 유사도로 관련 FAQ를 찾는다.
임베딩 엔드포인트가 없으면(키 미설정) 간단한 키워드 겹침 검색으로 폴백한다(mock-first).

- `seed_faq()`   : FAQ를 pgvector에 (재)적재 (id 기준 upsert)
- `search_faq()` : 질문과 관련 있는 FAQ top_k 반환
"""

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
