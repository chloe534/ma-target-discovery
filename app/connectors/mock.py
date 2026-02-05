"""Mock connector for testing."""

from datetime import datetime
from typing import Optional

from app.models import AcquisitionCriteria, CandidateCompany
from .base import SourceConnector


class MockConnector(SourceConnector):
    """Mock connector that returns predefined test data."""

    name = "mock"

    def __init__(self, companies: Optional[list[CandidateCompany]] = None):
        self._companies = companies or self._default_companies()

    def generate_queries(self, criteria: AcquisitionCriteria) -> list[str]:
        """Generate mock queries."""
        return [f"mock query for {ind}" for ind in criteria.industries_include]

    async def search(
        self,
        criteria: AcquisitionCriteria,
        limit: int = 50,
    ) -> list[CandidateCompany]:
        """Return mock companies."""
        return self._companies[:limit]

    def _default_companies(self) -> list[CandidateCompany]:
        """Generate default test companies."""
        return [
            CandidateCompany(
                name="HealthTech Solutions",
                domain="healthtechsolutions.com",
                website="https://healthtechsolutions.com",
                description="B2B healthcare SaaS platform for patient management",
                source=self.name,
                discovered_at=datetime.utcnow(),
                industry="Healthcare Technology",
                location="San Francisco, CA",
                employee_count=50,
            ),
            CandidateCompany(
                name="FinanceFlow",
                domain="financeflow.io",
                website="https://financeflow.io",
                description="Automated accounting software for SMBs",
                source=self.name,
                discovered_at=datetime.utcnow(),
                industry="Fintech",
                location="New York, NY",
                employee_count=30,
            ),
            CandidateCompany(
                name="DataSync Pro",
                domain="datasyncpro.com",
                website="https://datasyncpro.com",
                description="Enterprise data integration and ETL platform",
                source=self.name,
                discovered_at=datetime.utcnow(),
                industry="Data Infrastructure",
                location="Austin, TX",
                employee_count=75,
            ),
            CandidateCompany(
                name="CloudSecure",
                domain="cloudsecure.io",
                website="https://cloudsecure.io",
                description="Cloud security and compliance automation",
                source=self.name,
                discovered_at=datetime.utcnow(),
                industry="Cybersecurity",
                location="Boston, MA",
                employee_count=100,
            ),
            CandidateCompany(
                name="RetailAI",
                domain="retailai.co",
                website="https://retailai.co",
                description="AI-powered inventory and demand forecasting",
                source=self.name,
                discovered_at=datetime.utcnow(),
                industry="Retail Technology",
                location="Seattle, WA",
                employee_count=45,
            ),
        ]
