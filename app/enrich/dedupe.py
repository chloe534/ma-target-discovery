"""Domain-based deduplication and normalization."""

import logging
import re
from difflib import SequenceMatcher
from typing import Optional
from urllib.parse import urlparse

from app.models import CandidateCompany

logger = logging.getLogger(__name__)


class Deduplicator:
    """Deduplicate candidate companies by domain and name."""

    def __init__(self, name_similarity_threshold: float = 0.85):
        self.name_similarity_threshold = name_similarity_threshold

    def deduplicate(
        self,
        candidates: list[CandidateCompany],
    ) -> list[CandidateCompany]:
        """Deduplicate candidates by domain and fuzzy name matching."""
        seen_domains: dict[str, CandidateCompany] = {}
        seen_names: dict[str, CandidateCompany] = {}
        result: list[CandidateCompany] = []

        for candidate in candidates:
            # Normalize domain
            if candidate.domain:
                candidate.domain = self.normalize_domain(candidate.domain)

            # Check domain uniqueness
            if candidate.domain:
                if candidate.domain in seen_domains:
                    # Merge data if new candidate has more info
                    existing = seen_domains[candidate.domain]
                    self._merge_candidate(existing, candidate)
                    continue
                seen_domains[candidate.domain] = candidate

            # Check name uniqueness (fuzzy)
            normalized_name = self._normalize_name(candidate.name)
            is_duplicate = False

            for seen_name, existing in seen_names.items():
                if self._names_match(normalized_name, seen_name):
                    # Same company, different source
                    self._merge_candidate(existing, candidate)
                    is_duplicate = True
                    break

            if not is_duplicate:
                seen_names[normalized_name] = candidate
                result.append(candidate)

        return result

    @staticmethod
    def normalize_domain(domain: str) -> str:
        """Normalize a domain name."""
        if not domain:
            return ""

        # Handle full URLs
        if "://" in domain:
            parsed = urlparse(domain)
            domain = parsed.netloc or parsed.path

        domain = domain.lower().strip()

        # Remove www prefix
        if domain.startswith("www."):
            domain = domain[4:]

        # Remove trailing slash and path
        domain = domain.split("/")[0]

        # Remove port
        domain = domain.split(":")[0]

        return domain

    @staticmethod
    def extract_domain(url: Optional[str]) -> Optional[str]:
        """Extract and normalize domain from a URL."""
        if not url:
            return None

        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split("/")[0]
            return Deduplicator.normalize_domain(domain)
        except Exception:
            return None

    def _normalize_name(self, name: str) -> str:
        """Normalize a company name for comparison."""
        name = name.lower().strip()

        # Remove common suffixes
        suffixes = [
            r"\s+(inc\.?|llc|ltd\.?|corp\.?|co\.?|company)$",
            r"\s+(incorporated|limited|corporation)$",
            r",\s+(inc\.?|llc|ltd\.?)$",
        ]
        for suffix in suffixes:
            name = re.sub(suffix, "", name, flags=re.I)

        # Remove special characters
        name = re.sub(r"[^\w\s]", "", name)

        # Normalize whitespace
        name = " ".join(name.split())

        return name

    def _names_match(self, name1: str, name2: str) -> bool:
        """Check if two normalized names refer to the same company."""
        if name1 == name2:
            return True

        # One contains the other
        if name1 in name2 or name2 in name1:
            return True

        # Fuzzy matching
        ratio = SequenceMatcher(None, name1, name2).ratio()
        return ratio >= self.name_similarity_threshold

    def _merge_candidate(
        self,
        existing: CandidateCompany,
        new: CandidateCompany,
    ):
        """Merge data from new candidate into existing."""
        # Prefer non-None values
        if not existing.domain and new.domain:
            existing.domain = new.domain
        if not existing.website and new.website:
            existing.website = new.website
        if not existing.description and new.description:
            existing.description = new.description
        if not existing.industry and new.industry:
            existing.industry = new.industry
        if not existing.location and new.location:
            existing.location = new.location
        if not existing.employee_count and new.employee_count:
            existing.employee_count = new.employee_count
