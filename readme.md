# Mortgage Document Package Processor

A cost-aware, high-throughput architecture for processing mortgage PDF packages into grouped, ordered, validated document outputs.

## Pipeline

```text
PDF Ingest → Pre-processing → Classification → Duplicate Detection → Grouping & Ordering → Validation → Output
```

## Goals

- Identify each mortgage document type in a package.
- Group all pages that belong to each document.
- Order pages inside each document using page counters, dates, and semantic continuity.
- Flag missing pages, missing signatures, duplicate pages, and checklist failures.
- Minimize LLM usage by exhausting deterministic and local ML classification first.
- Scale horizontally for large daily volume targets such as 1,000 packages/day.

## Recommended Stack

- **API:** FastAPI
- **PDF extraction:** PyMuPDF (`fitz`)
- **OCR:** Tesseract via `pytesseract`
- **Duplicate detection:** perceptual hashes with Hamming-distance matching
- **Classical ML:** scikit-learn TF-IDF + Logistic Regression
- **LLM fallback:** structured JSON responses for only ambiguous pages
- **Validation:** config-driven checklist plus pluggable signature detection

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
uvicorn mortgage_processor.api:app --reload
```

## API Example

```bash
curl -X POST http://127.0.0.1:8000/process-package \
  -H 'content-type: application/json' \
  -d '{
    "package_id": "PKG-20240509-001",
    "pages": [
      {"page_number": 1, "text": "Uniform Residential Loan Application Form 1003 Page 1 of 2 Borrower Signature", "native_text": true},
      {"page_number": 2, "text": "Uniform Residential Loan Application Form 1003 Page 2 of 2 Borrower Signature", "native_text": true},
      {"page_number": 3, "text": "Bank Statement March 2024 Account Summary Page 1 of 1", "native_text": true}
    ]
  }'
```

## Architecture Notes

See [`docs/architecture.md`](docs/architecture.md) for the full staged design and implementation details.
