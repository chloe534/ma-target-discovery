"""Business model classification and disqualifier detection."""

import logging
from dataclasses import dataclass
from typing import Optional

from app.models import AcquisitionCriteria
from .parser import RuleBasedParser

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of business classification."""

    business_model: Optional[str]
    confidence: float
    customer_types: list[str]
    industries: list[str]
    disqualifiers_detected: list[str]
    is_disqualified: bool
    disqualification_reasons: list[str]


class BusinessClassifier:
    """Classify business model and detect disqualifiers."""

    # Industry keyword mappings
    INDUSTRY_KEYWORDS = {
        "healthcare tech": [
            "healthcare", "health tech", "medical", "patient", "clinical",
            "hospital", "telehealth", "healthtech", "medtech", "ehr", "emr",
        ],
        "fintech": [
            "fintech", "financial", "banking", "payments", "lending",
            "insurance", "insurtech", "wealth", "trading", "crypto",
        ],
        "edtech": [
            "education", "edtech", "learning", "school", "training",
            "e-learning", "lms", "course", "student",
        ],
        "cybersecurity": [
            "security", "cybersecurity", "infosec", "threat", "vulnerability",
            "encryption", "firewall", "compliance", "soc", "siem",
        ],
        "devtools": [
            "developer", "devops", "ci/cd", "deployment", "infrastructure",
            "api", "sdk", "code", "programming", "software development",
        ],
        "martech": [
            "marketing", "martech", "advertising", "analytics", "attribution",
            "campaign", "crm", "customer data", "email marketing",
        ],
        "hrtech": [
            "hr", "human resources", "recruiting", "hiring", "payroll",
            "benefits", "workforce", "talent", "employee",
        ],
        "proptech": [
            "real estate", "property", "proptech", "housing", "rental",
            "mortgage", "construction", "building",
        ],
        "logistics": [
            "logistics", "shipping", "supply chain", "warehouse", "delivery",
            "freight", "fleet", "transportation",
        ],
        "data infrastructure": [
            "data", "database", "data warehouse", "etl", "data pipeline",
            "analytics", "bi", "business intelligence", "data lake",
        ],
    }

    # Common disqualifier patterns
    DISQUALIFIER_PATTERNS = {
        "cryptocurrency": [r"\bcrypto\b", r"\bblockchain\b", r"\bnft\b", r"\bweb3\b"],
        "gambling": [r"\bgambling\b", r"\bcasino\b", r"\bbetting\b", r"\bpoker\b"],
        "adult_content": [r"\badult\b", r"\bexplicit\b", r"\b18\+\b"],
        "weapons": [r"\bweapons?\b", r"\bfirearms?\b", r"\bammunition\b"],
        "tobacco": [r"\btobacco\b", r"\bcigarette\b", r"\bvaping\b", r"\be-?cig\b"],
        "government_contractor": [r"\bgovernment.contract\b", r"\bdefense.contract\b"],
        "litigation": [r"\blawsuit\b", r"\blitigation\b", r"\bsued\b"],
        "bankruptcy": [r"\bbankruptcy\b", r"\binsolvent\b", r"\bchapter.11\b"],
    }

    def __init__(self):
        self.parser = RuleBasedParser()

    def classify(
        self,
        text: str,
        criteria: AcquisitionCriteria,
        existing_data: Optional[dict] = None,
    ) -> ClassificationResult:
        """Classify a company based on text content and criteria."""
        existing_data = existing_data or {}

        # Parse text for structured data
        parsed = self.parser.parse(text)

        # Determine business model
        business_model = existing_data.get("business_model") or parsed.business_model
        bm_confidence = existing_data.get("business_model_confidence", 0) or parsed.business_model_confidence

        # Detect industries
        industries = self._detect_industries(text, criteria)

        # Detect customer types
        customer_types = existing_data.get("customer_types", []) or parsed.customer_types

        # Check disqualifiers
        disqualifiers_detected, disqualification_reasons = self._check_disqualifiers(
            text, criteria
        )

        # Check exclusions
        is_disqualified = bool(disqualification_reasons)

        # Check if business model is excluded
        if business_model and criteria.business_model.exclude_types:
            if business_model.lower() in [t.lower() for t in criteria.business_model.exclude_types]:
                is_disqualified = True
                disqualification_reasons.append(f"Excluded business model: {business_model}")

        # Check if industry is excluded
        for industry in industries:
            if industry.lower() in [i.lower() for i in criteria.industries_exclude]:
                is_disqualified = True
                disqualification_reasons.append(f"Excluded industry: {industry}")

        return ClassificationResult(
            business_model=business_model,
            confidence=bm_confidence,
            customer_types=customer_types,
            industries=industries,
            disqualifiers_detected=disqualifiers_detected,
            is_disqualified=is_disqualified,
            disqualification_reasons=disqualification_reasons,
        )

    def _detect_industries(
        self,
        text: str,
        criteria: AcquisitionCriteria,
    ) -> list[str]:
        """Detect industries from text."""
        text_lower = text.lower()
        detected = []

        # Check criteria industries first
        for industry in criteria.industries_include:
            industry_lower = industry.lower()
            if industry_lower in self.INDUSTRY_KEYWORDS:
                keywords = self.INDUSTRY_KEYWORDS[industry_lower]
            else:
                keywords = [industry_lower]

            for keyword in keywords:
                if keyword in text_lower:
                    detected.append(industry)
                    break

        # Also check all known industries
        for industry, keywords in self.INDUSTRY_KEYWORDS.items():
            if industry not in [d.lower() for d in detected]:
                for keyword in keywords:
                    if keyword in text_lower:
                        detected.append(industry)
                        break

        return list(set(detected))

    def _check_disqualifiers(
        self,
        text: str,
        criteria: AcquisitionCriteria,
    ) -> tuple[list[str], list[str]]:
        """Check for disqualifying conditions."""
        import re

        text_lower = text.lower()
        detected = []
        reasons = []

        # Check standard disqualifier patterns
        for name, patterns in self.DISQUALIFIER_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.I):
                    detected.append(name)
                    break

        # Check criteria-specific disqualifiers
        for disqualifier in criteria.disqualifiers:
            pattern = r"\b" + re.escape(disqualifier.lower()) + r"\b"
            if re.search(pattern, text_lower, re.I):
                detected.append(disqualifier)

        # Check dealbreakers (hard fails)
        for dealbreaker in criteria.dealbreakers:
            pattern = r"\b" + re.escape(dealbreaker.lower()) + r"\b"
            if re.search(pattern, text_lower, re.I):
                detected.append(dealbreaker)
                reasons.append(f"Dealbreaker detected: {dealbreaker}")

        # Check excluded keywords
        for keyword in criteria.keywords_exclude:
            pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
            if re.search(pattern, text_lower, re.I):
                detected.append(keyword)
                reasons.append(f"Excluded keyword found: {keyword}")

        return detected, reasons
