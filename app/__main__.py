"""CLI entry point for M&A Target Discovery."""

import argparse
import asyncio
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.models import AcquisitionCriteria, CandidateCompany, EnrichedCompany
from app.models.database import init_db
from app.connectors import DuckDuckGoConnector, MockConnector
from app.crawler import Fetcher, ContentExtractor
from app.enrich import Deduplicator, RuleBasedParser, LLMParser, BusinessClassifier
from app.score import Scorer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_discovery(
    criteria: AcquisitionCriteria,
    output_path: Path,
    use_mock: bool = False,
    limit: int = 50,
) -> list:
    """Run the complete discovery pipeline."""
    # Initialize database
    init_db()

    # Phase 1: Discovery
    logger.info("Phase 1: Discovering candidates...")
    if use_mock:
        connector = MockConnector()
        logger.info("Using mock connector for testing")
    else:
        connector = DuckDuckGoConnector()
        logger.info("Using DuckDuckGo for web search")

    candidates = await connector.search(criteria, limit=limit)
    logger.info(f"Found {len(candidates)} candidates")

    if not candidates:
        logger.warning("No candidates found. Check your search criteria.")
        return []

    # Phase 2: Deduplication
    logger.info("Phase 2: Deduplicating candidates...")
    deduper = Deduplicator()
    candidates = deduper.deduplicate(candidates)
    logger.info(f"{len(candidates)} candidates after deduplication")

    # Phase 3: Enrichment
    logger.info("Phase 3: Enriching candidates...")
    enriched = await enrich_candidates(candidates, criteria)
    logger.info(f"Enriched {len(enriched)} candidates")

    # Phase 4: Scoring
    logger.info("Phase 4: Scoring and ranking...")
    scorer = Scorer()
    scored = scorer.score_and_rank(enriched, criteria)
    logger.info(f"Scored {len(scored)} candidates")

    # Export results
    logger.info(f"Exporting results to {output_path}...")
    export_to_csv(scored, output_path)
    logger.info(f"Results exported to {output_path}")

    # Print summary
    print_summary(scored)

    return scored


async def enrich_candidates(
    candidates: list[CandidateCompany],
    criteria: AcquisitionCriteria,
) -> list[EnrichedCompany]:
    """Enrich candidate companies with additional data."""
    fetcher = Fetcher()
    extractor = ContentExtractor()
    parser = RuleBasedParser()
    llm_parser = LLMParser()
    classifier = BusinessClassifier()

    enriched = []
    pages_to_fetch = ["", "about", "product", "pricing", "careers"]
    total = len(candidates)

    for i, candidate in enumerate(candidates, 1):
        logger.info(f"  Enriching {i}/{total}: {candidate.name}")

        try:
            # Create enriched company from candidate
            enriched_company = EnrichedCompany(**candidate.model_dump())

            if candidate.website:
                # Fetch key pages
                base_url = candidate.website.rstrip("/")
                fetch_results = await fetcher.fetch_pages(base_url, pages_to_fetch)

                # Extract content from each page
                all_text = []
                for url, result in fetch_results.items():
                    if result.success and result.content:
                        text = extractor.extract(result.content, url)
                        if text:
                            enriched_company.page_contents[url] = text
                            all_text.append(text)
                            enriched_company.enrichment_sources.append(url)

                combined_text = "\n".join(all_text)

                if combined_text:
                    # Rule-based extraction
                    parsed = parser.parse(combined_text)

                    # Use LLM if confidence is low
                    if parsed.overall_confidence < settings.llm_confidence_threshold:
                        if settings.anthropic_api_key:
                            logger.debug(f"    Using LLM for {candidate.name}")
                            llm_result = await llm_parser.parse(
                                candidate.name,
                                candidate.website,
                                combined_text[:8000],
                            )
                            parsed_dict = {
                                "business_model": parsed.business_model,
                                "business_model_confidence": parsed.business_model_confidence,
                                "customer_types": parsed.customer_types,
                                "employee_count": parsed.employee_count,
                                "revenue_estimate": parsed.revenue_estimate,
                                "industries": parsed.industries,
                                "compliance_indicators": parsed.compliance_indicators,
                                "signals": parsed.signals,
                                "overall_confidence": parsed.overall_confidence,
                            }
                            merged = llm_parser.merge_with_rule_based(parsed_dict, llm_result)
                        else:
                            merged = {
                                "business_model": parsed.business_model,
                                "business_model_confidence": parsed.business_model_confidence,
                                "customer_types": parsed.customer_types,
                                "employee_count": parsed.employee_count,
                                "revenue_estimate": parsed.revenue_estimate,
                                "industries": parsed.industries,
                                "compliance_indicators": parsed.compliance_indicators,
                                "signals": parsed.signals,
                                "overall_confidence": parsed.overall_confidence,
                            }
                    else:
                        merged = {
                            "business_model": parsed.business_model,
                            "business_model_confidence": parsed.business_model_confidence,
                            "customer_types": parsed.customer_types,
                            "employee_count": parsed.employee_count,
                            "revenue_estimate": parsed.revenue_estimate,
                            "industries": parsed.industries,
                            "compliance_indicators": parsed.compliance_indicators,
                            "signals": parsed.signals,
                            "overall_confidence": parsed.overall_confidence,
                        }

                    # Apply enrichment
                    enriched_company.business_model = merged.get("business_model")
                    enriched_company.business_model_confidence = merged.get("business_model_confidence", 0.0)
                    enriched_company.customer_types = merged.get("customer_types", [])
                    enriched_company.employees_estimate = merged.get("employee_count")
                    enriched_company.revenue_estimate = merged.get("revenue_estimate")
                    enriched_company.compliance_indicators = merged.get("compliance_indicators", [])
                    enriched_company.signals_detected = merged.get("signals", [])
                    enriched_company.extraction_confidence = merged.get("overall_confidence", 0.0)

                    # Classify and detect disqualifiers
                    classification = classifier.classify(combined_text, criteria, merged)
                    enriched_company.industries = classification.industries
                    enriched_company.disqualifiers_detected = classification.disqualifiers_detected

            enriched_company.enriched_at = datetime.utcnow()
            enriched.append(enriched_company)

        except Exception as e:
            logger.warning(f"    Failed to enrich {candidate.name}: {e}")
            # Still include with minimal enrichment
            enriched.append(EnrichedCompany(**candidate.model_dump()))

    return enriched


