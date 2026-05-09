import re
from collections.abc import Iterable

from app.core.config import Settings, get_settings
from app.models import Classification, ClassificationMethod, DocumentType, Page

Rule = tuple[DocumentType, float, list[re.Pattern[str]], list[str]]

RULES: list[Rule] = [
    (
        DocumentType.FINAL_LOAN_APPLICATION_1003,
        0.95,
        [
            re.compile(r"\bfinal\b", re.I),
            re.compile(r"uniform residential loan application|form 1003", re.I),
        ],
        ["final", "form_1003"],
    ),
    (
        DocumentType.LOAN_APPLICATION_1003,
        0.92,
        [re.compile(r"uniform residential loan application|form 1003", re.I)],
        ["form_1003"],
    ),
    (
        DocumentType.BANK_STATEMENT,
        0.90,
        [re.compile(r"bank statement|statement period|beginning balance|ending balance", re.I)],
        ["statement_period"],
    ),
    (
        DocumentType.TAX_RETURN_1040,
        0.91,
        [re.compile(r"form 1040|u\.s\. individual income tax return", re.I)],
        ["form_1040"],
    ),
    (
        DocumentType.W2,
        0.90,
        [
            re.compile(r"\bw-?2\b|wage and tax statement", re.I),
            re.compile(r"employer identification number", re.I),
        ],
        ["w2", "ein"],
    ),
    (
        DocumentType.PAYSTUB,
        0.88,
        [re.compile(r"paystub|pay statement|gross pay|net pay", re.I)],
        ["gross_pay", "net_pay"],
    ),
    (
        DocumentType.CLOSING_DISCLOSURE,
        0.92,
        [re.compile(r"closing disclosure|loan costs|cash to close", re.I)],
        ["closing_disclosure"],
    ),
]


class RuleBasedClassifier:
    """Cheap, deterministic classifier for high-signal mortgage pages."""

    def classify(self, page: Page) -> Classification:
        normalized = page.text.strip()
        if not normalized:
            return Classification(page_number=page.page_number)

        for doc_type, confidence, patterns, fields in RULES:
            if all(pattern.search(normalized) for pattern in patterns):
                return Classification(
                    page_number=page.page_number,
                    doc_type=doc_type,
                    confidence=confidence,
                    method=ClassificationMethod.RULE,
                    key_fields_found=fields,
                )

        return Classification(page_number=page.page_number)


class SklearnClassifierAdapter:
    """Adapter boundary for a trained TF-IDF + Logistic Regression model.

    The production implementation can load a persisted sklearn pipeline. The default
    implementation intentionally returns UNKNOWN so the service remains deterministic until a model
    artifact exists.
    """

    def classify(self, page: Page) -> Classification:
        return Classification(page_number=page.page_number)


class LLMClassifierAdapter:
    """Boundary for targeted LLM classification of only unresolved pages."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def classify_batch(self, pages: Iterable[Page]) -> list[Classification]:
        classifications: list[Classification] = []
        for page in pages:
            snippet = " ".join(page.text.split()[: self.settings.llm_text_token_budget])
            classifications.append(
                Classification(
                    page_number=page.page_number,
                    doc_type=DocumentType.UNKNOWN,
                    confidence=0.0,
                    method=ClassificationMethod.UNCLASSIFIED,
                    key_fields_found=["llm_pending"] if snippet else [],
                )
            )
        return classifications


class CascadingClassifier:
    """Runs rule, sklearn, then LLM classification to minimize LLM spend."""

    def __init__(
        self,
        settings: Settings | None = None,
        rule_classifier: RuleBasedClassifier | None = None,
        sklearn_classifier: SklearnClassifierAdapter | None = None,
        llm_classifier: LLMClassifierAdapter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.rule_classifier = rule_classifier or RuleBasedClassifier()
        self.sklearn_classifier = sklearn_classifier or SklearnClassifierAdapter()
        self.llm_classifier = llm_classifier or LLMClassifierAdapter(self.settings)

    def classify_pages(self, pages: list[Page]) -> list[Classification]:
        final: dict[int, Classification] = {}
        unresolved: list[Page] = []

        for page in pages:
            rule_result = self.rule_classifier.classify(page)
            if rule_result.confidence >= self.settings.minimum_auto_classification_confidence:
                final[page.page_number] = rule_result
                continue

            sklearn_result = self.sklearn_classifier.classify(page)
            if sklearn_result.confidence >= self.settings.minimum_auto_classification_confidence:
                final[page.page_number] = sklearn_result
            else:
                unresolved.append(page)

        for start in range(0, len(unresolved), self.settings.max_llm_batch_size):
            batch = unresolved[start : start + self.settings.max_llm_batch_size]
            for llm_result in self.llm_classifier.classify_batch(batch):
                final[llm_result.page_number] = llm_result

        return [final[page.page_number] for page in pages]
