"""Tests for deduplication functionality."""

import pytest
from datetime import datetime

from app.enrich.dedupe import Deduplicator
from app.models import CandidateCompany


class TestDomainNormalization:
    """Tests for domain normalization."""

    def test_normalize_basic_domain(self):
        deduper = Deduplicator()
        assert deduper.normalize_domain("example.com") == "example.com"

    def test_normalize_www_prefix(self):
        deduper = Deduplicator()
        assert deduper.normalize_domain("www.example.com") == "example.com"

    def test_normalize_https_url(self):
        deduper = Deduplicator()
        assert deduper.normalize_domain("https://www.example.com") == "example.com"

    def test_normalize_http_url(self):
        deduper = Deduplicator()
        assert deduper.normalize_domain("http://example.com") == "example.com"

    def test_normalize_with_path(self):
        deduper = Deduplicator()
        assert deduper.normalize_domain("https://example.com/about") == "example.com"

    def test_normalize_with_port(self):
        deduper = Deduplicator()
        assert deduper.normalize_domain("example.com:8080") == "example.com"

    def test_normalize_trailing_slash(self):
        deduper = Deduplicator()
        assert deduper.normalize_domain("example.com/") == "example.com"

    def test_normalize_uppercase(self):
        deduper = Deduplicator()
        assert deduper.normalize_domain("EXAMPLE.COM") == "example.com"

    def test_normalize_empty(self):
        deduper = Deduplicator()
        assert deduper.normalize_domain("") == ""

    def test_extract_domain_from_url(self):
        assert Deduplicator.extract_domain("https://www.example.com/page") == "example.com"

    def test_extract_domain_none(self):
        assert Deduplicator.extract_domain(None) is None


class TestDeduplication:
    """Tests for company deduplication."""

    def _make_candidate(
        self,
        name: str,
        domain: str = None,
        website: str = None,
    ) -> CandidateCompany:
        return CandidateCompany(
            name=name,
            domain=domain,
            website=website,
            source="test",
            discovered_at=datetime.utcnow(),
        )

    def test_dedupe_by_domain(self):
        deduper = Deduplicator()
        candidates = [
            self._make_candidate("Company A", domain="companya.com"),
            self._make_candidate("Company A Inc", domain="companya.com"),
        ]
        result = deduper.deduplicate(candidates)
        assert len(result) == 1
        assert result[0].name == "Company A"

    def test_dedupe_by_fuzzy_name(self):
        deduper = Deduplicator()
        candidates = [
            self._make_candidate("Acme Corporation"),
            self._make_candidate("Acme Corp"),
        ]
        result = deduper.deduplicate(candidates)
        assert len(result) == 1

    def test_dedupe_preserves_unique(self):
        deduper = Deduplicator()
        candidates = [
            self._make_candidate("Acme Widgets", domain="acmewidgets.com"),
            self._make_candidate("Globex Industries", domain="globexindustries.com"),
            self._make_candidate("Stark Enterprises", domain="starkenterprises.com"),
        ]
        result = deduper.deduplicate(candidates)
        assert len(result) == 3

    def test_dedupe_merges_data(self):
        deduper = Deduplicator()
        candidates = [
            self._make_candidate("Company A", domain="companya.com"),
            CandidateCompany(
                name="Company A Inc",
                domain="companya.com",
                website="https://companya.com",
                description="A great company",
                source="test",
                discovered_at=datetime.utcnow(),
            ),
        ]
        result = deduper.deduplicate(candidates)
        assert len(result) == 1
        assert result[0].website == "https://companya.com"
        assert result[0].description == "A great company"

    def test_dedupe_removes_suffixes(self):
        deduper = Deduplicator()
        candidates = [
            self._make_candidate("Tech Solutions Inc."),
            self._make_candidate("Tech Solutions, LLC"),
        ]
        result = deduper.deduplicate(candidates)
        assert len(result) == 1

    def test_dedupe_different_names_same_domain(self):
        deduper = Deduplicator()
        candidates = [
            self._make_candidate("Old Name", domain="example.com"),
            self._make_candidate("New Name", domain="example.com"),
        ]
        result = deduper.deduplicate(candidates)
        assert len(result) == 1
        # First one wins
        assert result[0].name == "Old Name"

    def test_dedupe_handles_none_domain(self):
        deduper = Deduplicator()
        candidates = [
            self._make_candidate("Acme Innovations"),
            self._make_candidate("Globex Technologies"),
        ]
        result = deduper.deduplicate(candidates)
        assert len(result) == 2
