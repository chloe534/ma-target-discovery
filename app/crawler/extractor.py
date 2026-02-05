"""HTML content extraction."""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)


class ContentExtractor:
    """Extract clean text content from HTML."""

    # Tags to remove entirely
    REMOVE_TAGS = [
        "script", "style", "noscript", "iframe", "svg",
        "nav", "footer", "header", "aside", "form",
    ]

    # Tags that indicate main content
    CONTENT_TAGS = ["article", "main", "section", "div"]

    # Common class/id patterns for main content
    CONTENT_PATTERNS = [
        r"content", r"main", r"article", r"post", r"entry",
        r"body", r"text", r"story", r"page",
    ]

    # Patterns for non-content areas
    SKIP_PATTERNS = [
        r"nav", r"menu", r"footer", r"header", r"sidebar",
        r"comment", r"share", r"social", r"related", r"ad",
        r"cookie", r"popup", r"modal", r"banner",
    ]

    def extract(self, html: str, url: Optional[str] = None) -> str:
        """Extract clean text from HTML."""
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, "lxml")

            # Remove unwanted tags
            for tag in self.REMOVE_TAGS:
                for element in soup.find_all(tag):
                    element.decompose()

            # Remove comments
            for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
                comment.extract()

            # Try to find main content area
            main_content = self._find_main_content(soup)

            if main_content:
                text = self._extract_text(main_content)
            else:
                # Fall back to body or full document
                body = soup.find("body") or soup
                text = self._extract_text(body)

            # Clean up whitespace
            text = self._clean_text(text)

            return text

        except Exception as e:
            logger.warning(f"Failed to extract content from {url}: {e}")
            return ""

    def extract_metadata(self, html: str) -> dict:
        """Extract metadata from HTML."""
        metadata = {}

        try:
            soup = BeautifulSoup(html, "lxml")

            # Title
            title_tag = soup.find("title")
            if title_tag:
                metadata["title"] = title_tag.get_text(strip=True)

            # Meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                metadata["description"] = meta_desc.get("content", "")

            # Meta keywords
            meta_kw = soup.find("meta", attrs={"name": "keywords"})
            if meta_kw:
                metadata["keywords"] = meta_kw.get("content", "")

            # Open Graph
            og_title = soup.find("meta", property="og:title")
            if og_title:
                metadata["og_title"] = og_title.get("content", "")

            og_desc = soup.find("meta", property="og:description")
            if og_desc:
                metadata["og_description"] = og_desc.get("content", "")

            # Schema.org Organization
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    import json
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        if data.get("@type") == "Organization":
                            metadata["schema_org"] = data
                            break
                except (json.JSONDecodeError, TypeError):
                    continue

        except Exception as e:
            logger.debug(f"Failed to extract metadata: {e}")

        return metadata

    def _find_main_content(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        """Try to find the main content area."""
        # First try semantic tags
        for tag in ["main", "article"]:
            element = soup.find(tag)
            if element:
                return element

        # Try content-related class/id patterns
        for pattern in self.CONTENT_PATTERNS:
            regex = re.compile(pattern, re.I)

            # Check by id
            element = soup.find(id=regex)
            if element and self._is_content_element(element):
                return element

            # Check by class
            element = soup.find(class_=regex)
            if element and self._is_content_element(element):
                return element

        return None

    def _is_content_element(self, element: BeautifulSoup) -> bool:
        """Check if element likely contains main content."""
        # Skip if it matches non-content patterns
        element_id = element.get("id", "")
        element_classes = " ".join(element.get("class", []))

        for pattern in self.SKIP_PATTERNS:
            if re.search(pattern, element_id, re.I):
                return False
            if re.search(pattern, element_classes, re.I):
                return False

        # Check if it has substantial text
        text = element.get_text(strip=True)
        return len(text) > 200

    def _extract_text(self, element: BeautifulSoup) -> str:
        """Extract text from an element."""
        # Get all text, separating with newlines
        texts = []

        for descendant in element.descendants:
            if isinstance(descendant, str):
                text = descendant.strip()
                if text:
                    texts.append(text)
            elif descendant.name in ["br", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"]:
                texts.append("\n")

        return " ".join(texts)

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text."""
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)

        # Fix newlines
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove leading/trailing whitespace from lines
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        return text.strip()
