"""API routes for M&A Target Discovery."""

import csv
import io
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.models import AcquisitionCriteria, CandidateCompany, EnrichedCompany, ScoredCompany
from app.models.database import DBSearchRun, DBScore, DBCompany, get_session
from app.connectors import DuckDuckGoConnector, MockConnector
from app.crawler import Fetcher, ContentExtractor
from app.enrich import Deduplicator, RuleBasedParser, LLMParser, BusinessClassifier
from app.score import Scorer

logger = logging.getLogger(__name__)

router = APIRouter()


class SearchRequest(BaseModel):
    """Request body for starting a search."""
    criteria: AcquisitionCriteria
    use_mock: bool = False
    limit: int = 50


class SearchResponse(BaseModel):
    """Response for search submission."""
    run_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    """Response for search status."""
    run_id: str
    status: str
    total_found: int
    total_scored: int
    error_message: Optional[str] = None


class ResultItem(BaseModel):
    """Single result item for API response."""
    rank: int
    name: str
    domain: Optional[str]
    website: Optional[str]
    fit_score: float
    confidence: float
    business_model: Optional[str]
    industries: list[str]
    customer_types: list[str]
    employees_estimate: Optional[int]
    match_summary: list[str]
    evidence: list[dict]
    is_disqualified: bool
    disqualification_reasons: list[str]


class ResultsResponse(BaseModel):
    """Response for search results."""
    run_id: str
    status: str
    total_results: int
    results: list[ResultItem]


# In-memory storage for active searches (for MVP simplicity)
active_searches: dict[str, dict] = {}


@router.post("/search", response_model=SearchResponse)
async def start_search(request: SearchRequest, background_tasks: BackgroundTasks):
    """Start a new M&A target discovery search."""
    run_id = str(uuid.uuid4())

    # Store search run in database
    session = get_session()
    search_run = DBSearchRun(
        run_id=run_id,
        criteria=request.criteria.model_dump_json(),
        status="pending",
        started_at=datetime.utcnow(),
    )
    session.add(search_run)
    session.commit()
    session.close()

    # Store in memory for progress tracking
    active_searches[run_id] = {
        "status": "pending",
        "criteria": request.criteria,
        "use_mock": request.use_mock,
        "limit": request.limit,
        "results": [],
    }

    # Run search in background
    background_tasks.add_task(run_search, run_id)

    return SearchResponse(
        run_id=run_id,
        status="pending",
        message="Search started. Use /status/{run_id} to check progress.",
    )


@router.get("/status/{run_id}", response_model=StatusResponse)
async def get_status(run_id: str):
    """Get the status of a search run."""
    # Check memory first
    if run_id in active_searches:
        search = active_searches[run_id]
        return StatusResponse(
            run_id=run_id,
            status=search["status"],
            total_found=search.get("total_found", 0),
            total_scored=len(search.get("results", [])),
            error_message=search.get("error"),
        )

    # Check database
    session = get_session()
    search_run = session.query(DBSearchRun).filter_by(run_id=run_id).first()
    session.close()

    if not search_run:
        raise HTTPException(status_code=404, detail="Search run not found")

    return StatusResponse(
        run_id=run_id,
        status=search_run.status,
        total_found=search_run.total_found,
        total_scored=search_run.total_scored,
        error_message=search_run.error_message,
    )


@router.get("/results/{run_id}", response_model=ResultsResponse)
async def get_results(run_id: str):
    """Get the results of a completed search run."""
    # Check memory first
    if run_id in active_searches:
        search = active_searches[run_id]
        if search["status"] not in ["completed", "failed"]:
            return ResultsResponse(
                run_id=run_id,
                status=search["status"],
                total_results=0,
                results=[],
            )

        results = [_format_result(r) for r in search.get("results", [])]
        return ResultsResponse(
            run_id=run_id,
            status=search["status"],
            total_results=len(results),
            results=results,
        )

    # Check database
    session = get_session()
    search_run = session.query(DBSearchRun).filter_by(run_id=run_id).first()

    if not search_run:
        session.close()
        raise HTTPException(status_code=404, detail="Search run not found")

    # Load results from database
    scores = session.query(DBScore).filter_by(search_run_id=search_run.id).all()
    results = []

    for score in scores:
        company = session.query(DBCompany).filter_by(id=score.company_id).first()
        if company:
            results.append(_format_db_result(company, score))

    session.close()

    # Sort by rank
    results.sort(key=lambda r: r.rank)

    return ResultsResponse(
        run_id=run_id,
        status=search_run.status,
        total_results=len(results),
        results=results,
    )


@router.get("/export/{run_id}")
async def export_results(run_id: str):
    """Export search results as CSV."""
    # Get results
    results_response = await get_results(run_id)

    if not results_response.results:
        raise HTTPException(status_code=404, detail="No results to export")

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Rank", "Name", "Domain", "Website", "Fit Score", "Confidence",
        "Business Model", "Industries", "Customer Types", "Employees",
        "Match Summary", "Disqualified", "Disqualification Reasons",
    ])

    # Data rows
    for r in results_response.results:
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
            "Yes" if r.is_disqualified else "No",
            "; ".join(r.disqualification_reasons),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ma_targets_{run_id[:8]}.csv"},
    )


