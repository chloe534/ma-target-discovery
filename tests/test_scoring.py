"""Tests for scoring functionality."""

import pytest
from datetime import datetime

from app.models import AcquisitionCriteria, EnrichedCompany, Evidence
from app.score.scorer import Scorer


def make_criteria(**kwargs) -> AcquisitionCriteria:
    """Create test criteria with defaults."""
    defaults = {
        "industries_include": ["healthcare tech"],
        "keywords_include": ["SaaS", "B2B"],
        "business_model": {"types": ["SaaS"]},
        "customer_type": ["B2B"],
        "weights": {
            "industry": 0.25,
            "business_model": 0.25,
            "customer_type": 0.25,
            "keyword": 0.25,
        },
    }
    defaults.update(kwargs)
    return AcquisitionCriteria(**defaults)


def make_company(**kwargs) -> EnrichedCompany:
    """Create test enriched company with defaults."""
    defaults = {
        "name": "Test Company",
        "domain": "testcompany.com",
        "source": "test",
        "discovered_at": datetime.utcnow(),
        "business_model": "SaaS",
        "business_model_confidence": 0.8,
        "customer_types": ["B2B"],
        "industries": ["healthcare tech"],
    }
    defaults.update(kwargs)
    return EnrichedCompany(**defaults)


class TestScorer:
    """Tests for the scoring engine."""

    def test_score_perfect_match(self):
        scorer = Scorer()
        criteria = make_criteria()
        company = make_company(
            business_model="SaaS",
            business_model_confidence=0.9,
            customer_types=["B2B"],
            industries=["healthcare tech"],
        )
        result = scorer.score(company, criteria)
        assert result.fit_score > 70  # Good match but not all criteria have evidence
        assert not result.is_disqualified

    def test_score_no_match(self):
        scorer = Scorer()
        criteria = make_criteria()
        company = make_company(
            business_model="services",
            business_model_confidence=0.9,
            customer_types=["B2C"],
            industries=["retail"],
        )
        result = scorer.score(company, criteria)
        assert result.fit_score < 30

    def test_score_partial_match(self):
        scorer = Scorer()
        criteria = make_criteria()
        company = make_company(
            business_model="SaaS",
            business_model_confidence=0.9,
            customer_types=["B2C"],  # Doesn't match
            industries=["healthcare tech"],
        )
        result = scorer.score(company, criteria)
        assert 30 < result.fit_score < 80

    def test_score_disqualified(self):
        scorer = Scorer()
        criteria = make_criteria(dealbreakers=["gambling"])
        company = make_company(disqualifiers_detected=["gambling"])
        result = scorer.score(company, criteria)
        assert result.is_disqualified
        assert result.fit_score == 0
        assert "gambling" in str(result.disqualification_reasons)

    def test_score_excluded_industry(self):
        scorer = Scorer()
        criteria = make_criteria(industries_exclude=["gambling"])
        company = make_company(industries=["gambling"])
        result = scorer.score(company, criteria)
        assert result.is_disqualified

    def test_score_excluded_business_model(self):
        scorer = Scorer()
        criteria = make_criteria(
            business_model={"types": ["SaaS"], "exclude_types": ["services"]}
        )
        company = make_company(business_model="services")
        result = scorer.score(company, criteria)
        assert result.is_disqualified

    def test_score_generates_summary(self):
        scorer = Scorer()
        criteria = make_criteria()
        company = make_company()
        result = scorer.score(company, criteria)
        assert len(result.match_summary) > 0

    def test_score_breakdown(self):
        scorer = Scorer()
        criteria = make_criteria()
        company = make_company()
        result = scorer.score(company, criteria)
        assert "industry" in result.score_breakdown
        assert "business_model" in result.score_breakdown
        assert "customer_type" in result.score_breakdown

    def test_rank_companies(self):
        scorer = Scorer()
        criteria = make_criteria()
        companies = [
            make_company(name="Low Match", business_model="services", industries=["other"]),
            make_company(name="High Match", business_model="SaaS", industries=["healthcare tech"]),
            make_company(name="Medium Match", business_model="SaaS", industries=["other"]),
        ]
        results = scorer.score_and_rank(companies, criteria)
        assert results[0].name == "High Match"
        assert results[0].rank == 1
        assert results[-1].name == "Low Match"
        assert results[-1].rank == 3

    def test_confidence_calculation(self):
        scorer = Scorer()
        criteria = make_criteria()

        # Company with lots of data
        rich_company = make_company(
            business_model="SaaS",
            business_model_confidence=0.9,
            customer_types=["B2B"],
            industries=["healthcare tech"],
            employees_estimate=50,
            headquarters="San Francisco, CA",
            extraction_confidence=0.8,
        )

        # Company with minimal data
        sparse_company = make_company(
            business_model=None,
            business_model_confidence=0.0,
            customer_types=[],
            industries=[],
        )

        rich_result = scorer.score(rich_company, criteria)
        sparse_result = scorer.score(sparse_company, criteria)

        assert rich_result.confidence > sparse_result.confidence


class TestScorerWeights:
    """Tests for weighted scoring."""

    def test_custom_weights(self):
        scorer = Scorer()
        # Heavy weight on industry
        criteria = make_criteria(
            weights={
                "industry": 0.8,
                "business_model": 0.1,
                "customer_type": 0.1,
            }
        )
        company = make_company(
            industries=["healthcare tech"],
            business_model="services",  # Doesn't match
            customer_types=["B2C"],  # Doesn't match
        )
        result = scorer.score(company, criteria)
        # Should still score relatively high due to industry match
        assert result.fit_score > 50

    def test_zero_weight_ignored(self):
        scorer = Scorer()
        criteria = make_criteria(
            weights={
                "industry": 1.0,
                "business_model": 0.0,  # Ignored
                "customer_type": 0.0,  # Ignored
            }
        )
        company = make_company(
            industries=["healthcare tech"],
            business_model="wrong",
            customer_types=["wrong"],
        )
        result = scorer.score(company, criteria)
        # Industry matches, high score but other default-weighted criteria affect it
        assert result.fit_score > 85
