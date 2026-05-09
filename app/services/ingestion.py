from collections.abc import Iterable

from app.models import Page, PageSource


def pages_from_text_snippets(snippets: Iterable[str]) -> list[Page]:
    """Test/dev ingestion helper that turns text snippets into Page models.

    Production PDF ingestion should split with PyMuPDF, OCR scanned pages with Tesseract,
    and compute perceptual hashes before constructing the same Page model used by the rest of the
    pipeline.
    """

    return [
        Page(
            page_number=index,
            source=PageSource.NATIVE_DIGITAL,
            text=snippet,
            phash=f"{index:016x}",
            quality_score=1.0,
        )
        for index, snippet in enumerate(snippets, start=1)
    ]
