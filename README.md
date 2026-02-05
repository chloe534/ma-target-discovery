# M&A Target Discovery Platform

An MVP platform for discovering, enriching, scoring, and ranking M&A acquisition targets based on configurable criteria profiles.

## Features

- **Discovery**: Search for potential acquisition targets using DuckDuckGo and OpenCorporates
- **Enrichment**: Automatically crawl company websites to extract business information
- **Scoring**: Score and rank companies against your acquisition criteria
- **Evidence**: Provide supporting evidence for each match with source citations
- **Export**: Export ranked results to CSV for further analysis

## Quick Start

### Installation

```bash
# Clone or navigate to the project
cd ma-target-discovery

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

1. **Criteria File**: Edit `criteria.json` with your acquisition criteria (see below)
2. **API Keys** (optional): Set environment variables for enhanced features:
   ```bash
   export ANTHROPIC_API_KEY=your_key_here  # For LLM-powered extraction
   export OPENCORPORATES_API_KEY=your_key  # For company data API
   ```

### Running via CLI

```bash
# Run discovery with default criteria file
python -m app --criteria criteria.json

# Run with mock data for testing
python -m app --criteria criteria.json --mock

# Specify output file
python -m app --criteria criteria.json --output results.csv

# Verbose logging
python -m app --criteria criteria.json --verbose
```

### Running the Web UI

```bash
# Start the API server
uvicorn app.api.main:app --reload

# Open browser to http://localhost:8000
```

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_scoring.py
```

## Criteria Configuration

The `criteria.json` file defines your acquisition target profile:

```json
{
  "industries_include": ["healthcare tech", "fintech"],
  "industries_exclude": ["gambling", "cryptocurrency"],
  "keywords_include": ["SaaS", "B2B", "enterprise"],
  "keywords_exclude": ["consulting", "agency"],
  "geography": {
    "countries": ["US", "UK"],
    "exclude_countries": []
  },
  "size": {
    "employees_min": 10,
    "employees_max": 500,
    "revenue_min": 1000000,
    "revenue_max": 50000000
  },
  "business_model": {
    "types": ["SaaS"],
    "exclude_types": ["services"],
    "recurring_revenue_required": true
  },
  "customer_type": ["B2B", "enterprise"],
  "compliance_tags": ["SOC2"],
  "dealbreakers": ["gambling", "adult content"],
  "preferred_signals": ["growing_team", "recent_funding"],
  "weights": {
    "industry": 0.20,
    "business_model": 0.25,
    "customer_type": 0.15,
    "size": 0.15,
    "compliance": 0.10,
    "signals": 0.15
  }
}
```

### Criteria Fields

| Field | Description |
|-------|-------------|
| `industries_include` | Industries to search for |
| `industries_exclude` | Industries to reject |
| `keywords_include` | Positive keywords to look for |
| `keywords_exclude` | Negative keywords to avoid |
| `geography.countries` | ISO country codes to include |
| `geography.exclude_countries` | Countries to exclude |
| `size.employees_min/max` | Employee count range |
| `size.revenue_min/max` | Revenue range (USD) |
| `business_model.types` | Acceptable business models (SaaS, marketplace, etc.) |
| `business_model.exclude_types` | Business models to reject |
| `customer_type` | Target customer types (B2B, B2C, enterprise, SMB) |
| `compliance_tags` | Required compliance (SOC2, HIPAA, GDPR, etc.) |
| `dealbreakers` | Instant disqualification criteria |
| `preferred_signals` | Positive signals to look for |
| `weights` | Scoring weights per criterion (0-1) |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/search` | Start a new search with criteria |
| GET | `/api/status/{run_id}` | Check search progress |
| GET | `/api/results/{run_id}` | Get ranked results |
| GET | `/api/export/{run_id}` | Download CSV export |
| GET | `/health` | Health check |

## Adding New Connectors

To add a new data source connector:

1. Create a new file in `app/connectors/`:

```python
from app.connectors.base import SourceConnector
from app.models import AcquisitionCriteria, CandidateCompany

class MyConnector(SourceConnector):
    name = "my_connector"

    def generate_queries(self, criteria: AcquisitionCriteria) -> list[str]:
        # Generate search queries from criteria
        return [...]

    async def search(
        self,
        criteria: AcquisitionCriteria,
        limit: int = 50,
    ) -> list[CandidateCompany]:
        # Implement search logic
        return [...]
```

2. Register in `app/connectors/__init__.py`
3. Add to the search pipeline in `app/api/routes.py`

## Project Structure

```
ma-target-discovery/
├── app/
│   ├── models/          # Data models (Pydantic + SQLAlchemy)
│   ├── connectors/      # Data source connectors
│   ├── crawler/         # Web crawling and extraction
│   ├── enrich/          # Enrichment pipeline
│   ├── score/           # Scoring engine
│   ├── api/             # FastAPI application
│   └── ui/static/       # Web UI
├── tests/               # Test suite
├── data/                # SQLite database and cache
├── criteria.json        # Example criteria file
└── requirements.txt     # Python dependencies
```

## How Scoring Works

1. **Hard Filters**: Companies are first checked against dealbreakers and exclusions
2. **Criterion Scoring**: Each criterion (industry, business model, etc.) is scored 0-1
3. **Weighted Sum**: Scores are combined using configured weights
4. **Confidence**: Based on data completeness and extraction quality
5. **Ranking**: Companies are ranked by fit_score, then confidence

## Ethical Considerations

- Respects robots.txt for all crawled sites
- Rate-limited to 1 request/second per domain
- 30-day cache to minimize redundant requests
- User-agent identifies the bot with contact info

## License

MIT License
