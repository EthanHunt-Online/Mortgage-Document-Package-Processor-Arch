# Mortgage Document Package Processor — Architecture

A FastAPI-first reference architecture for processing mortgage PDF packages into grouped,
ordered, and validated document records while minimizing LLM cost.

## Pipeline Overview

```text
PDF Upload → Page Ingestion → Pre-processing → Classification → Duplicate Detection → Grouping & Ordering → Validation → Output
```

## Recommended Stack

| Layer | Choice | Why |
| --- | --- | --- |
| API | FastAPI | Async-ready Python API, upload support, OpenAPI docs, simple deployment surface. |
| PDF parsing | PyMuPDF (`fitz`) | Fast page splitting, native text extraction, page rendering. |
| OCR | Tesseract via `pytesseract` | Local, low-cost OCR for scanned pages. |
| Image hashing | `imagehash`/Pillow | Perceptual hash for exact and near-duplicate detection. |
| Cheap ML | scikit-learn TF-IDF + Logistic Regression | Transparent second-pass classifier before LLM fallback. |
| LLM fallback | Structured-output capable provider | Only ambiguous OCR/native text snippets are sent to the LLM. |
| Service contract | Pydantic v2 models | Strong JSON schema for API and worker boundaries. |

## Implemented Proof-of-Architecture

This repository now includes a deterministic service skeleton with both text-snippet and PDF upload
entrypoints:

- `app/main.py` starts the FastAPI app.
- `app/api/routes.py` exposes:
  - `GET /health`
  - `POST /packages/process-text` for text-snippet proof-of-processing
  - `POST /packages/process-pdf` for multipart PDF uploads
- `app/services/ingestion.py` opens PDFs with PyMuPDF, extracts native text and bounding boxes,
  renders page images for perceptual hashes, falls back to local Tesseract OCR for scanned pages,
  and emits non-fatal ingestion exceptions.
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

## End-to-End Protocol

The design follows the case-study constraints: do not trust file names, do not assume pages are
machine-readable, avoid unnecessary LLM calls, handle unseen packages, and prefer partial output with
specific exceptions over crashes.

| Stage | Objective | Logic / Algorithm | Tools | Cost and Latency Control |
| --- | --- | --- | --- | --- |
| 1. PDF upload | Accept a raw, randomly ordered mortgage bundle. | `POST /packages/process-pdf` accepts multipart uploads and optional `package_id`; file name is used only as a fallback identifier, never as a classification signal. | FastAPI `UploadFile`, Pydantic response model. | Streaming upload interface; reject empty/non-PDF-looking uploads before processing. |
| 2. Page ingestion and pre-processing | Normalize up to 2,000 PDF pages into independent page records. | Open with PyMuPDF, inspect each page, extract native text and bounding boxes, render page image, compute pHash. If native text is too sparse, render at OCR DPI and run Tesseract. Page failures become `exceptions[]`. | PyMuPDF, Pillow, imagehash, Tesseract. | Native text path avoids OCR; local OCR has zero LLM cost; configurable page limit and render DPI. |
| 3. Lightweight classification | Classify obvious pages without an LLM. | Regex/keyword rules identify 1003, bank statements, W-2, 1040, paystubs, and closing disclosures. A sklearn adapter is the second-pass boundary for TF-IDF + Logistic Regression. | Python regex, scikit-learn adapter. | Free deterministic pass first; only low-confidence pages continue. |
| 4. Targeted LLM classification | Resolve ambiguous pages only. | Batch unresolved page-text snippets, truncate to configured token budget, and return structured classifications. Current adapter is a production integration seam. | Claude/GPT-class structured output provider. | Text-only snippets, batch size 10, first 500 tokens, pHash-based cache-ready boundary. |
| 5. Duplicate detection | Flag exact and near-duplicate pages. | Compare pHashes with Hamming distance; group near matches and keep the highest-quality page as canonical. | imagehash, Python bit operations. | Hash comparisons are cheap; avoids duplicate LLM/classification work in production cache. |
| 6. Grouping and ordering | Assemble document records from random page order. | Group by `doc_type`, sort by `Page X of Y` counters when present, otherwise preserve package order; extract bank statement period when present. | Pydantic models, regex. | Lightweight deterministic ordering before any semantic embedding enhancement. |
| 7. Validation | Detect completeness and quality problems. | Required document checks, page-counter gaps, signature cues, duplicate-page exceptions. | Config-driven Python validators. | Non-crashing validation preserves partial output and flags review work. |
| 8. Output | Return structured decisioning payload. | Return `documents[]`, `exceptions[]`, and `duplicate_groups[]`. | FastAPI JSON response. | Client receives usable partial results even if OCR/page extraction fails. |

## Upload PDF API

Run the API:

```bash
uvicorn app.main:app --reload
```

Upload a mortgage PDF bundle:

```bash
curl -X POST http://127.0.0.1:8000/packages/process-pdf \
  -F 'package_id=PKG-20240509-001' \
  -F 'file=@/path/to/mortgage-package.pdf;type=application/pdf'
```

The response uses the same output contract as the text endpoint. Ingestion exceptions such as
`ocr_failed`, `page_ingestion_failed`, or `pdf_page_limit_exceeded` are prepended to pipeline
exceptions so downstream review sees exactly what degraded.

## Stage 1: Ingestion & Pre-processing

**Objective:** Normalize raw PDFs into processable page units.

Implemented PDF ingestion:

1. Split PDFs into individual pages with PyMuPDF.
2. Detect native digital pages by checking extracted text length.
3. OCR scanned image pages with local Tesseract.
4. Extract text and bounding boxes into the `Page` model.
5. Generate a perceptual hash (`phash`) for duplicate detection.
6. Continue past recoverable page/OCR failures by appending exception records.

The `app/services/ingestion.py` text-snippet helper remains available for fast unit tests and local
pipeline demos before using real PDF files.

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

Example text-only request:

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
