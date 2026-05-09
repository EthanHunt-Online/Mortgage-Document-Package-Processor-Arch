from app.core.config import Settings, get_settings
from app.models import DuplicateGroup, Page


def hamming_distance(left: str, right: str) -> int:
    """Return the bit-level Hamming distance between two hexadecimal perceptual hashes."""

    return bin(int(left, 16) ^ int(right, 16)).count("1")


class DuplicateDetector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def detect(self, pages: list[Page]) -> list[DuplicateGroup]:
        groups: list[DuplicateGroup] = []
        consumed: set[int] = set()
        hashable_pages = [page for page in pages if page.phash]

        for page in hashable_pages:
            if page.page_number in consumed:
                continue

            matches = [
                candidate
                for candidate in hashable_pages
                if candidate.page_number != page.page_number
                and candidate.page_number not in consumed
                and candidate.phash
                and page.phash
                and hamming_distance(page.phash, candidate.phash)
                < self.settings.duplicate_hamming_threshold
            ]
            if not matches:
                continue

            candidates = [page, *matches]
            canonical = max(candidates, key=lambda candidate: candidate.quality_score)
            duplicate_pages = sorted(
                candidate.page_number
                for candidate in candidates
                if candidate.page_number != canonical.page_number
            )
            consumed.update(candidate.page_number for candidate in candidates)
            groups.append(
                DuplicateGroup(
                    canonical_page=canonical.page_number,
                    duplicate_pages=duplicate_pages,
                    reason="near_duplicate_phash",
                )
            )

        return groups
