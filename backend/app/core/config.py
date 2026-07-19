"""애플리케이션 환경설정.

`.env` 파일과 환경변수에서 값을 읽어 `Settings` 객체로 제공한다.

LLM은 역할별 티어(reasoning / standard / fast)로 나뉜다. 각 티어는 자체
base_url·api_key·model 을 가질 수 있고(elice 모델별 전용 엔드포인트 대응),
비어 있으면 공용(`llm_base_url`/`llm_api_key`)으로 폴백한다. 공용도 없으면
OpenAI 직접(`openai_*`)으로 폴백한다.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 기반 설정. 프로젝트 루트의 `.env`를 로드한다."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ----- LLM: OpenAI 직접 (최종 폴백/로컬 테스트) -----
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # ----- LLM: elice AI Cloud (OpenAI 호환) -----
    # 공용 엔드포인트 (티어별 값이 비면 여기로 폴백)
    llm_base_url: str = ""
    llm_api_key: str = ""

    # 티어별 엔드포인트·키·모델 (모델마다 전용 엔드포인트가 다를 수 있어 분리)
    reasoning_base_url: str = ""
    reasoning_api_key: str = ""
    reasoning_model: str = ""

    standard_base_url: str = ""
    standard_api_key: str = ""
    standard_model: str = ""

    fast_base_url: str = ""
    fast_api_key: str = ""
    fast_model: str = ""

    # ----- 임베딩 (RAG 검색용, OpenAI 호환) -----
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"

    # ----- 데이터베이스 (Postgres + pgvector) -----
    # 로컬 개발: 프로젝트 docker-compose의 pgvector (호스트 5433).
    # docker-compose 내부에서는 environment의 DATABASE_URL(db:5432)이 우선한다.
    database_url: str = "postgresql+psycopg://tripagent:tripagent@localhost:5433/tripagent"

    # ----- 여행 데이터 API (선택) -----
    tour_api_key: str = ""
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_base_url: str = "https://test.api.amadeus.com"
    openweather_api_key: str = ""

    # ----- 앱 설정 -----
    use_mock_only: bool = False
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        """콤마 구분 문자열을 오리진 리스트로 변환."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolve_tier(self, tier: str) -> tuple[str, str, str]:
        """티어 이름 → (base_url, api_key, model).

        티어별 값이 비면 공용(llm_*)으로, model이 비면 openai_model로 폴백한다.
        """
        base_url = getattr(self, f"{tier}_base_url", "") or self.llm_base_url
        api_key = getattr(self, f"{tier}_api_key", "") or self.llm_api_key
        model = getattr(self, f"{tier}_model", "") or self.openai_model
        return base_url, api_key, model

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_elice(self) -> bool:
        """공용 또는 어느 티어든 base_url+api_key가 잡혀 있으면 True."""
        if self.llm_base_url and self.llm_api_key:
            return True
        for tier in ("reasoning", "standard", "fast"):
            base_url, api_key, _ = self.resolve_tier(tier)
            if base_url and api_key:
                return True
        return False

    @property
    def has_llm(self) -> bool:
        """LLM 사용 가능 여부 (elice/호환 엔드포인트 또는 OpenAI)."""
        return self.has_elice or self.has_openai

    @property
    def llm_enabled(self) -> bool:
        """실제 LLM 호출 여부 (mock 전용 모드가 아니고 LLM이 설정됐을 때)."""
        return self.has_llm and not self.use_mock_only

    @property
    def has_tour_api(self) -> bool:
        return bool(self.tour_api_key)

    @property
    def has_amadeus(self) -> bool:
        return bool(self.amadeus_client_id and self.amadeus_client_secret)

    def embedding_config(self) -> tuple[str, str, str]:
        """RAG 임베딩 (base_url, api_key, model)."""
        return self.embedding_base_url, self.embedding_api_key, self.embedding_model

    @property
    def has_embedding(self) -> bool:
        """임베딩 엔드포인트가 설정됐는지 (RAG 사용 가능 여부)."""
        return bool(self.embedding_base_url and self.embedding_api_key)


@lru_cache
def get_settings() -> Settings:
    """설정 싱글턴. 앱 전역에서 재사용한다."""
    return Settings()


# 에이전트 역할 → 모델 티어 매핑.
AGENT_LLM_MAP: dict[str, str] = {
    "coordinator": "standard",
    "planner": "reasoning",
    "supervisor": "fast",
    "destination": "standard",
    "itinerary": "reasoning",
    "booking": "standard",
    "payment": "fast",
}
