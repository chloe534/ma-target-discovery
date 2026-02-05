"""Rule-based extraction from company web pages."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of rule-based extraction."""

    business_model: Optional[str] = None
    business_model_confidence: float = 0.0
    customer_types: list[str] = field(default_factory=list)
    employee_count: Optional[int] = None
    revenue_estimate: Optional[int] = None
    revenue_is_estimated: bool = False
    funding_total: Optional[int] = None
    industries: list[str] = field(default_factory=list)
    compliance_indicators: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)
    overall_confidence: float = 0.0
    # New fields for cannabis/software targeting
    is_cannabis_industry: bool = False
    cannabis_confidence: float = 0.0
    software_revenue_confidence: float = 0.0
    software_indicators_found: list[str] = field(default_factory=list)
    services_indicators_found: list[str] = field(default_factory=list)


class RuleBasedParser:
    """Extract structured data from text using regex and keyword patterns."""

    # Business model patterns
    BUSINESS_MODEL_PATTERNS = {
        "SaaS": [
            r"\b(saas|software.as.a.service)\b",
            r"\b(subscription|recurring.revenue|monthly.plan)\b",
            r"\b(cloud.based|cloud.platform|cloud.software)\b",
        ],
        "marketplace": [
            r"\b(marketplace|two.?sided|platform.connecting)\b",
            r"\b(buyers?.and.sellers?|connect.+with)\b",
        ],
        "services": [
            r"\b(consulting|professional.services|agency)\b",
            r"\b(managed.services|service.provider)\b",
        ],
        "hardware": [
            r"\b(hardware|device|physical.product)\b",
            r"\b(manufacturing|iot.device)\b",
        ],
        "e-commerce": [
            r"\b(e.?commerce|online.store|shop)\b",
            r"\b(retail|direct.to.consumer|d2c)\b",
        ],
    }

    # Customer type patterns
    CUSTOMER_TYPE_PATTERNS = {
        "B2B": [
            r"\b(b2b|business.to.business|enterprise)\b",
            r"\b(for.businesses|business.customers)\b",
        ],
        "B2C": [
            r"\b(b2c|business.to.consumer|consumer)\b",
            r"\b(for.individuals|personal.use)\b",
        ],
        "enterprise": [
            r"\b(enterprise|large.organizations?|fortune.500)\b",
            r"\b(enterprise.grade|enterprise.ready)\b",
        ],
        "SMB": [
            r"\b(smb|small.business|medium.business)\b",
            r"\b(small.and.medium|growing.businesses)\b",
        ],
    }

    # Employee count patterns
    EMPLOYEE_PATTERNS = [
        r"(\d+)\+?\s*employees",
        r"team\s*of\s*(\d+)",
        r"(\d+)\s*team\s*members",
        r"staff\s*of\s*(\d+)",
    ]

    # Revenue patterns (in millions) - use lowercase since text is lowercased
    REVENUE_PATTERNS = [
        r"\$(\d+(?:\.\d+)?)\s*(?:m|million)\s*(?:arr|revenue|mrr)",
        r"\$(\d+(?:\.\d+)?)\s+million\s+(?:arr|revenue|mrr)",
        r"(\d+(?:\.\d+)?)\s*million\s*(?:in\s*)?revenue",
        r"arr\s*(?:of\s*)?\$?(\d+(?:\.\d+)?)\s*(?:m|million)",
    ]

    # Funding patterns
    FUNDING_PATTERNS = [
        r"raised\s*\$?(\d+(?:\.\d+)?)\s*(?:M|million)",
        r"\$(\d+(?:\.\d+)?)\s*(?:M|million)\s*(?:in\s*)?funding",
        r"series\s*[a-d]\s*(?:of\s*)?\$?(\d+(?:\.\d+)?)\s*(?:M|million)",
    ]

    # Compliance indicators
    COMPLIANCE_PATTERNS = {
        "SOC2": [r"\bsoc\s*2\b", r"\bsoc2\b", r"\bsoc.ii\b"],
        "HIPAA": [r"\bhipaa\b", r"\bhipaa.compliant\b"],
        "GDPR": [r"\bgdpr\b", r"\bgdpr.compliant\b"],
        "ISO27001": [r"\biso.?27001\b", r"\biso.27001\b"],
        "PCI-DSS": [r"\bpci.?dss\b", r"\bpci.compliant\b"],
        "FedRAMP": [r"\bfedramp\b"],
    }

    # Positive signals
    SIGNAL_PATTERNS = {
        "growing_team": [r"we.?re.hiring", r"join.our.team", r"open.positions", r"careers"],
        "recent_funding": [r"recently.raised", r"just.raised", r"announced.funding", r"series.[a-d]"],
        "product_launch": [r"just.launched", r"now.available", r"introducing"],
        "customer_growth": [r"serving.(\d+).customers", r"trusted.by.(\d+)"],
        "subscription": [r"subscription", r"monthly.plan", r"annual.plan", r"pricing.plan"],
        "recurring_revenue": [r"recurring.revenue", r"\barr\b", r"\bmrr\b", r"saas"],
    }

    # Software business indicators (for 75% software revenue check)
    SOFTWARE_INDICATORS = [
        r"\bsaas\b",
        r"\bsoftware.as.a.service\b",
        r"cloud.platform",
        r"subscription.software",
        r"software.platform",
        r"pricing.page",
        r"free.trial",
        r"sign.up",
        r"start.free",
        r"monthly.subscription",
        r"annual.subscription",
        r"per.user",
        r"per.seat",
        r"enterprise.plan",
        r"software.solution",
        r"platform.features",
        r"api.access",
        r"integrations",
        r"dashboard",
        r"analytics.platform",
        r"management.software",
        r"automation.platform",
    ]

    # Services/non-software indicators (negative for software revenue check)
    SERVICES_INDICATORS = [
        r"consulting.services",
        r"professional.services",
        r"managed.services",
        r"staffing",
        r"agency.services",
        r"implementation.services",
        r"hourly.rate",
        r"project.based",
        r"custom.development",
        r"outsourcing",
    ]

    # Cannabis industry specific patterns
    CANNABIS_INDICATORS = [
        r"\bcannabis\b",
        r"\bmarijuana\b",
        r"\bdispensary\b",
        r"\bcultivation\b",
        r"\bseed.to.sale\b",
        r"\bseed-to-sale\b",
        r"\bmetrc\b",
        r"\bbiotrack\b",
        r"\bcannabis.compliance\b",
        r"\bcannabis.pos\b",
        r"\bcannabis.retail\b",
        r"\bcannabis.erp\b",
        r"\bhemp\b",
        r"\bcbd\b",
        r"\bthc\b",
        r"\bterpene\b",
        r"\bcannabinoid\b",
        r"\bgrow.operation\b",
        r"\bextraction\b",
        r"\bedibles?\b",
        r"\bconcentrates?\b",
    ]

    def parse(self, text: str, metadata: Optional[dict] = None) -> ExtractionResult:
        """Extract structured data from text."""
        text_lower = text.lower()
        result = ExtractionResult()

        # Extract business model
        bm_scores: dict[str, float] = {}
        for model, patterns in self.BUSINESS_MODEL_PATTERNS.items():
            score = self._count_pattern_matches(text_lower, patterns)
            if score > 0:
                bm_scores[model] = score

        if bm_scores:
            best_model = max(bm_scores.keys(), key=lambda k: bm_scores[k])
            result.business_model = best_model
            result.business_model_confidence = min(bm_scores[best_model] / 3.0, 1.0)

        # Extract customer types
        for ctype, patterns in self.CUSTOMER_TYPE_PATTERNS.items():
            if self._has_pattern_match(text_lower, patterns):
                result.customer_types.append(ctype)

        # Extract employee count
        for pattern in self.EMPLOYEE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    result.employee_count = int(match.group(1))
                    result.evidence["employee_count"] = match.group(0)
                    break
                except (ValueError, IndexError):
                    continue

        # Extract revenue
        for pattern in self.REVENUE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    millions = float(match.group(1))
                    result.revenue_estimate = int(millions * 1_000_000)
                    result.evidence["revenue"] = match.group(0)
                    break
                except (ValueError, IndexError):
                    continue

        # Extract funding
        for pattern in self.FUNDING_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    millions = float(match.group(1))
                    result.funding_total = int(millions * 1_000_000)
                    result.evidence["funding"] = match.group(0)
                    break
                except (ValueError, IndexError):
                    continue

        # Check compliance indicators
        for indicator, patterns in self.COMPLIANCE_PATTERNS.items():
            if self._has_pattern_match(text_lower, patterns):
                result.compliance_indicators.append(indicator)

        # Check positive signals
        for signal, patterns in self.SIGNAL_PATTERNS.items():
            if self._has_pattern_match(text_lower, patterns):
                result.signals.append(signal)

        # Check cannabis industry indicators
        cannabis_matches = 0
        for pattern in self.CANNABIS_INDICATORS:
            matches = len(re.findall(pattern, text_lower, re.I))
            cannabis_matches += matches
        if cannabis_matches > 0:
            result.is_cannabis_industry = True
            result.cannabis_confidence = min(cannabis_matches / 5.0, 1.0)
            result.industries.append("cannabis software")

        # Check software revenue indicators
        software_score = 0
        for pattern in self.SOFTWARE_INDICATORS:
            if re.search(pattern, text_lower, re.I):
                software_score += 1
                result.software_indicators_found.append(pattern)

        services_score = 0
        for pattern in self.SERVICES_INDICATORS:
            if re.search(pattern, text_lower, re.I):
                services_score += 1
                result.services_indicators_found.append(pattern)

        # Calculate software revenue confidence (higher software indicators, lower services = higher confidence)
        if software_score > 0:
            # Base confidence from software indicators
            base_confidence = min(software_score / 8.0, 0.8)
            # Penalty for services indicators
            services_penalty = min(services_score * 0.15, 0.5)
            result.software_revenue_confidence = max(0, base_confidence - services_penalty)
        else:
            result.software_revenue_confidence = 0.0

        # ARR estimation heuristic: if no revenue found but employee count exists
        # Estimate ARR = employee_count * $1,000,000
        if result.revenue_estimate is None and result.employee_count is not None:
            result.revenue_estimate = result.employee_count * 1_000_000
            result.revenue_is_estimated = True
            result.evidence["revenue"] = f"Estimated from {result.employee_count} employees"

        # Calculate overall confidence
        confidence_factors = [
            0.3 if result.business_model else 0.0,
            0.2 if result.customer_types else 0.0,
            0.15 if result.employee_count else 0.0,
            0.15 if result.revenue_estimate or result.funding_total else 0.0,
            0.1 if result.compliance_indicators else 0.0,
            0.1 if result.signals else 0.0,
        ]
        result.overall_confidence = sum(confidence_factors)

        return result

    def _count_pattern_matches(self, text: str, patterns: list[str]) -> int:
        """Count total matches for a list of patterns."""
        count = 0
        for pattern in patterns:
            matches = re.findall(pattern, text, re.I)
            count += len(matches)
        return count

    def _has_pattern_match(self, text: str, patterns: list[str]) -> bool:
        """Check if any pattern matches."""
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                return True
        return False

    def extract_keywords(self, text: str, industry_keywords: list[str]) -> list[str]:
        """Extract matching industry keywords from text."""
        text_lower = text.lower()
        found = []

        for keyword in industry_keywords:
            pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
            if re.search(pattern, text_lower):
                found.append(keyword)

        return found

    def detect_disqualifiers(
        self,
        text: str,
        disqualifier_patterns: list[str],
    ) -> list[str]:
        """Detect disqualifying conditions in text."""
        text_lower = text.lower()
        found = []

        for pattern in disqualifier_patterns:
            if re.search(pattern, text_lower, re.I):
                found.append(pattern)

        return found
