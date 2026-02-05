"""OpenCorporates API connector."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx

from app.config import settings
from app.models import AcquisitionCriteria, CandidateCompany
from .base import SourceConnector

logger = logging.getLogger(__name__)


class OpenCorporatesConnector(SourceConnector):
    """Search for companies using OpenCorporates API (free tier)."""

    name = "opencorporates"
    BASE_URL = "https://api.opencorporates.com/v0.4"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.opencorporates_api_key

    def generate_queries(self, criteria: AcquisitionCriteria) -> list[str]:
        """Generate search queries for OpenCorporates."""
        queries = []

        # Use industries as primary search terms
        for industry in criteria.industries_include:
            queries.append(industry)

        # Add keywords
        for keyword in criteria.keywords_include:
            queries.append(keyword)

        return queries[:10]  # Limit due to free tier constraints

    async def search(
        self,
        criteria: AcquisitionCriteria,
        limit: int = 50,
    ) -> list[CandidateCompany]:
        """Search OpenCorporates for companies."""
        queries = self.generate_queries(criteria)
        candidates: dict[str, CandidateCompany] = {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            for query in queries:
                if len(candidates) >= limit:
                    break

                try:
                    results = await self._search_companies(client, query, criteria)
                    for candidate in results:
                        if candidate.domain and candidate.domain not in candidates:
                            candidates[candidate.domain] = candidate
                        elif candidate.name not in [c.name for c in candidates.values()]:
                            # Store by name if no domain
                            candidates[candidate.name] = candidate

                except Exception as e:
                    logger.warning(f"OpenCorporates search failed for '{query}': {e}")
                    continue

                # Rate limiting for free tier
                await asyncio.sleep(1.0)

        return list(candidates.values())[:limit]

    async def _search_companies(
        self,
        client: httpx.AsyncClient,
        query: str,
        criteria: AcquisitionCriteria,
    ) -> list[CandidateCompany]:
        """Execute a company search."""
        params = {
            "q": query,
            "per_page": 30,
            "order": "score",
        }

        # Add jurisdiction filter if geography specified
        if criteria.geography.countries:
            # OpenCorporates uses jurisdiction codes
            params["jurisdiction_code"] = "|".join(
                c.lower() for c in criteria.geography.countries[:5]
            )

        if self.api_key:
            params["api_token"] = self.api_key

        try:
            response = await client.get(
                f"{self.BASE_URL}/companies/search",
                params=params,
            )

            if response.status_code == 401:
                logger.warning("OpenCorporates API key invalid or rate limited")
                return []

            if response.status_code != 200:
                logger.warning(f"OpenCorporates returned {response.status_code}")
                return []

            data = response.json()
            companies = data.get("results", {}).get("companies", [])

            return [
                self._parse_company(c["company"])
                for c in companies
                if c.get("company")
            ]

        except httpx.TimeoutException:
            logger.warning("OpenCorporates request timed out")
            return []

    def _parse_company(self, data: dict) -> CandidateCompany:
        """Parse OpenCorporates company data."""
        name = data.get("name", "Unknown")

        # Try to extract website from data
        website = None
        domain = None

        # OpenCorporates sometimes has website in alternative names or data
        if "registered_address" in data:
            addr = data["registered_address"]
            location = ", ".join(filter(None, [
                addr.get("locality"),
                addr.get("region"),
                addr.get("country"),
            ]))
        else:
            location = data.get("jurisdiction_code", "").upper()

        return CandidateCompany(
            name=name,
            domain=domain,
            website=website,
            description=f"Company registered in {location}" if location else None,
            source=self.name,
            source_url=data.get("opencorporates_url"),
            discovered_at=datetime.utcnow(),
            location=location,
            industry=data.get("industry_codes", [{}])[0].get("description")
            if data.get("industry_codes") else None,
        )
