"""SQLAlchemy database models and setup."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

from app.config import settings

Base = declarative_base()


class DBCompany(Base):
    """Stored company record."""

    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(500), nullable=False)
    website = Column(String(1000))
    description = Column(Text)

    # Discovery info
    source = Column(String(100))
    source_url = Column(String(1000))
    discovered_at = Column(DateTime, default=datetime.utcnow)

    # Enriched data
    enriched_at = Column(DateTime)
    founded_year = Column(Integer)
    headquarters = Column(String(500))
    employees_estimate = Column(Integer)
    revenue_estimate = Column(Integer)
    funding_total = Column(Integer)

    # Classification
    business_model = Column(String(100))
    business_model_confidence = Column(Float, default=0.0)
    customer_types = Column(Text)  # JSON array
    industries = Column(Text)  # JSON array

    # Signals
    compliance_indicators = Column(Text)  # JSON array
    signals_detected = Column(Text)  # JSON array
    disqualifiers_detected = Column(Text)  # JSON array

    # Extraction data
    extraction_confidence = Column(Float, default=0.0)
    page_contents = Column(Text)  # JSON dict

    # Relationships
    enrichments = relationship("DBEnrichment", back_populates="company")
    scores = relationship("DBScore", back_populates="company")

    __table_args__ = (
        Index("idx_company_name", "name"),
        Index("idx_company_business_model", "business_model"),
    )

    def get_customer_types(self) -> list[str]:
        return json.loads(self.customer_types) if self.customer_types else []

    def set_customer_types(self, types: list[str]):
        self.customer_types = json.dumps(types)

    def get_industries(self) -> list[str]:
        return json.loads(self.industries) if self.industries else []

    def set_industries(self, industries: list[str]):
        self.industries = json.dumps(industries)


class DBEnrichment(Base):
    """Enrichment history for a company."""

    __tablename__ = "enrichments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    source = Column(String(100), nullable=False)
    enriched_at = Column(DateTime, default=datetime.utcnow)
    data = Column(Text)  # JSON blob of enrichment data
    success = Column(Boolean, default=True)
    error_message = Column(Text)

    company = relationship("DBCompany", back_populates="enrichments")

    __table_args__ = (Index("idx_enrichment_company", "company_id"),)


class DBSearchRun(Base):
    """Search run tracking."""

    __tablename__ = "search_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), unique=True, nullable=False, index=True)
    criteria = Column(Text, nullable=False)  # JSON
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    total_found = Column(Integer, default=0)
    total_scored = Column(Integer, default=0)
    error_message = Column(Text)

    scores = relationship("DBScore", back_populates="search_run")


class DBScore(Base):
    """Scoring results for a search run."""

    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_run_id = Column(Integer, ForeignKey("search_runs.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    fit_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    rank = Column(Integer)

    passed_filters = Column(Boolean, default=True)
    failed_filters = Column(Text)  # JSON array
    is_disqualified = Column(Boolean, default=False)
    disqualification_reasons = Column(Text)  # JSON array

    evidence = Column(Text)  # JSON array of Evidence objects
    match_summary = Column(Text)  # JSON array
    score_breakdown = Column(Text)  # JSON dict

    scored_at = Column(DateTime, default=datetime.utcnow)

    search_run = relationship("DBSearchRun", back_populates="scores")
    company = relationship("DBCompany", back_populates="scores")

    __table_args__ = (
        Index("idx_score_run", "search_run_id"),
        Index("idx_score_company", "company_id"),
        Index("idx_score_fit", "fit_score"),
    )


class DBCache(Base):
    """URL content cache."""

    __tablename__ = "cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(2000), unique=True, nullable=False, index=True)
    content = Column(Text)
    content_type = Column(String(100))
    fetched_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    status_code = Column(Integer)

    __table_args__ = (Index("idx_cache_expires", "expires_at"),)


class DBRobotsCache(Base):
    """Robots.txt cache per domain."""

    __tablename__ = "robots_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    robots_txt = Column(Text)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)


# Database initialization
def init_db(db_url: Optional[str] = None) -> sessionmaker:
    """Initialize database and return session maker."""
    url = db_url or settings.database_url
    engine = create_engine(url, echo=False)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def get_session() -> Session:
    """Get a new database session."""
    SessionLocal = init_db()
    return SessionLocal()
