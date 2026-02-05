"""Source connectors for discovering candidate companies."""

from .base import SourceConnector
from .web_search import DuckDuckGoConnector
from .opencorporates import OpenCorporatesConnector
from .mock import MockConnector

__all__ = [
    "SourceConnector",
    "DuckDuckGoConnector",
    "OpenCorporatesConnector",
    "MockConnector",
]
