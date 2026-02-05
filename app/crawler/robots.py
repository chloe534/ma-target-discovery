"""Robots.txt parser and checker."""

import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import settings
from app.models.database import DBRobotsCache, get_session

logger = logging.getLogger(__name__)


class RobotsChecker:
    """Check robots.txt compliance for URLs."""

    def __init__(self, user_agent: Optional[str] = None):
        self.user_agent = user_agent or settings.user_agent
        self._parsers: dict[str, RobotFileParser] = {}

    async def can_fetch(self, url: str) -> bool:
        """Check if the given URL can be fetched according to robots.txt."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if not domain:
                return False

            parser = await self._get_parser(domain, f"{parsed.scheme}://{domain}")
            if parser is None:
                # If we can't get robots.txt, assume allowed
                return True

            return parser.can_fetch(self.user_agent, url)

        except Exception as e:
            logger.warning(f"Error checking robots.txt for {url}: {e}")
            return True  # Allow on error

    async def _get_parser(self, domain: str, base_url: str) -> Optional[RobotFileParser]:
        """Get or create a robots.txt parser for a domain."""
        if domain in self._parsers:
            return self._parsers[domain]

        # Check cache
        robots_txt = await self._get_cached_robots(domain)

        if robots_txt is None:
            # Fetch robots.txt
            robots_txt = await self._fetch_robots(base_url)
            if robots_txt is not None:
                await self._cache_robots(domain, robots_txt)

        if robots_txt is None:
            self._parsers[domain] = None
            return None

        # Parse robots.txt
        parser = RobotFileParser()
        parser.parse(robots_txt.splitlines())
        self._parsers[domain] = parser

        return parser

    async def _fetch_robots(self, base_url: str) -> Optional[str]:
        """Fetch robots.txt from a domain."""
        robots_url = f"{base_url}/robots.txt"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.connect_timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    robots_url,
                    headers={"User-Agent": self.user_agent},
                )

                if response.status_code == 200:
                    return response.text
                else:
                    logger.debug(f"No robots.txt at {robots_url}: {response.status_code}")
                    return ""  # Empty means no restrictions

        except Exception as e:
            logger.debug(f"Failed to fetch robots.txt from {base_url}: {e}")
            return None

    async def _get_cached_robots(self, domain: str) -> Optional[str]:
        """Get cached robots.txt for a domain."""
        try:
            session = get_session()
            cached = session.query(DBRobotsCache).filter_by(domain=domain).first()

            if cached and cached.expires_at > datetime.utcnow():
                return cached.robots_txt

            session.close()
        except Exception as e:
            logger.debug(f"Cache lookup failed: {e}")

        return None

    async def _cache_robots(self, domain: str, robots_txt: str):
        """Cache robots.txt for a domain."""
        try:
            session = get_session()
            expires_at = datetime.utcnow() + timedelta(hours=settings.robots_cache_duration_hours)

            cached = session.query(DBRobotsCache).filter_by(domain=domain).first()
            if cached:
                cached.robots_txt = robots_txt
                cached.fetched_at = datetime.utcnow()
                cached.expires_at = expires_at
            else:
                cached = DBRobotsCache(
                    domain=domain,
                    robots_txt=robots_txt,
                    fetched_at=datetime.utcnow(),
                    expires_at=expires_at,
                )
                session.add(cached)

            session.commit()
            session.close()

        except Exception as e:
            logger.debug(f"Failed to cache robots.txt: {e}")
