# Mortgage Document Package Processor Architecture

## Overview

The processor converts a mixed mortgage PDF package into a deterministic JSON result that lists identified documents, ordered page ranges, confidence scores, and non-blocking exceptions.

```text
PDF Ingest → Pre-processing → Classification → Duplicate Detection → Grouping & Ordering → Validation → Output
```

The design keeps expensive LLM calls at the edge of the system. Native PDF text extraction, OCR, perceptual hashing, keyword/regex rules, and classical ML all run before the LLM fallback.

## Stage 1: Ingestion and Pre-processing

**Objective:** normalize raw PDFs into page-level records.

1. Split PDFs into page units with PyMuPDF.
2. Detect whether each page is native digital or scanned.
3. Run local Tesseract OCR only for scanned pages.
4. Persist extracted text and bounding boxes as page JSON.
5. Generate a perceptual hash for every page.

Page records should include:

- package ID
- one-based page number
- extracted text
- bounding boxes
- native/scanned indicator
- pHash
- quality score

## Stage 2: Lightweight Classification

**Objective:** classify most pages without LLM usage.

Rule examples:

| Signal | Example |
| --- | --- |
| Keyword | `Form 1003`, `Uniform Residential` → loan application |
| Regex | SSN-like pattern with `W-2` → tax document |
| Layout | twelve monthly rows → bank statement |
| Logo/template | known lender or bank logo → source-specific statement |

A TF-IDF + Logistic Regression classifier can run after rules to classify common mortgage forms learned from labeled pages. Production routing should use confidence thresholds so low-confidence classical predictions still go to the LLM fallback.

## Stage 3: Targeted LLM Classification

**Objective:** handle only ambiguous pages.

- Send only unclassified or low-confidence page snippets.
- Batch snippets, for example up to ten pages per API request.
- Truncate text to header/footer-heavy snippets, such as the first 500 tokens.
- Request strict structured output: `doc_type`, `confidence`, and `key_fields_found`.
- Cache results by pHash to avoid repeat LLM cost across packages.

## Stage 4: Duplicate Detection

**Objective:** identify exact and near-duplicate pages.

- Compare perceptual hashes within each package.
- Treat Hamming distance below a small threshold, such as five, as a near duplicate.
- Group duplicate pages and keep the best-quality page for downstream assembly.
- Append duplicate details to the exceptions list without crashing processing.

## Stage 5: Grouping and Sequence Ordering

**Objective:** assemble page-level classifications into document-level units.

Ordering precedence:

1. Explicit page counters such as `Page X of Y`.
2. Date signals such as bank statement periods.
3. Semantic continuity using short text embeddings and cosine similarity.
4. Original package order as the final deterministic fallback.

Missing page detection runs during this stage by comparing observed counters against expected counters.

## Stage 6: Validation

**Objective:** verify completeness and quality.

Validation checks are config-driven and non-crashing:

| Check | Method |
| --- | --- |
| Required documents | checklist by package/product type |
| Signature presence | CV signature detector or text/layout rule near signature lines |
| Missing pages | page counter gap analysis |
| Date consistency | final 1003 date after initial 1003 date |
| Duplicate versions | signature and date based final-version heuristic |

Failures are appended to `exceptions[]` so operations teams receive a complete report for each package.

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
      "detail": "Page 3 of 4 not found"
    }
  ]
}
```

## Scaling Model

At 1,000 packages/day, average load is modest but burst handling matters. The recommended deployment is:

- FastAPI API tier for upload, status, and result retrieval.
- Worker queue for CPU-heavy PDF extraction and OCR.
- Independent classifier workers for rules, sklearn, and LLM fallback.
- Shared cache keyed by pHash for duplicate and LLM classification reuse.
- Object storage for original PDFs and page JSON artifacts.
- Relational database for package state, document metadata, and exceptions.

## Cost Controls

- Prefer native text extraction over OCR.
- Use local OCR rather than vision LLMs for scanned pages.
- Apply rules and sklearn before LLM fallback.
- Send text snippets only, not full-page images.
- Batch LLM requests.
- Cache LLM responses by pHash.
- Store model confidence and route only ambiguous pages to manual review.
