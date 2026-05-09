from app.models import Document, DocumentType, DuplicateGroup, ExceptionItem, Page
from app.pipeline.grouping import PAGE_COUNTER_PATTERN

REQUIRED_DOCUMENTS = {
    DocumentType.LOAN_APPLICATION_1003,
    DocumentType.BANK_STATEMENT,
}

SIGNATURE_TERMS = ("borrower signature", "applicant signature", "signature of borrower")
SIGNED_TERMS = ("/s/", "electronically signed", "signed by")


class PackageValidator:
    """Applies non-crashing validation checks and emits exception records."""

    def validate(
        self,
        pages: list[Page],
        documents: list[Document],
        duplicate_groups: list[DuplicateGroup],
    ) -> list[ExceptionItem]:
        exceptions: list[ExceptionItem] = []
        present_types = {document.type for document in documents}

        for required in sorted(REQUIRED_DOCUMENTS):
            if required not in present_types:
                exceptions.append(
                    ExceptionItem(
                        type="missing_required_document",
                        doc=required.value,
                        detail=f"Required document type {required.value} not found",
                    )
                )

        page_by_number = {page.page_number: page for page in pages}
        for document in documents:
            doc_pages = [page_by_number[number] for number in document.pages]
            exceptions.extend(self._missing_page_exceptions(document, doc_pages))
            document.signed = self._is_signed(doc_pages)
            if self._requires_signature(document.type) and not document.signed:
                exceptions.append(
                    ExceptionItem(
                        type="missing_signature",
                        doc=document.type.value,
                        detail="Signature cue not detected on document pages",
                        pages=document.pages,
                    )
                )

        for duplicate_group in duplicate_groups:
            exceptions.append(
                ExceptionItem(
                    type="duplicate_pages",
                    detail=(
                        f"Canonical page {duplicate_group.canonical_page}; duplicates "
                        f"{duplicate_group.duplicate_pages}"
                    ),
                    pages=[duplicate_group.canonical_page, *duplicate_group.duplicate_pages],
                )
            )

        return exceptions

    @staticmethod
    def _missing_page_exceptions(document: Document, pages: list[Page]) -> list[ExceptionItem]:
        counters: dict[int, int] = {}
        for page in pages:
            match = PAGE_COUNTER_PATTERN.search(page.text)
            if match:
                counters[int(match.group(1))] = int(match.group(2))

        if not counters:
            return []

        total = max(counters.values())
        missing = sorted(set(range(1, total + 1)) - set(counters))
        if not missing:
            return []

        return [
            ExceptionItem(
                type="missing_page",
                doc=document.type.value,
                detail=f"Missing page(s) {missing} of {total}",
                pages=document.pages,
            )
        ]

    @staticmethod
    def _is_signed(pages: list[Page]) -> bool:
        text = "\n".join(page.text.lower() for page in pages)
        return any(term in text for term in SIGNED_TERMS)

    @staticmethod
    def _requires_signature(doc_type: DocumentType) -> bool:
        return doc_type in {
            DocumentType.LOAN_APPLICATION_1003,
            DocumentType.INITIAL_LOAN_APPLICATION_1003,
            DocumentType.FINAL_LOAN_APPLICATION_1003,
            DocumentType.CLOSING_DISCLOSURE,
        }
