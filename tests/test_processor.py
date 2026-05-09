from app.models import Page, PageSource
from app.pipeline.duplicates import DuplicateDetector, hamming_distance
from app.pipeline.processor import MortgagePackageProcessor


def test_rule_classification_grouping_and_missing_page_detection() -> None:
    pages = [
        Page(
            page_number=1,
            source=PageSource.NATIVE_DIGITAL,
            text=(
                "Final Uniform Residential Loan Application Form 1003 "
                "Page 1 of 3 /s/ Jane Borrower"
            ),
            phash="0000000000000001",
            quality_score=1.0,
        ),
        Page(
            page_number=2,
            source=PageSource.NATIVE_DIGITAL,
            text="Final Uniform Residential Loan Application Form 1003 Page 3 of 3",
            phash="0000000000000002",
            quality_score=1.0,
        ),
        Page(
            page_number=3,
            source=PageSource.NATIVE_DIGITAL,
            text="Bank Statement statement period 2024-03 beginning balance ending balance",
            phash="00000000000000ff",
            quality_score=1.0,
        ),
    ]

    result = MortgagePackageProcessor().process_pages("PKG-TEST-001", pages)

    document_types = {document.type.value for document in result.documents}
    assert "final_loan_application_1003" in document_types
    assert "bank_statement" in document_types
    assert any(exception.type == "missing_page" for exception in result.exceptions)


def test_duplicate_detector_prefers_highest_quality_page() -> None:
    pages = [
        Page(
            page_number=1,
            source=PageSource.SCANNED_IMAGE,
            text="Bank Statement",
            phash="0000000000000000",
            quality_score=0.4,
        ),
        Page(
            page_number=2,
            source=PageSource.NATIVE_DIGITAL,
            text="Bank Statement",
            phash="0000000000000001",
            quality_score=1.0,
        ),
    ]

    groups = DuplicateDetector().detect(pages)

    assert groups[0].canonical_page == 2
    assert groups[0].duplicate_pages == [1]
    assert hamming_distance("0", "f") == 4
