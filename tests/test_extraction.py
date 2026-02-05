"""Tests for data extraction functionality."""

import pytest

from app.enrich.parser import RuleBasedParser
from app.crawler.extractor import ContentExtractor


class TestRuleBasedParser:
    """Tests for rule-based extraction."""

    def test_extract_saas_business_model(self):
        parser = RuleBasedParser()
        text = "We offer a cloud-based SaaS platform with monthly subscription plans."
        result = parser.parse(text)
        assert result.business_model == "SaaS"
        assert result.business_model_confidence > 0

    def test_extract_marketplace_business_model(self):
        parser = RuleBasedParser()
        text = "Our marketplace connects buyers and sellers in the B2B space."
        result = parser.parse(text)
        assert result.business_model == "marketplace"

    def test_extract_b2b_customer_type(self):
        parser = RuleBasedParser()
        text = "We serve enterprise customers and B2B organizations."
        result = parser.parse(text)
        assert "B2B" in result.customer_types or "enterprise" in result.customer_types

    def test_extract_employee_count(self):
        parser = RuleBasedParser()
        text = "Join our team of 150 employees working on innovative solutions."
        result = parser.parse(text)
        assert result.employee_count == 150

    def test_extract_employee_count_team_format(self):
        parser = RuleBasedParser()
        text = "We have a team of 75 dedicated professionals."
        result = parser.parse(text)
        assert result.employee_count == 75

    def test_extract_revenue(self):
        parser = RuleBasedParser()
        text = "We've reached $5 million ARR and continue to grow."
        result = parser.parse(text)
        assert result.revenue_estimate == 5_000_000

    def test_extract_funding(self):
        parser = RuleBasedParser()
        text = "Recently raised $10 million in Series A funding."
        result = parser.parse(text)
        assert result.funding_total == 10_000_000

    def test_extract_compliance_soc2(self):
        parser = RuleBasedParser()
        text = "We are SOC 2 compliant and maintain strict security standards."
        result = parser.parse(text)
        assert "SOC2" in result.compliance_indicators

    def test_extract_compliance_hipaa(self):
        parser = RuleBasedParser()
        text = "Our platform is HIPAA compliant for healthcare data."
        result = parser.parse(text)
        assert "HIPAA" in result.compliance_indicators

    def test_extract_growing_team_signal(self):
        parser = RuleBasedParser()
        text = "We're hiring! Join our team and view open positions."
        result = parser.parse(text)
        assert "growing_team" in result.signals

    def test_extract_no_matches(self):
        parser = RuleBasedParser()
        text = "This is a simple text with no business information."
        result = parser.parse(text)
        assert result.business_model is None
        assert result.overall_confidence < 0.3

    def test_extract_keywords(self):
        parser = RuleBasedParser()
        text = "We provide healthcare technology solutions for hospitals."
        keywords = parser.extract_keywords(text, ["healthcare", "fintech", "technology"])
        assert "healthcare" in keywords
        assert "technology" in keywords
        assert "fintech" not in keywords

    def test_detect_disqualifiers(self):
        parser = RuleBasedParser()
        text = "Our cryptocurrency trading platform offers NFT marketplaces."
        disqualifiers = parser.detect_disqualifiers(text, ["cryptocurrency", "nft"])
        assert "cryptocurrency" in disqualifiers
        assert "nft" in disqualifiers


class TestContentExtractor:
    """Tests for HTML content extraction."""

    def test_extract_basic_html(self):
        extractor = ContentExtractor()
        html = "<html><body><p>Hello World</p></body></html>"
        result = extractor.extract(html)
        assert "Hello World" in result

    def test_extract_removes_scripts(self):
        extractor = ContentExtractor()
        html = """
        <html>
        <body>
            <p>Visible content</p>
            <script>console.log('hidden');</script>
        </body>
        </html>
        """
        result = extractor.extract(html)
        assert "Visible content" in result
        assert "console.log" not in result

    def test_extract_removes_styles(self):
        extractor = ContentExtractor()
        html = """
        <html>
        <head><style>.hidden { display: none; }</style></head>
        <body><p>Content here</p></body>
        </html>
        """
        result = extractor.extract(html)
        assert "Content here" in result
        assert ".hidden" not in result

    def test_extract_main_content(self):
        extractor = ContentExtractor()
        html = """
        <html>
        <body>
            <nav>Navigation menu</nav>
            <main><article>Main content here</article></main>
            <footer>Footer text</footer>
        </body>
        </html>
        """
        result = extractor.extract(html)
        assert "Main content" in result

    def test_extract_metadata(self):
        extractor = ContentExtractor()
        html = """
        <html>
        <head>
            <title>Company Name - Best in Industry</title>
            <meta name="description" content="We provide great services">
        </head>
        <body></body>
        </html>
        """
        metadata = extractor.extract_metadata(html)
        assert metadata.get("title") == "Company Name - Best in Industry"
        assert "great services" in metadata.get("description", "")

    def test_extract_empty_html(self):
        extractor = ContentExtractor()
        result = extractor.extract("")
        assert result == ""

    def test_extract_handles_malformed_html(self):
        extractor = ContentExtractor()
        html = "<p>Unclosed paragraph<div>Some content"
        result = extractor.extract(html)
        assert "content" in result.lower()
