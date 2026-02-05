"""Tests for hard filter functionality."""

import pytest
from datetime import datetime

from app.models import AcquisitionCriteria, EnrichedCompany
from app.score.filters import HardFilters, quick_filter


def make_criteria(**kwargs) -> AcquisitionCriteria:
    """Create test criteria with defaults."""
    return AcquisitionCriteria(**kwargs)


def make_company(**kwargs) -> EnrichedCompany:
    """Create test enriched company with defaults."""
    defaults = {
        "name": "Test Company",
        "domain": "testcompany.com",
        "source": "test",
        "discovered_at": datetime.utcnow(),
    }
    defaults.update(kwargs)
    return EnrichedCompany(**defaults)


class TestHardFilters:
    """Tests for hard pass/fail filters."""

    def test_passes_with_no_constraints(self):
        filters = HardFilters()
        criteria = make_criteria()
        company = make_company()
        result = filters.apply(company, criteria)
        assert result.passed
        assert not result.is_disqualified

    def test_fails_on_dealbreaker(self):
        filters = HardFilters()
        criteria = make_criteria(dealbreakers=["gambling", "adult"])
        company = make_company(disqualifiers_detected=["gambling"])
        result = filters.apply(company, criteria)
        assert result.is_disqualified
        assert not result.passed
        assert "gambling" in str(result.disqualification_reasons)

    def test_fails_on_excluded_industry(self):
        filters = HardFilters()
        criteria = make_criteria(industries_exclude=["cryptocurrency"])
        company = make_company(industries=["cryptocurrency", "fintech"])
        result = filters.apply(company, criteria)
        assert result.is_disqualified
        assert "cryptocurrency" in str(result.disqualification_reasons)

    def test_fails_on_excluded_business_model(self):
        filters = HardFilters()
        criteria = make_criteria(
            business_model={"types": [], "exclude_types": ["consulting"]}
        )
        company = make_company(business_model="consulting")
        result = filters.apply(company, criteria)
        assert result.is_disqualified

    def test_fails_on_min_employees(self):
        filters = HardFilters()
        criteria = make_criteria(size={"employees_min": 50})
        company = make_company(employees_estimate=25)
        result = filters.apply(company, criteria)
        assert not result.passed
        assert "employee count" in str(result.failed_filters).lower()

    def test_fails_on_max_employees(self):
        filters = HardFilters()
        criteria = make_criteria(size={"employees_max": 100})
        company = make_company(employees_estimate=500)
        result = filters.apply(company, criteria)
        assert not result.passed

    def test_fails_on_min_revenue(self):
        filters = HardFilters()
        criteria = make_criteria(size={"revenue_min": 1_000_000})
        company = make_company(revenue_estimate=500_000)
        result = filters.apply(company, criteria)
        assert not result.passed

    def test_fails_on_max_revenue(self):
        filters = HardFilters()
        criteria = make_criteria(size={"revenue_max": 10_000_000})
        company = make_company(revenue_estimate=50_000_000)
        result = filters.apply(company, criteria)
        assert not result.passed

    def test_passes_within_size_range(self):
        filters = HardFilters()
        criteria = make_criteria(
            size={
                "employees_min": 10,
                "employees_max": 100,
                "revenue_min": 500_000,
                "revenue_max": 10_000_000,
            }
        )
        company = make_company(
            employees_estimate=50,
            revenue_estimate=2_000_000,
        )
        result = filters.apply(company, criteria)
        assert result.passed

    def test_fails_on_excluded_country(self):
        filters = HardFilters()
        criteria = make_criteria(
            geography={"exclude_countries": ["China", "Russia"]}
        )
        company = make_company(headquarters="Beijing, China")
        result = filters.apply(company, criteria)
        assert not result.passed
        assert "excluded country" in str(result.failed_filters).lower()

    def test_fails_on_required_country(self):
        filters = HardFilters()
        criteria = make_criteria(
            geography={"countries": ["US", "UK"]}
        )
        company = make_company(headquarters="Berlin, Germany")
        result = filters.apply(company, criteria)
        assert not result.passed

    def test_passes_on_required_country(self):
        filters = HardFilters()
        criteria = make_criteria(
            geography={"countries": ["US", "UK"]}
        )
        company = make_company(headquarters="New York, US")
        result = filters.apply(company, criteria)
        assert result.passed

    def test_fails_on_recurring_revenue_requirement(self):
        filters = HardFilters()
        criteria = make_criteria(
            business_model={"types": [], "recurring_revenue_required": True}
        )
        company = make_company(business_model="services")
        result = filters.apply(company, criteria)
        assert not result.passed

    def test_passes_recurring_revenue_for_saas(self):
        filters = HardFilters()
        criteria = make_criteria(
            business_model={"types": [], "recurring_revenue_required": True}
        )
        company = make_company(business_model="SaaS")
        result = filters.apply(company, criteria)
        # SaaS counts as recurring revenue
        assert result.passed


class TestQuickFilter:
    """Tests for the quick_filter helper function."""

    def test_quick_filter_pass(self):
        criteria = make_criteria()
        company = make_company()
        assert quick_filter(company, criteria) is True

    def test_quick_filter_fail(self):
        criteria = make_criteria(dealbreakers=["gambling"])
        company = make_company(disqualifiers_detected=["gambling"])
        assert quick_filter(company, criteria) is False
