from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    """Runtime configuration for the document package processor."""

    app_name: str = "Mortgage Document Package Processor"
    max_llm_batch_size: int = 10
    llm_text_token_budget: int = 500
    duplicate_hamming_threshold: int = 5
    minimum_auto_classification_confidence: float = 0.82


@lru_cache
def get_settings() -> Settings:
    return Settings()
