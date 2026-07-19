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
    """임베딩 미설정 시 폴백: 한글 문자 겹침 기반 러프 검색."""
    faqs = load("faq")

    def score(faq: dict) -> int:
        q = set(query.replace(" ", ""))
        text = (faq["question"] + faq["answer"]).replace(" ", "")
        return len(q & set(text))

    ranked = sorted(faqs, key=lambda f: -score(f))
    return [{**f, "score": score(f)} for f in ranked[:top_k]]


def search_faq(query: str, top_k: int = 3) -> list[dict]:
    """질문과 가장 관련 있는 FAQ top_k개를 반환한다."""
    if not get_settings().has_embedding:
        logger.info("rag: 임베딩 미설정 → 키워드 폴백 모드")
        return _keyword_search(query, top_k)

    results = _store().similarity_search_with_score(query, k=top_k)
    return [{**doc.metadata, "score": round(float(dist), 3)} for doc, dist in results]
