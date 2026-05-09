# Mortgage Document Package Processor — Architecture

A FastAPI-first reference architecture for processing mortgage PDF packages into grouped,
ordered, and validated document records while minimizing LLM cost.

## Pipeline Overview

```text
PDF Ingest → Pre-processing → Classification → Duplicate Detection → Grouping & Ordering → Validation → Output
```

## Recommended Stack

| Layer | Choice | Why |
| --- | --- | --- |
| API | FastAPI | Async-ready Python API, OpenAPI docs, simple deployment surface. |
| PDF parsing | PyMuPDF (`fitz`) | Fast page splitting, native text extraction, page rendering. |
| OCR | Tesseract via `pytesseract` | Local, low-cost OCR for scanned pages. |
| Image hashing | `imagehash`/Pillow | Perceptual hash for exact and near-duplicate detection. |
| Cheap ML | scikit-learn TF-IDF + Logistic Regression | Transparent second-pass classifier before LLM fallback. |
| LLM fallback | Structured-output capable provider | Only ambiguous OCR/native text snippets are sent to the LLM. |
| Service contract | Pydantic v2 models | Strong JSON schema for API and worker boundaries. |

## Implemented Proof-of-Architecture

This repository now includes a deterministic service skeleton that can run without external LLM
credentials:

- `app/main.py` starts the FastAPI app.
- `app/api/routes.py` exposes `GET /health` and `POST /packages/process-text` for text-snippet
  proof-of-processing.
- `app/models.py` defines the page, classification, duplicate, document, exception, and package
  output contracts.
- `app/pipeline/classification.py` implements the cost-saving cascade:
  1. rule-based classifier,
  2. sklearn adapter boundary,
  3. LLM adapter boundary for unresolved pages only.
- `app/pipeline/duplicates.py` detects near-duplicate perceptual hashes and keeps the highest-quality
  page.
- `app/pipeline/grouping.py` groups classified pages and orders by `Page X of Y` when available.
- `app/pipeline/validation.py` emits non-crashing exceptions for required documents, missing pages,
  missing signatures, and duplicates.
- `app/pipeline/processor.py` orchestrates the end-to-end post-ingestion pipeline.

## Stage 1: Ingestion & Pre-processing

**Objective:** Normalize raw PDFs into processable page units.

Planned production ingestion should:

1. Split PDFs into individual pages with PyMuPDF.
2. Detect native digital pages by checking selectable text.
3. OCR scanned image pages with local Tesseract.
4. Extract text and bounding boxes into the `Page` model.
5. Generate a perceptual hash (`phash`) for duplicate detection.

The current `app/services/ingestion.py` includes a text-snippet helper so the rest of the pipeline can
be exercised before PDF infrastructure is wired in.

## Stage 2: Lightweight Classification — No LLM

The first classifier pass is deterministic and free. Current examples include:

| Signal | Example Rule |
| --- | --- |
| Keyword match | `Form 1003`, `Uniform Residential` → loan application. |
| Regex patterns | `Form 1040` → tax return; `W-2` + EIN cue → W-2. |
| Statement cues | `statement period`, `beginning balance`, `ending balance` → bank statement. |
| Closing cues | `Closing Disclosure`, `cash to close` → closing disclosure. |

A scikit-learn adapter is included as a clean extension point for a trained TF-IDF + Logistic
Regression pipeline.

## Stage 3: Targeted LLM Classification

Only unresolved pages flow to the LLM adapter. The adapter boundary is intentionally isolated so the
production implementation can add provider-specific structured outputs and cache lookups by `phash`.

Cost controls represented in code/config:

- Batch size defaults to 10 pages.
- Text budget defaults to the first 500 tokens.
- The processor passes text only, never full page images.
- Deterministic stages run before the LLM boundary.

## Stage 4: Duplicate Detection

`DuplicateDetector` compares page perceptual hashes with bit-level Hamming distance. Groups below the
configured threshold are reported as duplicates, and the canonical page is selected by quality score
so native digital pages can win over noisy scans.

## Stage 5: Grouping & Sequence Ordering

`DocumentAssembler` groups pages by `doc_type`, orders pages by detected `Page X of Y` counters when
present, and preserves original package order as a fallback. Bank statement period extraction is
included as document metadata.

## Stage 6: Validation

Validation is non-crashing: failures become `exceptions[]` records. Current checks include:

- required document types present,
- missing page counter gaps,
- missing signature cues for signature-sensitive documents,
- duplicate pages.

## Stage 7: Output Contract

```json
{
  "package_id": "PKG-20240509-001",
  "documents": [
    {
      "type": "final_loan_application_1003",
      "pages": [12, 13, 14],
      "signed": true,
      "confidence": 0.97
    }
  ],
  "exceptions": [
    {
      "type": "missing_page",
      "doc": "tax_return_1040",
      "detail": "Missing page(s) [3] of 4"
    }
  ],
  "duplicate_groups": []
}
```

## Local Development

Install development dependencies:

```bash
python -m pip install -e '.[dev]'
```

Run tests:

```bash
pytest
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Example request:

```bash
curl -X POST http://127.0.0.1:8000/packages/process-text \
  -H 'Content-Type: application/json' \
  -d '{
    "package_id": "PKG-DEMO-001",
    "pages": [
      "Final Uniform Residential Loan Application Form 1003 Page 1 of 2 /s/ Jane Borrower",
      "Final Uniform Residential Loan Application Form 1003 Page 2 of 2",
      "Bank Statement statement period 2024-03 beginning balance ending balance"
    ]
  }'
```

## Scale Notes

For a 1000-package/day target, deploy the API separately from workers:

- API accepts uploads and creates jobs.
- Worker pool performs PyMuPDF/Tesseract extraction in parallel.
- Classification cache uses `phash` as the key.
- LLM calls are batched and limited to unresolved pages.
- Results and exceptions are persisted for audit and downstream review.
