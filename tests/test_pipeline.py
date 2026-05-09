from mortgage_processor.models import PackageRequest, PageInput
from mortgage_processor.pipeline import process_package


def test_process_package_groups_orders_and_extracts_period():
    request = PackageRequest(
        package_id="PKG-20240509-001",
        pages=[
            PageInput(
                page_number=2,
                text="Uniform Residential Loan Application Form 1003 Page 2 of 2 Borrower Signature",
                phash="aaaa",
            ),
            PageInput(
                page_number=1,
                text="Uniform Residential Loan Application Form 1003 Page 1 of 2 Borrower Signature",
                phash="aaab",
            ),
            PageInput(
                page_number=3,
                text="Bank Statement March 2024 Account Summary Page 1 of 1",
                phash="bbbb",
            ),
        ],
    )

    result = process_package(request)

    loan_application = next(document for document in result.documents if document.type == "final_loan_application_1003")
    bank_statement = next(document for document in result.documents if document.type == "bank_statement")

    assert loan_application.pages == [1, 2]
    assert loan_application.signed is True
    assert loan_application.confidence == 0.95
    assert bank_statement.pages == [3]
    assert bank_statement.period == "2024-03"


def test_missing_page_and_missing_signature_are_reported():
    request = PackageRequest(
        package_id="PKG-MISSING",
        pages=[
            PageInput(page_number=1, text="Uniform Residential Loan Application Form 1003 Page 1 of 3"),
            PageInput(page_number=3, text="Uniform Residential Loan Application Form 1003 Page 3 of 3"),
        ],
    )

    result = process_package(request)

    exception_types = {exception.type for exception in result.exceptions}
    assert "missing_page" in exception_types
    assert "missing_signature" in exception_types
    assert any("Page 2 of 3" in exception.detail for exception in result.exceptions)


def test_duplicates_and_unclassified_pages_are_reported():
    duplicate_text = "Bank Statement Account Summary Page 1 of 1"
    request = PackageRequest(
        package_id="PKG-DUPES",
        pages=[
            PageInput(page_number=1, text=duplicate_text, phash="abcde"),
            PageInput(page_number=2, text=duplicate_text, phash="abcdf"),
            PageInput(page_number=3, text="Random cover sheet"),
        ],
    )

    result = process_package(request)

    assert any(exception.type == "duplicate_page" and exception.pages == [1, 2] for exception in result.exceptions)
    assert any(exception.type == "unclassified_page" and exception.pages == [3] for exception in result.exceptions)
