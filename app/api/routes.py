from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models import PackageResult
from app.pipeline.processor import MortgagePackageProcessor
from app.services.ingestion import pages_from_text_snippets

router = APIRouter()


class TextPackageRequest(BaseModel):
    package_id: str = Field(..., examples=["PKG-20240509-001"])
    pages: list[str] = Field(..., min_length=1)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/packages/process-text", response_model=PackageResult)
def process_text_package(payload: TextPackageRequest) -> PackageResult:
    """Process text snippets through the same post-ingestion pipeline used for PDFs."""

    pages = pages_from_text_snippets(payload.pages)
    return MortgagePackageProcessor().process_pages(payload.package_id, pages)
