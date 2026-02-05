"""Scoring engine for ranking M&A targets."""

import logging
from typing import Optional

from app.models import AcquisitionCriteria, EnrichedCompany, ScoredCompany, Evidence
from .filters import HardFilters, FilterResult
from .evidence import EvidenceExtractor

logger = logging.getLogger(__name__)


class Scorer:
    """Score and rank enriched companies against acquisition criteria."""

    # Default weights for criteria if not specified
    DEFAULT_WEIGHTS = {
        "industry": 0.2,
        "keyword": 0.15,
        "business_model": 0.2,
        "customer_type": 0.15,
        "geography": 0.1,
        "size": 0.1,
        "compliance": 0.05,
        "signals": 0.05,
    }

    def __init__(self):
        self.filters = HardFilters()
        self.evidence_extractor = EvidenceExtractor()

    def score(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> ScoredCompany:
        """Score a company against acquisition criteria."""
        # Apply hard filters first
        filter_result = self.filters.apply(company, criteria)

        # Extract evidence
        evidence = self.evidence_extractor.extract_evidence(company, criteria)

        # Calculate scores per criterion
        score_breakdown = self._calculate_scores(company, criteria, evidence)

        # Calculate weighted fit score
        fit_score = self._calculate_fit_score(score_breakdown, criteria)

        # Calculate confidence based on evidence coverage
        confidence = self._calculate_confidence(company, evidence, criteria)

        # Generate match summary
        match_summary = self._generate_summary(company, criteria, evidence, score_breakdown)

        # Create scored company
        scored = ScoredCompany(
            **company.model_dump(),
            fit_score=fit_score,
            confidence=confidence,
            passed_filters=filter_result.passed,
            failed_filters=filter_result.failed_filters,
            is_disqualified=filter_result.is_disqualified,
            disqualification_reasons=filter_result.disqualification_reasons,
            evidence=evidence,
            match_summary=match_summary,
            score_breakdown=score_breakdown,
        )

        # Set score to 0 if disqualified
        if scored.is_disqualified:
            scored.fit_score = 0.0

        return scored

    def score_and_rank(
        self,
        companies: list[EnrichedCompany],
        criteria: AcquisitionCriteria,
    ) -> list[ScoredCompany]:
        """Score all companies and return ranked list."""
        scored = [self.score(company, criteria) for company in companies]

        # Sort by fit_score descending, then by confidence
        scored.sort(key=lambda c: (c.fit_score, c.confidence), reverse=True)

        # Assign ranks
        for i, company in enumerate(scored):
            company.rank = i + 1

        return scored

    def _calculate_scores(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
        evidence: list[Evidence],
    ) -> dict[str, float]:
        """Calculate score for each criterion category."""
        scores = {}

        # Industry match score - boost for cannabis if cannabis keywords in criteria
        industry_score = self._score_industry(company, criteria)
        if company.is_cannabis_industry:
            # Check if cannabis is in criteria
            cannabis_in_criteria = any(
                "cannabis" in ind.lower()
                for ind in criteria.industries_include
            )
            if cannabis_in_criteria:
                # Give cannabis companies a significant boost
                industry_score = max(industry_score, company.cannabis_confidence)
        scores["industry"] = industry_score

        # Keyword match score
        scores["keyword"] = self._score_keywords(company, criteria, evidence)

        # Business model score - factor in software revenue confidence
        bm_score = self._score_business_model(company, criteria)
        # Boost if high software revenue confidence
        if company.software_revenue_confidence > 0.5:
            bm_score = max(bm_score, company.software_revenue_confidence)
        scores["business_model"] = bm_score

        # Customer type score
        scores["customer_type"] = self._score_customer_type(company, criteria)

        # Geography score
        scores["geography"] = self._score_geography(company, criteria)

        # Size score
        scores["size"] = self._score_size(company, criteria)

        # Compliance score
        scores["compliance"] = self._score_compliance(company, criteria)

        # Signals score
        scores["signals"] = self._score_signals(company, criteria)

        return scores

    def _score_industry(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> float:
        """Score industry match."""
        if not criteria.industries_include:
            return 1.0  # No requirement

        if not company.industries:
            return 0.0

        matches = sum(
            1 for ind in company.industries
            if ind.lower() in [i.lower() for i in criteria.industries_include]
        )

        return min(matches / len(criteria.industries_include), 1.0)

    def _score_keywords(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
        evidence: list[Evidence],
    ) -> float:
        """Score keyword matches."""
        if not criteria.keywords_include:
            return 1.0

        # Count keyword evidence
        keyword_evidence = [e for e in evidence if e.criterion.startswith("keyword:")]
        matches = len(set(e.criterion for e in keyword_evidence))

        return min(matches / len(criteria.keywords_include), 1.0)

    def _score_business_model(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> float:
        """Score business model match."""
        if not criteria.business_model.types:
            return 1.0

        if not company.business_model:
            return 0.0

        if company.business_model.lower() in [t.lower() for t in criteria.business_model.types]:
            return company.business_model_confidence
        return 0.0

    def _score_customer_type(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> float:
        """Score customer type match."""
        if not criteria.customer_type:
            return 1.0

        if not company.customer_types:
            return 0.0

        matches = sum(
            1 for ct in company.customer_types
            if ct in criteria.customer_type
        )

        return min(matches / len(criteria.customer_type), 1.0)

    def _score_geography(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> float:
        """Score geography match."""
        if not criteria.geography.countries and not criteria.geography.regions:
            return 1.0

        if not company.headquarters:
            return 0.5  # Unknown, give partial credit

        location = company.headquarters.lower()

        # Check countries
        if criteria.geography.countries:
            for country in criteria.geography.countries:
                if country.lower() in location:
                    return 1.0
            return 0.0

        # Check regions
        if criteria.geography.regions:
            for region in criteria.geography.regions:
                if region.lower() in location:
                    return 1.0
            return 0.0

        return 0.5

    def _score_size(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> float:
        """Score size constraints match."""
        size = criteria.size
        scores = []

        # Employee count
        if size.employees_min or size.employees_max:
            if company.employees_estimate:
                in_range = True
                if size.employees_min and company.employees_estimate < size.employees_min:
                    in_range = False
                if size.employees_max and company.employees_estimate > size.employees_max:
                    in_range = False
                scores.append(1.0 if in_range else 0.0)
            else:
                scores.append(0.5)  # Unknown

        # Revenue
        if size.revenue_min or size.revenue_max:
            if company.revenue_estimate:
                in_range = True
                if size.revenue_min and company.revenue_estimate < size.revenue_min:
                    in_range = False
                if size.revenue_max and company.revenue_estimate > size.revenue_max:
                    in_range = False
                scores.append(1.0 if in_range else 0.0)
            else:
                scores.append(0.5)

        # Funding
        if size.funding_min or size.funding_max:
            if company.funding_total:
                in_range = True
                if size.funding_min and company.funding_total < size.funding_min:
                    in_range = False
                if size.funding_max and company.funding_total > size.funding_max:
                    in_range = False
                scores.append(1.0 if in_range else 0.0)
            else:
                scores.append(0.5)

        if not scores:
            return 1.0  # No size requirements

        return sum(scores) / len(scores)

    def _score_compliance(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> float:
        """Score compliance requirements."""
        if not criteria.compliance_tags:
            return 1.0

        if not company.compliance_indicators:
            return 0.0

        matches = sum(
            1 for tag in criteria.compliance_tags
            if tag in company.compliance_indicators
        )

        return matches / len(criteria.compliance_tags)

    def _score_signals(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> float:
        """Score preferred signals."""
        if not criteria.preferred_signals:
            return 1.0

        if not company.signals_detected:
            return 0.0

        matches = sum(
            1 for signal in criteria.preferred_signals
            if signal in company.signals_detected
        )

        return matches / len(criteria.preferred_signals)

    def _calculate_fit_score(
        self,
        score_breakdown: dict[str, float],
        criteria: AcquisitionCriteria,
    ) -> float:
        """Calculate weighted fit score (0-100)."""
        total_weight = 0.0
        weighted_sum = 0.0

        for criterion, score in score_breakdown.items():
            weight = criteria.get_weight(criterion, self.DEFAULT_WEIGHTS.get(criterion, 0.5))
            weighted_sum += score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        # Normalize to 0-100
        return (weighted_sum / total_weight) * 100

    def _calculate_confidence(
        self,
        company: EnrichedCompany,
        evidence: list[Evidence],
        criteria: AcquisitionCriteria,
    ) -> float:
        """Calculate confidence in the score based on evidence coverage."""
        confidence_factors = []

        # Data completeness
        data_fields = [
            company.business_model,
            company.customer_types,
            company.industries,
            company.employees_estimate,
            company.headquarters,
        ]
        data_completeness = sum(1 for f in data_fields if f) / len(data_fields)
        confidence_factors.append(data_completeness)

        # Evidence coverage
        if evidence:
            avg_evidence_confidence = sum(e.confidence for e in evidence) / len(evidence)
            confidence_factors.append(avg_evidence_confidence)
        else:
            confidence_factors.append(0.3)

        # Business model confidence
        if company.business_model:
            confidence_factors.append(company.business_model_confidence)

        # Extraction confidence
        if company.extraction_confidence > 0:
            confidence_factors.append(company.extraction_confidence)

        return sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.0

    def _generate_summary(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
        evidence: list[Evidence],
        score_breakdown: dict[str, float],
    ) -> list[str]:
        """Generate human-readable match summary bullets."""
        summary = []

        # Cannabis industry highlight (priority)
        if company.is_cannabis_industry:
            conf = int(company.cannabis_confidence * 100)
            summary.append(f"CANNABIS SOFTWARE ({conf}% confidence)")

        # ARR/Revenue information
        if company.revenue_estimate:
            arr_millions = company.revenue_estimate / 1_000_000
            if company.revenue_is_estimated:
                summary.append(f"Estimated ARR: ${arr_millions:.0f}M (from employee count)")
            else:
                summary.append(f"ARR: ${arr_millions:.0f}M")

        # Software revenue confidence
        if company.software_revenue_confidence > 0.3:
            conf = int(company.software_revenue_confidence * 100)
            summary.append(f"Software revenue indicators: {conf}% confidence")

        # Business model
        if company.business_model and score_breakdown.get("business_model", 0) > 0.5:
            summary.append(f"{company.business_model} business model")

        # Industry matches
        matched_industries = [
            ind for ind in company.industries
            if ind.lower() in [i.lower() for i in criteria.industries_include]
        ]
        if matched_industries and not company.is_cannabis_industry:
            summary.append(f"Industry: {', '.join(matched_industries[:3])}")

        # Size/scale
        if company.employees_estimate:
            summary.append(f"Team size: ~{company.employees_estimate} employees")

        # Customer type
        matched_customers = [
            ct for ct in company.customer_types
            if ct in criteria.customer_type
        ]
        if matched_customers:
            summary.append(f"Customer focus: {', '.join(matched_customers)}")

        # Positive signals
        matched_signals = [
            s for s in company.signals_detected
            if s in criteria.preferred_signals
        ]
        if matched_signals:
            signal_labels = [s.replace("_", " ") for s in matched_signals]
            summary.append(f"Signals: {', '.join(signal_labels[:3])}")

        if not summary:
            summary.append("Limited match data available")

        return summary[:7]  # Max 7 bullets
