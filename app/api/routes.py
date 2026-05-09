from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.models import PackageResult
from app.pipeline.processor import MortgagePackageProcessor
from app.services.ingestion import PdfIngestionService, pages_from_text_snippets

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


@router.post("/packages/process-pdf", response_model=PackageResult)
async def process_pdf_package(
    file: Annotated[UploadFile, File(description="Raw mortgage package PDF bundle.")],
    package_id: Annotated[str | None, Form()] = None,
) -> PackageResult:
    """Upload and process a mortgage PDF package.

    The API ignores the file name for classification, extracts every page independently, uses native
    text when available, falls back to local OCR for scanned pages, and returns partial output with
    exceptions when page-level extraction fails.
    """

    filename = file.filename or "uploaded.pdf"
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded PDF is empty.",
        )
    if not pdf_bytes.lstrip().startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload content must be a PDF file.",
        )

    try:
        ingestion_result = PdfIngestionService().ingest(pdf_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file could not be opened as a PDF: {exc}",
        ) from exc
    finally:
        await file.close()

    result = MortgagePackageProcessor().process_pages(
        package_id or filename, ingestion_result.pages
    )
    result.exceptions = [*ingestion_result.exceptions, *result.exceptions]
    return result
