"""Orchestration for package classification, grouping, and validation."""

from __future__ import annotations

import re
from collections import defaultdict

from mortgage_processor.classification import classify_page
from mortgage_processor.duplicates import detect_duplicates
from mortgage_processor.models import (
    DocumentResult,
    ExceptionResult,
    PackageRequest,
    PackageResult,
    PageInput,
)

PAGE_COUNTER_RE = re.compile(r"\bpage\s+(?P<current>\d+)\s+of\s+(?P<total>\d+)\b", re.IGNORECASE)
PERIOD_RE = re.compile(
    r"\b(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(?P<year>20\d{2})\b",
    re.IGNORECASE,
)

MONTHS = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}

REQUIRED_DOC_TYPES = {"final_loan_application_1003"}
SIGNATURE_REQUIRED_DOC_TYPES = {"final_loan_application_1003"}
SIGNATURE_TERMS = ("signature", "signed", "borrower signature", "applicant signature")


def process_package(request: PackageRequest) -> PackageResult:
    """Process normalized pages into the expected package output contract."""

    exceptions = detect_duplicates(request.pages)
    classified_pages: dict[str, list[tuple[PageInput, float]]] = defaultdict(list)

    for page in request.pages:
        classification = classify_page(page)
        if classification.doc_type is None:
            exceptions.append(
                ExceptionResult(
                    type="unclassified_page",
                    pages=[page.page_number],
                    detail="Page could not be classified by deterministic rules and should be routed to ML/LLM fallback.",
                )
            )
            continue

        if classification.confidence < 0.8:
            exceptions.append(
                ExceptionResult(
                    type="low_confidence_classification",
                    doc=classification.doc_type,
                    pages=[page.page_number],
                    detail=f"Classification confidence {classification.confidence:.2f} is below review threshold.",
                )
            )

        classified_pages[classification.doc_type].append((page, classification.confidence))

    documents = [
        _build_document(doc_type, page_pairs, exceptions)
        for doc_type, page_pairs in sorted(classified_pages.items())
    ]

    present_doc_types = {document.type for document in documents}
    for required_doc_type in sorted(REQUIRED_DOC_TYPES - present_doc_types):
        exceptions.append(
            ExceptionResult(
                type="missing_required_document",
                doc=required_doc_type,
                detail=f"Required document type {required_doc_type} was not found.",
            )
        )

    for document in documents:
        if document.type in SIGNATURE_REQUIRED_DOC_TYPES and not document.signed:
            exceptions.append(
                ExceptionResult(
                    type="missing_signature",
                    doc=document.type,
                    pages=document.pages,
                    detail=f"Required signature was not detected for {document.type}.",
                )
            )

    return PackageResult(
        package_id=request.package_id,
        documents=documents,
        exceptions=exceptions,
    )


def _build_document(
    doc_type: str,
    page_pairs: list[tuple[PageInput, float]],
    exceptions: list[ExceptionResult],
) -> DocumentResult:
    ordered_pages = _order_pages([page for page, _confidence in page_pairs])
    page_numbers = [page.page_number for page in ordered_pages]
    confidence = sum(confidence for _page, confidence in page_pairs) / len(page_pairs)
    signed = any(_has_signature_signal(page.text) for page in ordered_pages)
    period = _extract_period(ordered_pages) if doc_type == "bank_statement" else None

    _append_missing_page_exceptions(doc_type, ordered_pages, exceptions)

    return DocumentResult(
        type=doc_type,
        pages=page_numbers,
        signed=signed,
        confidence=round(confidence, 2),
        period=period,
    )


def _order_pages(pages: list[PageInput]) -> list[PageInput]:
    def sort_key(page: PageInput) -> tuple[int, int]:
        counter = PAGE_COUNTER_RE.search(page.text)
        if counter:
            return (0, int(counter.group("current")))
        return (1, page.page_number)

    return sorted(pages, key=sort_key)


def _append_missing_page_exceptions(
    doc_type: str,
    pages: list[PageInput],
    exceptions: list[ExceptionResult],
) -> None:
    counters = [PAGE_COUNTER_RE.search(page.text) for page in pages]
    parsed = [(int(match.group("current")), int(match.group("total"))) for match in counters if match]
    if not parsed:
        return

    expected_total = max(total for _current, total in parsed)
    observed = {current for current, _total in parsed}
    for missing_page in sorted(set(range(1, expected_total + 1)) - observed):
        exceptions.append(
            ExceptionResult(
                type="missing_page",
                doc=doc_type,
                detail=f"Page {missing_page} of {expected_total} not found.",
            )
        )


def _has_signature_signal(text: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in SIGNATURE_TERMS)


def _extract_period(pages: list[PageInput]) -> str | None:
    for page in pages:
        match = PERIOD_RE.search(page.text)
        if match:
            month = MONTHS[match.group("month").lower()]
            return f"{match.group('year')}-{month}"
    return None
