"""Data models for M&A Target Discovery."""

from .criteria import (
    AcquisitionCriteria,
    GeographyFilter,
    SizeConstraints,
    BusinessModelFilter,
)
from .candidate import (
    CandidateCompany,
    EnrichedCompany,
    ScoredCompany,
    Evidence,
)

__all__ = [
    "AcquisitionCriteria",
    "GeographyFilter",
    "SizeConstraints",
    "BusinessModelFilter",
    "CandidateCompany",
    "EnrichedCompany",
    "ScoredCompany",
    "Evidence",
]
