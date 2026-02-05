"""HTTP fetcher with caching and rate limiting."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.models.database import DBCache, get_session
from .robots import RobotsChecker

logger = logging.getLogger(__name__)


class FetchResult:
    """Result of a fetch operation."""

    def __init__(
        self,
        url: str,
        content: Optional[str] = None,
        status_code: int = 0,
        content_type: Optional[str] = None,
        error: Optional[str] = None,
        from_cache: bool = False,
    ):
        self.url = url
        self.content = content
        self.status_code = status_code
        self.content_type = content_type
        self.error = error
        self.from_cache = from_cache

    @property
    def success(self) -> bool:
        return self.content is not None and 200 <= self.status_code < 400


class Fetcher:
    """HTTP fetcher with caching, rate limiting, and robots.txt compliance."""

    def __init__(
        self,
        user_agent: Optional[str] = None,
        respect_robots: bool = True,
        use_cache: bool = True,
    ):
        self.user_agent = user_agent or settings.user_agent
        self.respect_robots = respect_robots
        self.use_cache = use_cache
        self.robots_checker = RobotsChecker(self.user_agent)

        # Rate limiting per domain
        self._domain_last_request: dict[str, datetime] = {}
        self._rate_limit_lock = asyncio.Lock()

    async def fetch(self, url: str) -> FetchResult:
        """Fetch a URL with caching and rate limiting."""
        # Check cache first
        if self.use_cache:
            cached = await self._get_cached(url)
            if cached:
                return cached

        # Check robots.txt
        if self.respect_robots:
            if not await self.robots_checker.can_fetch(url):
                logger.info(f"Blocked by robots.txt: {url}")
                return FetchResult(
                    url=url,
                    error="Blocked by robots.txt",
                    status_code=403,
                )

        # Rate limit
        await self._wait_for_rate_limit(url)

        # Fetch
        result = await self._do_fetch(url)

        # Cache successful results
        if self.use_cache and result.success:
            await self._cache_result(result)

        return result

    async def fetch_pages(
        self,
        base_url: str,
        paths: list[str],
    ) -> dict[str, FetchResult]:
        """Fetch multiple pages from the same domain."""
        results = {}

        for path in paths:
            if path.startswith("http"):
                url = path
            else:
                url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

            result = await self.fetch(url)
            results[url] = result

        return results

    async def _wait_for_rate_limit(self, url: str):
        """Wait to respect rate limiting for the domain."""
        domain = urlparse(url).netloc

        async with self._rate_limit_lock:
            last_request = self._domain_last_request.get(domain)
            if last_request:
                elapsed = (datetime.utcnow() - last_request).total_seconds()
                if elapsed < settings.rate_limit_delay:
                    await asyncio.sleep(settings.rate_limit_delay - elapsed)

            self._domain_last_request[domain] = datetime.utcnow()

    async def _do_fetch(self, url: str) -> FetchResult:
        """Perform the actual HTTP fetch."""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=settings.connect_timeout,
                    read=settings.read_timeout,
                    write=settings.read_timeout,
                    pool=settings.connect_timeout,
                ),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                    },
                )

                content_type = response.headers.get("content-type", "")

                # Only process HTML/text content
                if "text/" not in content_type and "html" not in content_type:
                    return FetchResult(
                        url=url,
                        status_code=response.status_code,
                        content_type=content_type,
                        error=f"Non-text content type: {content_type}",
                    )

                return FetchResult(
                    url=url,
                    content=response.text,
                    status_code=response.status_code,
                    content_type=content_type,
                )

        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching {url}")
            return FetchResult(url=url, error="Timeout", status_code=0)

        except httpx.RequestError as e:
            logger.warning(f"Request error fetching {url}: {e}")
            return FetchResult(url=url, error=str(e), status_code=0)

        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            return FetchResult(url=url, error=str(e), status_code=0)

    async def _get_cached(self, url: str) -> Optional[FetchResult]:
        """Get cached fetch result."""
        try:
            session = get_session()
            cached = session.query(DBCache).filter_by(url=url).first()

            if cached and cached.expires_at > datetime.utcnow():
                result = FetchResult(
                    url=url,
                    content=cached.content,
                    status_code=cached.status_code or 200,
                    content_type=cached.content_type,
                    from_cache=True,
                )
                session.close()
                return result

            session.close()
        except Exception as e:
            logger.debug(f"Cache lookup failed: {e}")

        return None

    async def _cache_result(self, result: FetchResult):
        """Cache a fetch result."""
        try:
            session = get_session()
            expires_at = datetime.utcnow() + timedelta(days=settings.cache_duration_days)

            cached = session.query(DBCache).filter_by(url=result.url).first()
            if cached:
                cached.content = result.content
                cached.content_type = result.content_type
                cached.status_code = result.status_code
                cached.fetched_at = datetime.utcnow()
                cached.expires_at = expires_at
            else:
                cached = DBCache(
                    url=result.url,
                    content=result.content,
                    content_type=result.content_type,
                    status_code=result.status_code,
                    fetched_at=datetime.utcnow(),
                    expires_at=expires_at,
                )
                session.add(cached)

            session.commit()
            session.close()

        except Exception as e:
            logger.debug(f"Failed to cache result: {e}")
