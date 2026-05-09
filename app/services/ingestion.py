from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO

import fitz
import imagehash
import pytesseract
from PIL import Image

from app.core.config import Settings, get_settings
from app.models import BoundingBox, ExceptionItem, Page, PageSource, TextBlock


@dataclass(frozen=True)
class PdfIngestionResult:
    """Normalized page records plus non-fatal ingestion exceptions."""

    pages: list[Page]
    exceptions: list[ExceptionItem]


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


class PdfIngestionService:
    """Converts a raw PDF bundle into normalized Page models.

    The service follows the case-study constraints: filenames are ignored, each page is inspected
    independently, native text is preferred, scanned pages fall back to local OCR, and recoverable
    page-level failures are emitted as exceptions instead of crashing the whole package.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def ingest(self, pdf_bytes: bytes) -> PdfIngestionResult:
        exceptions: list[ExceptionItem] = []
        pages: list[Page] = []

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if document.page_count > self.settings.max_pdf_pages:
                exceptions.append(
                    ExceptionItem(
                        type="pdf_page_limit_exceeded",
                        detail=(
                            f"PDF has {document.page_count} pages; only the first "
                            f"{self.settings.max_pdf_pages} pages will be processed"
                        ),
                    )
                )

            page_count = min(document.page_count, self.settings.max_pdf_pages)
            for page_index in range(page_count):
                page = document.load_page(page_index)
                page_number = page_index + 1
                try:
                    pages.append(self._extract_page(page, page_number, exceptions))
                except Exception as exc:
                    exceptions.append(
                        ExceptionItem(
                            type="page_ingestion_failed",
                            detail=f"Page {page_number} could not be extracted: {exc}",
                            pages=[page_number],
                        )
                    )
                    pages.append(
                        Page(
                            page_number=page_number,
                            source=PageSource.SCANNED_IMAGE,
                            text="",
                            phash=None,
                            quality_score=0.0,
                        )
                    )
        finally:
            document.close()

        return PdfIngestionResult(pages=pages, exceptions=exceptions)

    def _extract_page(
        self,
        page: fitz.Page,
        page_number: int,
        exceptions: list[ExceptionItem],
    ) -> Page:
        native_text, text_blocks = self._extract_native_text(page)
        phash = self._page_phash(page)

        if len(native_text.strip()) >= self.settings.native_text_minimum_chars:
            return Page(
                page_number=page_number,
                source=PageSource.NATIVE_DIGITAL,
                text=native_text,
                text_blocks=text_blocks,
                phash=phash,
                quality_score=1.0,
            )

        ocr_text = ""
        try:
            ocr_text = self._ocr_page(page)
        except Exception as exc:
            exceptions.append(
                ExceptionItem(
                    type="ocr_failed",
                    detail=f"OCR failed for page {page_number}: {exc}",
                    pages=[page_number],
                )
            )

        return Page(
            page_number=page_number,
            source=PageSource.SCANNED_IMAGE,
            text=ocr_text or native_text,
            text_blocks=text_blocks,
            phash=phash,
            quality_score=0.65 if ocr_text else 0.25,
        )

    @staticmethod
    def _extract_native_text(page: fitz.Page) -> tuple[str, list[TextBlock]]:
        text_blocks: list[TextBlock] = []
        chunks: list[str] = []
        text_dict = page.get_text("dict")

        for block in text_dict.get("blocks", []):
            lines: list[str] = []
            for line in block.get("lines", []):
                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                if line_text.strip():
                    lines.append(line_text)
            block_text = "\n".join(lines).strip()
            if not block_text:
                continue

            chunks.append(block_text)
            bbox = block.get("bbox")
            text_blocks.append(
                TextBlock(
                    text=block_text,
                    bbox=BoundingBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3])
                    if bbox
                    else None,
                )
            )

        return "\n".join(chunks), text_blocks

    def _page_phash(self, page: fitz.Page) -> str:
        image = self._render_page_image(page, dpi=self.settings.pdf_render_dpi)
        return str(imagehash.phash(image))

    def _ocr_page(self, page: fitz.Page) -> str:
        image = self._render_page_image(page, dpi=self.settings.ocr_render_dpi)
        return pytesseract.image_to_string(image).strip()

    @staticmethod
    def _render_page_image(page: fitz.Page, dpi: int) -> Image.Image:
        pixmap = page.get_pixmap(dpi=dpi, alpha=False)
        image_bytes = pixmap.tobytes("png")
        return Image.open(BytesIO(image_bytes)).convert("RGB")
