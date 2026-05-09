from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PageSource(StrEnum):
    NATIVE_DIGITAL = "native_digital"
    SCANNED_IMAGE = "scanned_image"


class DocumentType(StrEnum):
    UNKNOWN = "unknown"
    LOAN_APPLICATION_1003 = "loan_application_1003"
    INITIAL_LOAN_APPLICATION_1003 = "initial_loan_application_1003"
    FINAL_LOAN_APPLICATION_1003 = "final_loan_application_1003"
    BANK_STATEMENT = "bank_statement"
    TAX_RETURN_1040 = "tax_return_1040"
    W2 = "w2"
    PAYSTUB = "paystub"
    CREDIT_REPORT = "credit_report"
    CLOSING_DISCLOSURE = "closing_disclosure"


class ClassificationMethod(StrEnum):
    RULE = "rule"
    SKLEARN = "sklearn"
    LLM = "llm"
    UNCLASSIFIED = "unclassified"


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class TextBlock(BaseModel):
    text: str
    bbox: BoundingBox | None = None


class Page(BaseModel):
    page_number: int = Field(..., ge=1)
    source: PageSource
    text: str = ""
    text_blocks: list[TextBlock] = Field(default_factory=list)
    phash: str | None = None
    quality_score: float = 0.0


class Classification(BaseModel):
    page_number: int
    doc_type: DocumentType = DocumentType.UNKNOWN
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    method: ClassificationMethod = ClassificationMethod.UNCLASSIFIED
    key_fields_found: list[str] = Field(default_factory=list)


class DuplicateGroup(BaseModel):
    canonical_page: int
    duplicate_pages: list[int]
    reason: str


class Document(BaseModel):
    type: DocumentType
    pages: list[int]
    signed: bool | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    period: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExceptionItem(BaseModel):
    type: str
    doc: str | None = None
    detail: str
    pages: list[int] = Field(default_factory=list)


class PackageResult(BaseModel):
    package_id: str
    documents: list[Document]
    exceptions: list[ExceptionItem]
    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)
