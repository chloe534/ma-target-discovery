"""Hard filters for pass/fail checks (dealbreakers)."""

import logging
from dataclasses import dataclass

from app.models import AcquisitionCriteria, EnrichedCompany

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Result of applying hard filters."""

    passed: bool
    failed_filters: list[str]
    is_disqualified: bool
    disqualification_reasons: list[str]


class HardFilters:
    """Apply hard pass/fail filters based on criteria."""

    def apply(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> FilterResult:
        """Apply all hard filters to a company."""
        failed_filters = []
        disqualification_reasons = []

        # Check dealbreakers from enrichment
        if company.disqualifiers_detected:
            for dq in company.disqualifiers_detected:
                if dq in criteria.dealbreakers:
                    disqualification_reasons.append(f"Dealbreaker: {dq}")

        # Check excluded industries
        for industry in company.industries:
            if industry.lower() in [i.lower() for i in criteria.industries_exclude]:
                disqualification_reasons.append(f"Excluded industry: {industry}")

        # Check excluded business model
        if company.business_model:
            if company.business_model.lower() in [
                t.lower() for t in criteria.business_model.exclude_types
            ]:
                disqualification_reasons.append(
                    f"Excluded business model: {company.business_model}"
                )

        # Check size constraints
        size_filters = self._check_size_constraints(company, criteria)
        failed_filters.extend(size_filters)

        # Check geography constraints
        geo_filters = self._check_geography_constraints(company, criteria)
        failed_filters.extend(geo_filters)

        # Check recurring revenue requirement
        if criteria.business_model.recurring_revenue_required:
            if company.business_model not in ["SaaS", "subscription"]:
                failed_filters.append("Recurring revenue required but not detected")

        is_disqualified = len(disqualification_reasons) > 0
        passed = not is_disqualified and len(failed_filters) == 0

        return FilterResult(
            passed=passed,
            failed_filters=failed_filters,
            is_disqualified=is_disqualified,
            disqualification_reasons=disqualification_reasons,
        )

    def _check_size_constraints(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> list[str]:
        """Check size-related constraints."""
        failed = []
        size = criteria.size

        # Employee count checks
        if company.employees_estimate:
            if size.employees_min and company.employees_estimate < size.employees_min:
                failed.append(
                    f"Employee count {company.employees_estimate} below minimum {size.employees_min}"
                )
            if size.employees_max and company.employees_estimate > size.employees_max:
                failed.append(
                    f"Employee count {company.employees_estimate} above maximum {size.employees_max}"
                )

        # Revenue checks
        if company.revenue_estimate:
            if size.revenue_min and company.revenue_estimate < size.revenue_min:
                failed.append(
                    f"Revenue ${company.revenue_estimate:,} below minimum ${size.revenue_min:,}"
                )
            if size.revenue_max and company.revenue_estimate > size.revenue_max:
                failed.append(
                    f"Revenue ${company.revenue_estimate:,} above maximum ${size.revenue_max:,}"
                )

        # Funding checks
        if company.funding_total:
            if size.funding_min and company.funding_total < size.funding_min:
                failed.append(
                    f"Funding ${company.funding_total:,} below minimum ${size.funding_min:,}"
                )
            if size.funding_max and company.funding_total > size.funding_max:
                failed.append(
                    f"Funding ${company.funding_total:,} above maximum ${size.funding_max:,}"
                )

        return failed

    def _check_geography_constraints(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> list[str]:
        """Check geography-related constraints."""
        failed = []
        geo = criteria.geography

        if not company.headquarters:
            # Can't verify geography without location data
            return failed

        location = company.headquarters.lower()

        # Check excluded countries
        for country in geo.exclude_countries:
            if country.lower() in location:
                failed.append(f"Company in excluded country: {country}")

        # Check required countries (if any specified)
        if geo.countries:
            country_match = False
            for country in geo.countries:
                if country.lower() in location:
                    country_match = True
                    break
            if not country_match:
                failed.append(
                    f"Company not in required countries: {', '.join(geo.countries)}"
                )

        # Check required regions (if any specified)
        if geo.regions:
            region_match = False
            for region in geo.regions:
                if region.lower() in location:
                    region_match = True
                    break
            if not region_match:
                failed.append(
                    f"Company not in required regions: {', '.join(geo.regions)}"
                )

        return failed


def quick_filter(
    company: EnrichedCompany,
    criteria: AcquisitionCriteria,
) -> bool:
    """Quick check if company passes basic filters (for early filtering)."""
    filters = HardFilters()
    result = filters.apply(company, criteria)
    return result.passed