async def run_search(run_id: str):
    """Execute the search pipeline."""
    search = active_searches.get(run_id)
    if not search:
        return

    try:
        search["status"] = "running"
        criteria = search["criteria"]
        use_mock = search["use_mock"]
        limit = search["limit"]

        # Phase 1: Discovery
        logger.info(f"[{run_id}] Starting discovery...")
        if use_mock:
            connector = MockConnector()
        else:
            connector = DuckDuckGoConnector()

        candidates = await connector.search(criteria, limit=limit)
        logger.info(f"[{run_id}] Found {len(candidates)} candidates")
        search["total_found"] = len(candidates)

        # Phase 2: Deduplication
        deduper = Deduplicator()
        candidates = deduper.deduplicate(candidates)
        logger.info(f"[{run_id}] {len(candidates)} candidates after deduplication")

        # Phase 3: Enrichment
        logger.info(f"[{run_id}] Starting enrichment...")
        enriched = await enrich_candidates(candidates, criteria)
        logger.info(f"[{run_id}] Enriched {len(enriched)} candidates")

        # Phase 4: Scoring
        logger.info(f"[{run_id}] Scoring candidates...")
        scorer = Scorer()
        scored = scorer.score_and_rank(enriched, criteria)
        logger.info(f"[{run_id}] Scored {len(scored)} candidates")

        search["results"] = scored
        search["status"] = "completed"

        # Update database
        _save_results_to_db(run_id, scored)

    except Exception as e:
        logger.error(f"[{run_id}] Search failed: {e}")
        search["status"] = "failed"
        search["error"] = str(e)

        session = get_session()
        search_run = session.query(DBSearchRun).filter_by(run_id=run_id).first()
        if search_run:
            search_run.status = "failed"
            search_run.error_message = str(e)
            session.commit()
        session.close()


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

    for candidate in candidates:
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
            logger.warning(f"Failed to enrich {candidate.name}: {e}")
            # Still include with minimal enrichment
            enriched.append(EnrichedCompany(**candidate.model_dump()))

    return enriched


def _format_result(scored: ScoredCompany) -> ResultItem:
    """Format a ScoredCompany for API response."""
    return ResultItem(
        rank=scored.rank or 0,
        name=scored.name,
        domain=scored.domain,
        website=scored.website,
        fit_score=scored.fit_score,
        confidence=scored.confidence,
        business_model=scored.business_model,
        industries=scored.industries,
        customer_types=scored.customer_types,
        employees_estimate=scored.employees_estimate,
        match_summary=scored.match_summary,
        evidence=[e.model_dump() for e in scored.evidence],
        is_disqualified=scored.is_disqualified,
        disqualification_reasons=scored.disqualification_reasons,
    )


def _format_db_result(company: DBCompany, score: DBScore) -> ResultItem:
    """Format database records for API response."""
    return ResultItem(
        rank=score.rank or 0,
        name=company.name,
        domain=company.domain,
        website=company.website,
        fit_score=score.fit_score,
        confidence=score.confidence,
        business_model=company.business_model,
        industries=company.get_industries(),
        customer_types=company.get_customer_types(),
        employees_estimate=company.employees_estimate,
        match_summary=json.loads(score.match_summary) if score.match_summary else [],
        evidence=json.loads(score.evidence) if score.evidence else [],
        is_disqualified=score.is_disqualified,
        disqualification_reasons=json.loads(score.disqualification_reasons) if score.disqualification_reasons else [],
    )


def _save_results_to_db(run_id: str, results: list[ScoredCompany]):
    """Save search results to database."""
    session = get_session()

    search_run = session.query(DBSearchRun).filter_by(run_id=run_id).first()
    if not search_run:
        session.close()
        return

    search_run.status = "completed"
    search_run.completed_at = datetime.utcnow()
    search_run.total_found = len(results)
    search_run.total_scored = len(results)

    for result in results:
        # Find or create company
        company = session.query(DBCompany).filter_by(domain=result.domain).first()
        if not company:
            company = DBCompany(
                domain=result.domain or result.name.lower().replace(" ", ""),
                name=result.name,
                website=result.website,
                description=result.description,
                source=result.source,
                discovered_at=result.discovered_at,
            )
            session.add(company)
            session.flush()

        # Update company data
        company.enriched_at = result.enriched_at
        company.business_model = result.business_model
        company.business_model_confidence = result.business_model_confidence
        company.employees_estimate = result.employees_estimate
        company.revenue_estimate = result.revenue_estimate
        company.set_customer_types(result.customer_types)
        company.set_industries(result.industries)

        # Create score record
        score = DBScore(
            search_run_id=search_run.id,
            company_id=company.id,
            fit_score=result.fit_score,
            confidence=result.confidence,
            rank=result.rank,
            passed_filters=result.passed_filters,
            failed_filters=json.dumps(result.failed_filters),
            is_disqualified=result.is_disqualified,
            disqualification_reasons=json.dumps(result.disqualification_reasons),
            evidence=json.dumps([e.model_dump() for e in result.evidence]),
            match_summary=json.dumps(result.match_summary),
            score_breakdown=json.dumps(result.score_breakdown),
        )
        session.add(score)

    session.commit()
    session.close()