def export_to_csv(results: list, output_path: Path):
    """Export results to CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            "Rank",
            "Name",
            "Domain",
            "Website",
            "Fit Score",
            "Confidence",
            "Business Model",
            "Industries",
            "Customer Types",
            "Employees",
            "Match Summary",
            "Evidence Count",
            "Disqualified",
            "Disqualification Reasons",
        ])

        # Data rows
        for r in results:
            writer.writerow([
                r.rank,
                r.name,
                r.domain or "",
                r.website or "",
                f"{r.fit_score:.1f}",
                f"{r.confidence:.2f}",
                r.business_model or "",
                "; ".join(r.industries),
                "; ".join(r.customer_types),
                r.employees_estimate or "",
                " | ".join(r.match_summary),
                len(r.evidence),
                "Yes" if r.is_disqualified else "No",
                "; ".join(r.disqualification_reasons),
            ])


def print_summary(results: list):
    """Print a summary of results to console."""
    print("\n" + "=" * 60)
    print("M&A TARGET DISCOVERY - RESULTS SUMMARY")
    print("=" * 60)

    qualified = [r for r in results if not r.is_disqualified]
    disqualified = [r for r in results if r.is_disqualified]

    print(f"\nTotal candidates scored: {len(results)}")
    print(f"Qualified targets: {len(qualified)}")
    print(f"Disqualified: {len(disqualified)}")

    if qualified:
        print("\n" + "-" * 60)
        print("TOP 10 TARGETS")
        print("-" * 60)

        for r in qualified[:10]:
            print(f"\n#{r.rank} {r.name}")
            print(f"   Score: {r.fit_score:.1f} | Confidence: {r.confidence:.2f}")
            if r.domain:
                print(f"   Domain: {r.domain}")
            if r.business_model:
                print(f"   Business Model: {r.business_model}")
            if r.industries:
                print(f"   Industries: {', '.join(r.industries[:3])}")
            if r.match_summary:
                print(f"   Why: {r.match_summary[0]}")

    print("\n" + "=" * 60)


def load_criteria(criteria_path: Path) -> AcquisitionCriteria:
    """Load criteria from JSON file."""
    with open(criteria_path, "r") as f:
        data = json.load(f)
    return AcquisitionCriteria(**data)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="M&A Target Discovery - Find and rank acquisition targets"
    )
    parser.add_argument(
        "--criteria", "-c",
        type=Path,
        default=Path("criteria.json"),
        help="Path to criteria JSON file (default: criteria.json)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=settings.data_dir / "ranked_targets.csv",
        help="Output CSV path (default: data/ranked_targets.csv)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=50,
        help="Maximum number of candidates to discover (default: 50)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock connector for testing",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load criteria
    if not args.criteria.exists():
        logger.error(f"Criteria file not found: {args.criteria}")
        logger.info("Create a criteria.json file or use --criteria to specify path")
        sys.exit(1)

    try:
        criteria = load_criteria(args.criteria)
        logger.info(f"Loaded criteria from {args.criteria}")
    except Exception as e:
        logger.error(f"Failed to load criteria: {e}")
        sys.exit(1)

    # Run discovery
    try:
        asyncio.run(run_discovery(
            criteria=criteria,
            output_path=args.output,
            use_mock=args.mock,
            limit=args.limit,
        ))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
