"""FastAPI application setup."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.models.database import init_db
from .routes import router

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title="M&A Target Discovery Platform",
    description="Discover, enrich, score, and rank M&A acquisition targets",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint (before static mount)
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


# Include API routes
app.include_router(router, prefix="/api")

# Serve static files (UI) - must be last since it mounts at /
static_path = Path(__file__).parent.parent / "ui" / "static"
if static_path.exists():
    app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
