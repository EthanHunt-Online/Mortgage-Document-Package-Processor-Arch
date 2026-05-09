"""Data models for mortgage package processing.

The core pipeline uses standard-library dataclasses so deterministic tests can run
without external services or dependency installation. The FastAPI layer can still
serialize these objects as JSON-compatible response bodies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class PageInput:
    """A normalized page submitted to the processing pipeline."""

    page_number: int
    text: str = ""
    native_text: bool = True
    phash: str | None = None
    quality_score: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number must be greater than or equal to 1")
        if not 0.0 <= self.quality_score <= 1.0:
            raise ValueError("quality_score must be between 0.0 and 1.0")


@dataclass(slots=True)
class PackageRequest:
    """Request body for processing an already-normalized package."""

    package_id: str
    pages: list[PageInput]


@dataclass(slots=True)
class DocumentResult:
    """A grouped and ordered document extracted from a package."""

    type: str
    pages: list[int]
    confidence: float
    signed: bool = False
    period: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass(slots=True)
class ExceptionResult:
    """A non-crashing validation or processing exception."""

    type: Literal[
        "duplicate_page",
        "low_confidence_classification",
        "missing_page",
        "missing_required_document",
        "missing_signature",
        "unclassified_page",
    ]
    detail: str
    doc: str | None = None
    pages: list[int] = field(default_factory=list)


@dataclass(slots=True)
class PackageResult:
    """Final package output contract."""

    package_id: str
    documents: list[DocumentResult]
    exceptions: list[ExceptionResult]
