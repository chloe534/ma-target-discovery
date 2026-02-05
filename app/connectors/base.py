"""Abstract base class for source connectors."""

from abc import ABC, abstractmethod
from typing import Optional

from app.models import AcquisitionCriteria, CandidateCompany


class SourceConnector(ABC):
    """Abstract interface for company discovery sources."""

    name: str = "base"

    @abstractmethod
    async def search(
        self,
        criteria: AcquisitionCriteria,
        limit: int = 50,
    ) -> list[CandidateCompany]:
        """
        Search for candidate companies matching the criteria.

        Args:
            criteria: The acquisition criteria to match against
            limit: Maximum number of results to return

        Returns:
            List of candidate companies found
        """
        pass

    @abstractmethod
    def generate_queries(self, criteria: AcquisitionCriteria) -> list[str]:
        """
        Generate search queries from acquisition criteria.

        Args:
            criteria: The acquisition criteria

        Returns:
            List of search query strings
        """
        pass

    def _build_industry_queries(self, criteria: AcquisitionCriteria) -> list[str]:
        """Build queries from industry targeting."""
        queries = []
        for industry in criteria.industries_include:
            base_query = f"{industry} company"
            if criteria.geography.countries:
                for country in criteria.geography.countries[:3]:
                    queries.append(f"{base_query} {country}")
            else:
                queries.append(base_query)
        return queries

    def _build_keyword_queries(self, criteria: AcquisitionCriteria) -> list[str]:
        """Build queries from keyword targeting."""
        queries = []
        for keyword in criteria.keywords_include:
            if criteria.business_model.types:
                for bm in criteria.business_model.types[:2]:
                    queries.append(f"{keyword} {bm}")
            else:
                queries.append(f"{keyword} startup")
        return queries

    @staticmethod
    def normalize_domain(url: Optional[str]) -> Optional[str]:
        """Normalize a URL to its domain."""
        if not url:
            return None
        # Remove protocol
        domain = url.lower()
        for prefix in ["https://", "http://", "www."]:
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        # Remove path and trailing slash
        domain = domain.split("/")[0].rstrip("/")
        return domain if domain else None
