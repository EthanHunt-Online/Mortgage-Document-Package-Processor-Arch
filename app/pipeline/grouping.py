import re
from collections import defaultdict

from app.models import Classification, Document, DocumentType, Page

PAGE_COUNTER_PATTERN = re.compile(r"page\s+(\d+)\s+of\s+(\d+)", re.I)
STATEMENT_PERIOD_PATTERN = re.compile(
    r"(?:statement period|period ending)[:\s]+([A-Z][a-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2})",
    re.I,
)


def _page_counter(text: str) -> tuple[int, int] | None:
    match = PAGE_COUNTER_PATTERN.search(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _statement_period(text: str) -> str | None:
    match = STATEMENT_PERIOD_PATTERN.search(text)
    return match.group(1) if match else None


class DocumentAssembler:
    """Groups page-level classifications into ordered document records."""

    def assemble(self, pages: list[Page], classifications: list[Classification]) -> list[Document]:
        page_by_number = {page.page_number: page for page in pages}
        grouped: dict[DocumentType, list[Classification]] = defaultdict(list)
        for classification in classifications:
            if classification.doc_type is not DocumentType.UNKNOWN:
                grouped[classification.doc_type].append(classification)

        documents: list[Document] = []
        for doc_type, group in grouped.items():
            ordered = sorted(
                group,
                key=lambda classification: self._sort_key(
                    page_by_number[classification.page_number]
                ),
            )
            doc_pages = [classification.page_number for classification in ordered]
            confidences = [classification.confidence for classification in ordered]
            period = None
            if doc_type == DocumentType.BANK_STATEMENT:
                period = next(
                    (
                        _statement_period(page_by_number[classification.page_number].text)
                        for classification in ordered
                        if _statement_period(page_by_number[classification.page_number].text)
                    ),
                    None,
                )

            documents.append(
                Document(
                    type=doc_type,
                    pages=doc_pages,
                    signed=None,
                    confidence=sum(confidences) / len(confidences),
                    period=period,
                )
            )

        return sorted(documents, key=lambda document: min(document.pages))

    @staticmethod
    def _sort_key(page: Page) -> tuple[int, int]:
        counter = _page_counter(page.text)
        if counter:
            return counter[0], page.page_number
        return page.page_number, page.page_number
