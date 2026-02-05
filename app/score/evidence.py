"""Evidence extraction and mapping for scoring."""

import logging
import re
from typing import Optional

from app.models import AcquisitionCriteria, EnrichedCompany, Evidence

logger = logging.getLogger(__name__)


class EvidenceExtractor:
    """Extract evidence snippets supporting criterion matches."""

    # Maximum snippet length
    MAX_SNIPPET_LENGTH = 200

    def extract_evidence(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
    ) -> list[Evidence]:
        """Extract evidence for all criteria matches."""
        evidence_list = []

        # Combine all page contents
        all_content = "\n".join(company.page_contents.values())

        # Extract evidence for each criterion type
        evidence_list.extend(
            self._extract_industry_evidence(company, criteria, all_content)
        )
        evidence_list.extend(
            self._extract_keyword_evidence(company, criteria, all_content)
        )
        evidence_list.extend(
            self._extract_business_model_evidence(company, criteria, all_content)
        )
        evidence_list.extend(
            self._extract_customer_type_evidence(company, criteria, all_content)
        )
        evidence_list.extend(
            self._extract_compliance_evidence(company, criteria, all_content)
        )
        evidence_list.extend(
            self._extract_signal_evidence(company, criteria, all_content)
        )

        return evidence_list

    def _extract_industry_evidence(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
        content: str,
    ) -> list[Evidence]:
        """Extract evidence for industry matches."""
        evidence = []

        for industry in criteria.industries_include:
            if industry.lower() in [i.lower() for i in company.industries]:
                snippet, source_url = self._find_snippet(
                    content, industry, company.page_contents
                )
                if snippet:
                    evidence.append(Evidence(
                        criterion=f"industry:{industry}",
                        snippet=snippet,
                        source_url=source_url or company.website or "",
                        confidence=0.8,
                        extraction_method="keyword",
                    ))

        return evidence

    def _extract_keyword_evidence(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
        content: str,
    ) -> list[Evidence]:
        """Extract evidence for keyword matches."""
        evidence = []

        for keyword in criteria.keywords_include:
            snippet, source_url = self._find_snippet(
                content, keyword, company.page_contents
            )
            if snippet:
                evidence.append(Evidence(
                    criterion=f"keyword:{keyword}",
                    snippet=snippet,
                    source_url=source_url or company.website or "",
                    confidence=0.7,
                    extraction_method="keyword",
                ))

        return evidence

    def _extract_business_model_evidence(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
        content: str,
    ) -> list[Evidence]:
        """Extract evidence for business model match."""
        evidence = []

        if not company.business_model:
            return evidence

        # Check if business model matches criteria
        if criteria.business_model.types:
            if company.business_model.lower() not in [
                t.lower() for t in criteria.business_model.types
            ]:
                return evidence

        # Find evidence for the business model
        bm_keywords = {
            "SaaS": ["subscription", "monthly", "cloud", "saas", "software as a service"],
            "marketplace": ["marketplace", "platform", "connect", "buyers", "sellers"],
            "services": ["consulting", "services", "agency", "professional"],
            "hardware": ["device", "hardware", "physical", "manufacturing"],
            "e-commerce": ["shop", "store", "buy", "commerce", "retail"],
        }

        keywords = bm_keywords.get(company.business_model, [company.business_model.lower()])

        for keyword in keywords:
            snippet, source_url = self._find_snippet(
                content, keyword, company.page_contents
            )
            if snippet:
                evidence.append(Evidence(
                    criterion=f"business_model:{company.business_model}",
                    snippet=snippet,
                    source_url=source_url or company.website or "",
                    confidence=company.business_model_confidence,
                    extraction_method="keyword",
                ))
                break

        return evidence

    def _extract_customer_type_evidence(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
        content: str,
    ) -> list[Evidence]:
        """Extract evidence for customer type matches."""
        evidence = []

        customer_keywords = {
            "B2B": ["business", "enterprise", "company", "organization", "b2b"],
            "B2C": ["consumer", "individual", "personal", "b2c"],
            "enterprise": ["enterprise", "fortune 500", "large organization"],
            "SMB": ["small business", "smb", "growing business"],
        }

        for ctype in criteria.customer_type:
            if ctype in company.customer_types:
                keywords = customer_keywords.get(ctype, [ctype.lower()])
                for keyword in keywords:
                    snippet, source_url = self._find_snippet(
                        content, keyword, company.page_contents
                    )
                    if snippet:
                        evidence.append(Evidence(
                            criterion=f"customer_type:{ctype}",
                            snippet=snippet,
                            source_url=source_url or company.website or "",
                            confidence=0.7,
                            extraction_method="keyword",
                        ))
                        break

        return evidence

    def _extract_compliance_evidence(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
        content: str,
    ) -> list[Evidence]:
        """Extract evidence for compliance indicators."""
        evidence = []

        for compliance in criteria.compliance_tags:
            if compliance in company.compliance_indicators:
                snippet, source_url = self._find_snippet(
                    content, compliance, company.page_contents
                )
                if snippet:
                    evidence.append(Evidence(
                        criterion=f"compliance:{compliance}",
                        snippet=snippet,
                        source_url=source_url or company.website or "",
                        confidence=0.9,
                        extraction_method="keyword",
                    ))

        return evidence

    def _extract_signal_evidence(
        self,
        company: EnrichedCompany,
        criteria: AcquisitionCriteria,
        content: str,
    ) -> list[Evidence]:
        """Extract evidence for preferred signals."""
        evidence = []

        signal_keywords = {
            "growing_team": ["hiring", "join our team", "careers", "open positions"],
            "recent_funding": ["raised", "funding", "series", "investment"],
            "product_launch": ["launched", "announcing", "introducing", "new product"],
            "customer_growth": ["customers", "users", "clients", "trusted by"],
        }

        for signal in criteria.preferred_signals:
            if signal in company.signals_detected:
                keywords = signal_keywords.get(signal, [signal.replace("_", " ")])
                for keyword in keywords:
                    snippet, source_url = self._find_snippet(
                        content, keyword, company.page_contents
                    )
                    if snippet:
                        evidence.append(Evidence(
                            criterion=f"signal:{signal}",
                            snippet=snippet,
                            source_url=source_url or company.website or "",
                            confidence=0.6,
                            extraction_method="keyword",
                        ))
                        break

        return evidence

    def _find_snippet(
        self,
        content: str,
        keyword: str,
        page_contents: dict[str, str],
    ) -> tuple[Optional[str], Optional[str]]:
        """Find a text snippet containing the keyword and its source URL."""
        content_lower = content.lower()
        keyword_lower = keyword.lower()

        # Find keyword in content
        pattern = r"\b" + re.escape(keyword_lower) + r"\b"
        match = re.search(pattern, content_lower)

        if not match:
            return None, None

        # Extract surrounding context
        start = max(0, match.start() - 80)
        end = min(len(content), match.end() + 80)

        snippet = content[start:end].strip()

        # Clean up snippet
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        # Truncate if too long
        if len(snippet) > self.MAX_SNIPPET_LENGTH:
            snippet = snippet[:self.MAX_SNIPPET_LENGTH] + "..."

        # Try to find which page the snippet came from
        source_url = None
        for url, page_content in page_contents.items():
            if keyword_lower in page_content.lower():
                source_url = url
                break

        return snippet, source_url
