from app.models import PackageResult, Page
from app.pipeline.classification import CascadingClassifier
from app.pipeline.duplicates import DuplicateDetector
from app.pipeline.grouping import DocumentAssembler
from app.pipeline.validation import PackageValidator


class MortgagePackageProcessor:
    """Orchestrates classification, duplicate detection, grouping, and validation."""

    def __init__(
        self,
        classifier: CascadingClassifier | None = None,
        duplicate_detector: DuplicateDetector | None = None,
        assembler: DocumentAssembler | None = None,
        validator: PackageValidator | None = None,
    ) -> None:
        self.classifier = classifier or CascadingClassifier()
        self.duplicate_detector = duplicate_detector or DuplicateDetector()
        self.assembler = assembler or DocumentAssembler()
        self.validator = validator or PackageValidator()

    def process_pages(self, package_id: str, pages: list[Page]) -> PackageResult:
        classifications = self.classifier.classify_pages(pages)
        duplicate_groups = self.duplicate_detector.detect(pages)
        documents = self.assembler.assemble(pages, classifications)
        exceptions = self.validator.validate(pages, documents, duplicate_groups)
        return PackageResult(
            package_id=package_id,
            documents=documents,
            exceptions=exceptions,
            duplicate_groups=duplicate_groups,
        )
