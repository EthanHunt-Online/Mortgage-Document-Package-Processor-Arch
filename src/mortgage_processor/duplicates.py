"""Duplicate page detection helpers."""

from __future__ import annotations

from collections import defaultdict

from mortgage_processor.models import ExceptionResult, PageInput


def hamming_distance(left: str, right: str) -> int:
    """Return the Hamming distance between two equal-length hash strings."""

    if len(left) != len(right):
        return max(len(left), len(right))
    return sum(a != b for a, b in zip(left, right))


def detect_duplicates(pages: list[PageInput], threshold: int = 4) -> list[ExceptionResult]:
    """Detect exact and near-duplicate pages using supplied perceptual hashes."""

    duplicate_groups: list[list[int]] = []
    consumed: set[int] = set()
    hashed_pages = [page for page in pages if page.phash]

    for index, page in enumerate(hashed_pages):
        if page.page_number in consumed or page.phash is None:
            continue

        group = [page.page_number]
        for candidate in hashed_pages[index + 1 :]:
            if candidate.page_number in consumed or candidate.phash is None:
                continue
            if hamming_distance(page.phash, candidate.phash) <= threshold:
                group.append(candidate.page_number)
                consumed.add(candidate.page_number)

        if len(group) > 1:
            consumed.update(group)
            duplicate_groups.append(sorted(group))

    exact_text_groups: defaultdict[str, list[int]] = defaultdict(list)
    for page in pages:
        normalized_text = " ".join(page.text.lower().split())
        if normalized_text:
            exact_text_groups[normalized_text].append(page.page_number)

    for group in exact_text_groups.values():
        sorted_group = sorted(group)
        if len(sorted_group) > 1 and sorted_group not in duplicate_groups:
            duplicate_groups.append(sorted_group)

    return [
        ExceptionResult(
            type="duplicate_page",
            pages=group,
            detail=f"Potential duplicate pages detected: {group}",
        )
        for group in sorted(duplicate_groups, key=lambda item: item[0])
    ]
