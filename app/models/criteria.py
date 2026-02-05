"""Acquisition Criteria Profile schema."""

from typing import Optional
from pydantic import BaseModel, Field


class GeographyFilter(BaseModel):
    """Geographic constraints for target companies."""

    countries: list[str] = Field(default_factory=list, description="ISO country codes to include")
    regions: list[str] = Field(default_factory=list, description="Regions/states to include")
    exclude_countries: list[str] = Field(default_factory=list, description="ISO country codes to exclude")
    headquarters_only: bool = Field(default=False, description="Only match HQ location, not offices")


class SizeConstraints(BaseModel):
    """Size constraints for target companies."""

    revenue_min: Optional[int] = Field(default=None, description="Minimum annual revenue in USD")
    revenue_max: Optional[int] = Field(default=None, description="Maximum annual revenue in USD")
    employees_min: Optional[int] = Field(default=None, description="Minimum employee count")
    employees_max: Optional[int] = Field(default=None, description="Maximum employee count")
    funding_min: Optional[int] = Field(default=None, description="Minimum total funding in USD")
    funding_max: Optional[int] = Field(default=None, description="Maximum total funding in USD")


class BusinessModelFilter(BaseModel):
    """Business model constraints."""

    types: list[str] = Field(
        default_factory=list,
        description="Business model types: SaaS, marketplace, services, hardware, etc."
    )
    exclude_types: list[str] = Field(default_factory=list, description="Business models to exclude")
    recurring_revenue_required: bool = Field(default=False, description="Require recurring revenue model")


class AcquisitionCriteria(BaseModel):
    """Complete acquisition criteria profile for target discovery."""

    # Industry targeting
    industries_include: list[str] = Field(
        default_factory=list,
        description="Industries to search (e.g., 'healthcare tech', 'fintech')"
    )
    industries_exclude: list[str] = Field(
        default_factory=list,
        description="Industries to exclude (e.g., 'gambling', 'adult')"
    )

    # Keyword targeting
    keywords_include: list[str] = Field(
        default_factory=list,
        description="Keywords that indicate good fit"
    )
    keywords_exclude: list[str] = Field(
        default_factory=list,
        description="Keywords that indicate poor fit"
    )

    # Filters
    geography: GeographyFilter = Field(default_factory=GeographyFilter)
    size: SizeConstraints = Field(default_factory=SizeConstraints)
    business_model: BusinessModelFilter = Field(default_factory=BusinessModelFilter)

    # Customer profile
    customer_type: list[str] = Field(
        default_factory=list,
        description="Target customer types: B2B, B2C, enterprise, SMB, etc."
    )

    # Compliance and signals
    compliance_tags: list[str] = Field(
        default_factory=list,
        description="Required compliance: SOC2, HIPAA, GDPR, etc."
    )
    preferred_signals: list[str] = Field(
        default_factory=list,
        description="Positive signals: 'growing team', 'recent funding', etc."
    )

    # Scoring configuration
    disqualifiers: list[str] = Field(
        default_factory=list,
        description="Conditions that disqualify a target"
    )
    dealbreakers: list[str] = Field(
        default_factory=list,
        description="Hard dealbreakers (instant fail)"
    )
    weights: dict[str, float] = Field(
        default_factory=dict,
        description="Criterion weights for scoring (criterion name -> weight 0-1)"
    )

    def get_weight(self, criterion: str, default: float = 0.5) -> float:
        """Get weight for a criterion, returning default if not specified."""
        return self.weights.get(criterion, default)
