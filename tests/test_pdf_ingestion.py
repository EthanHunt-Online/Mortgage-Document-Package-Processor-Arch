import fitz

from app.models import PageSource
from app.services.ingestion import PdfIngestionService


def test_pdf_ingestion_extracts_native_text_and_phash() -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Uniform Residential Loan Application Form 1003 Page 1 of 1")
    pdf_bytes = document.tobytes()
    document.close()

    result = PdfIngestionService().ingest(pdf_bytes)

    assert result.exceptions == []
    assert len(result.pages) == 1
    assert result.pages[0].source == PageSource.NATIVE_DIGITAL
    assert "Uniform Residential" in result.pages[0].text
    assert result.pages[0].phash
