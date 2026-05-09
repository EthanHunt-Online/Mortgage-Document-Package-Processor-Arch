"""Low-cost page classification rules.

The production architecture can add a scikit-learn classifier and an LLM fallback
behind this interface. The initial implementation intentionally uses deterministic
rules so tests run quickly and without network access.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mortgage_processor.models import PageInput


@dataclass(frozen=True)
class Classification:
    """Classification result for a single page."""

    doc_type: str | None
    confidence: float
    key_fields_found: list[str]


_RULES: tuple[tuple[str, str, float, tuple[str, ...]], ...] = (
    (
        "final_loan_application_1003",
        r"\b(form\s*1003|uniform residential loan application|urla)\b",
        0.95,
        ("Form 1003", "Uniform Residential Loan Application"),
    ),
    (
        "bank_statement",
        r"\b(bank statement|account summary|statement period|ending balance)\b",
        0.9,
        ("Bank Statement", "Statement Period"),
    ),
    (
        "tax_return_1040",
        r"\b(form\s*1040|u\.s\. individual income tax return|adjusted gross income)\b",
        0.9,
        ("Form 1040", "Adjusted Gross Income"),
    ),
    (
        "w2",
        r"\b(form\s*w-?2|wage and tax statement|employer identification number)\b",
        0.9,
        ("W-2", "Employer Identification Number"),
    ),
)


def classify_page(page: PageInput) -> Classification:
    """Classify a page using deterministic rules before any LLM fallback."""

    normalized = page.text.lower()
    for doc_type, pattern, confidence, fields in _RULES:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            found = [field for field in fields if field.lower() in normalized]
            return Classification(doc_type, confidence, found or list(fields[:1]))

    return Classification(None, 0.0, [])
