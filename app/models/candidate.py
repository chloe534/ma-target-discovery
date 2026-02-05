"""Candidate company models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


class Evidence(BaseModel):
    """Evidence supporting a criterion match."""

    criterion: str = Field(description="The criterion this evidence supports")
    snippet: str = Field(description="Text snippet containing the evidence")
    source_url: str = Field(description="URL where evidence was found")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this evidence")
    extraction_method: str = Field(description="How evidence was extracted: 'regex', 'keyword', 'llm'")


class CandidateCompany(BaseModel):
    """A company discovered from a source connector."""

    name: str = Field(description="Company name")
    domain: Optional[str] = Field(default=None, description="Primary domain (normalized)")
    website: Optional[str] = Field(default=None, description="Full website URL")
    description: Optional[str] = Field(default=None, description="Brief description from source")
    source: str = Field(description="Source connector that found this company")
    source_url: Optional[str] = Field(default=None, description="URL where company was found")
    discovered_at: datetime = Field(default_factory=datetime.utcnow)

    # Optional initial data from source
    industry: Optional[str] = None
    location: Optional[str] = None
    employee_count: Optional[int] = None


class EnrichedCompany(CandidateCompany):
    """A candidate company enriched with additional data."""

    # Enriched fields
    enriched_at: Optional[datetime] = None
    enrichment_sources: list[str] = Field(default_factory=list)

    # Company details
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    employees_estimate: Optional[int] = None
    revenue_estimate: Optional[int] = None
    funding_total: Optional[int] = None

    # Business classification
    business_model: Optional[str] = None
    business_model_confidence: float = 0.0
    customer_types: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)

    # Compliance and signals
    compliance_indicators: list[str] = Field(default_factory=list)
    signals_detected: list[str] = Field(default_factory=list)
    disqualifiers_detected: list[str] = Field(default_factory=list)

    # Raw data
    page_contents: dict[str, str] = Field(
        default_factory=dict,
        description="URL -> extracted text content"
    )
    extraction_confidence: float = Field(
        default=0.0,
        description="Overall confidence in extracted data"
    )


class ScoredCompany(EnrichedCompany):
    """An enriched company with fit scoring."""

    # Scoring results
    fit_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Overall fit score 0-100")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in the score")
    rank: Optional[int] = None

    # Filtering results
    passed_filters: bool = True
    failed_filters: list[str] = Field(default_factory=list)
    is_disqualified: bool = False
    disqualification_reasons: list[str] = Field(default_factory=list)

    # Evidence
    evidence: list[Evidence] = Field(default_factory=list)
    match_summary: list[str] = Field(
        default_factory=list,
        description="Human-readable bullets explaining why this matches"
    )

    # Scoring breakdown
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Score per criterion"
    )
