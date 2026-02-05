"""DuckDuckGo web search connector."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from duckduckgo_search import DDGS

from app.models import AcquisitionCriteria, CandidateCompany
from .base import SourceConnector

logger = logging.getLogger(__name__)


class DuckDuckGoConnector(SourceConnector):
    """Search for companies using DuckDuckGo."""

    name = "duckduckgo"

    def __init__(self, results_per_query: int = 10):
        self.results_per_query = results_per_query

    def generate_queries(self, criteria: AcquisitionCriteria) -> list[str]:
        """Generate search queries optimized for company discovery."""
        queries = []

        # Industry-based queries
        queries.extend(self._build_industry_queries(criteria))

        # Keyword-based queries
        queries.extend(self._build_keyword_queries(criteria))

        # Business model specific queries
        for bm_type in criteria.business_model.types:
            for industry in criteria.industries_include[:3]:
                queries.append(f"{industry} {bm_type}")

        # Add exclusion terms to queries
        exclusions = " ".join(f"-{term}" for term in criteria.keywords_exclude[:5])

        return [f"{q} {exclusions}".strip() for q in queries[:20]]

    async def search(
        self,
        criteria: AcquisitionCriteria,
        limit: int = 50,
    ) -> list[CandidateCompany]:
        """Search DuckDuckGo for companies matching criteria."""
        queries = self.generate_queries(criteria)
        candidates: dict[str, CandidateCompany] = {}

        for query in queries:
            if len(candidates) >= limit:
                break

            try:
                # Run synchronous DDG search in thread pool
                results = await asyncio.to_thread(
                    self._execute_search, query
                )

                for result in results:
                    candidate = self._parse_result(result, query)
                    if candidate and candidate.domain:
                        # Dedupe by domain
                        if candidate.domain not in candidates:
                            candidates[candidate.domain] = candidate

            except Exception as e:
                logger.warning(f"DuckDuckGo search failed for '{query}': {e}")
                continue

            # Small delay between queries
            await asyncio.sleep(0.5)

        return list(candidates.values())[:limit]

    def _execute_search(self, query: str) -> list[dict]:
        """Execute a DuckDuckGo search (synchronous)."""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(
                    query,
                    max_results=self.results_per_query,
                ))
                return results
        except Exception as e:
            logger.warning(f"DDG search error: {e}")
            return []

    def _parse_result(self, result: dict, query: str) -> Optional[CandidateCompany]:
        """Parse a DuckDuckGo result into a CandidateCompany."""
        try:
            url = result.get("href", "")
            title = result.get("title", "")
            body = result.get("body", "")

            domain = self.normalize_domain(url)
            if not domain:
                return None

            # Skip common non-company domains
            skip_domains = [
                "wikipedia.org", "linkedin.com", "facebook.com",
                "twitter.com", "youtube.com", "github.com",
                "crunchbase.com", "bloomberg.com", "forbes.com",
                "techcrunch.com", "reuters.com", "news.",
            ]
            if any(skip in domain for skip in skip_domains):
                return None

            # Extract company name from title (often "Company Name - Tagline")
            name = title.split(" - ")[0].split(" | ")[0].strip()
            if not name or len(name) < 2:
                name = domain.split(".")[0].title()

            return CandidateCompany(
                name=name,
                domain=domain,
                website=url,
                description=body[:500] if body else None,
                source=self.name,
                source_url=url,
                discovered_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.debug(f"Failed to parse result: {e}")
            return None
