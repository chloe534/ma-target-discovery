"""LLM-based extraction using Claude API."""

import json
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class LLMParser:
    """Extract structured data using Claude API when rule-based extraction has low confidence."""

    EXTRACTION_PROMPT = """Analyze this company's web content and extract structured information.

Company: {company_name}
Website: {website}

Content from their website:
---
{content}
---

Extract the following information in JSON format:
{{
    "business_model": "SaaS|marketplace|services|hardware|e-commerce|other",
    "business_model_explanation": "brief explanation",
    "customer_types": ["B2B", "B2C", "enterprise", "SMB"],
    "employee_count_estimate": number or null,
    "revenue_estimate_usd": number or null,
    "industries": ["list of industries"],
    "compliance_certifications": ["SOC2", "HIPAA", etc.],
    "positive_signals": ["growing_team", "recent_funding", etc.],
    "potential_concerns": ["list any red flags"],
    "confidence": 0.0-1.0
}}

Only include fields you can reasonably infer from the content. Be conservative with estimates.
Return only valid JSON, no other text."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.anthropic_api_key
        self._client = None

    @property
    def client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    async def parse(
        self,
        company_name: str,
        website: str,
        content: str,
        max_content_length: int = 8000,
    ) -> Optional[dict]:
        """Extract structured data using Claude API."""
        if not self.api_key:
            logger.warning("LLM parsing unavailable: ANTHROPIC_API_KEY not set")
            return None

        # Truncate content if too long
        if len(content) > max_content_length:
            content = content[:max_content_length] + "...[truncated]"

        prompt = self.EXTRACTION_PROMPT.format(
            company_name=company_name,
            website=website,
            content=content,
        )

        try:
            # Use sync client in async context (Anthropic SDK handles this)
            import asyncio
            response = await asyncio.to_thread(
                self._call_api, prompt
            )
            return response

        except Exception as e:
            logger.error(f"LLM extraction failed for {company_name}: {e}")
            return None

    def _call_api(self, prompt: str) -> Optional[dict]:
        """Call Claude API synchronously."""
        try:
            response = self.client.messages.create(
                model=settings.llm_model,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            # Extract text response
            text = response.content[0].text

            # Parse JSON from response
            # Handle potential markdown code blocks
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            return json.loads(text.strip())

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            return None

    def merge_with_rule_based(
        self,
        rule_based: dict,
        llm_result: Optional[dict],
    ) -> dict:
        """Merge rule-based and LLM extraction results."""
        if not llm_result:
            return rule_based

        merged = rule_based.copy()

        # Prefer LLM results for business model if rule-based confidence is low
        if (
            llm_result.get("business_model")
            and merged.get("business_model_confidence", 0) < 0.6
        ):
            merged["business_model"] = llm_result["business_model"]
            merged["business_model_confidence"] = llm_result.get("confidence", 0.7)

        # Merge customer types
        llm_types = llm_result.get("customer_types", [])
        existing_types = set(merged.get("customer_types", []))
        merged["customer_types"] = list(existing_types.union(set(llm_types)))

        # Use LLM estimates if rule-based didn't find them
        if not merged.get("employee_count") and llm_result.get("employee_count_estimate"):
            merged["employee_count"] = llm_result["employee_count_estimate"]

        if not merged.get("revenue_estimate") and llm_result.get("revenue_estimate_usd"):
            merged["revenue_estimate"] = llm_result["revenue_estimate_usd"]

        # Merge industries
        llm_industries = llm_result.get("industries", [])
        existing_industries = set(merged.get("industries", []))
        merged["industries"] = list(existing_industries.union(set(llm_industries)))

        # Merge compliance
        llm_compliance = llm_result.get("compliance_certifications", [])
        existing_compliance = set(merged.get("compliance_indicators", []))
        merged["compliance_indicators"] = list(existing_compliance.union(set(llm_compliance)))

        # Merge signals
        llm_signals = llm_result.get("positive_signals", [])
        existing_signals = set(merged.get("signals", []))
        merged["signals"] = list(existing_signals.union(set(llm_signals)))

        # Add potential concerns as disqualifiers to review
        if llm_result.get("potential_concerns"):
            merged["potential_concerns"] = llm_result["potential_concerns"]

        # Update confidence
        llm_confidence = llm_result.get("confidence", 0.5)
        rule_confidence = merged.get("overall_confidence", 0.5)
        merged["overall_confidence"] = max(rule_confidence, llm_confidence)

        return merged
