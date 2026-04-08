from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import queries
from .config import CACHE_DIR, RA_ENDPOINT, RA_USER_AGENT

logger = logging.getLogger(__name__)


class RAClientError(RuntimeError):
    pass


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class RAClient:
    def __init__(
        self,
        cache_dir: Path | None = None,
        rate_limit_per_sec: float = 1.0,
        refresh: bool = False,
    ) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh
        self._min_gap = 1.0 / rate_limit_per_sec if rate_limit_per_sec > 0 else 0.0
        self._last_request_at = 0.0
        self._client = httpx.Client(
            timeout=30.0,
            headers={
                "Content-Type": "application/json",
                "User-Agent": RA_USER_AGENT,
                "Referer": "https://ra.co/",
                "Origin": "https://ra.co",
                "ra-content-language": "en",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RAClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---------- caching ----------

    @staticmethod
    def cache_key(query: str, variables: dict) -> str:
        blob = json.dumps(
            {"q": query, "v": variables}, sort_keys=True, default=str
        ).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> dict | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            logger.warning("corrupt cache file %s, ignoring", path)
            return None

    def _write_cache(self, key: str, payload: dict) -> None:
        self._cache_path(key).write_text(json.dumps(payload))

    # ---------- HTTP ----------

    def _throttle(self) -> None:
        if self._min_gap <= 0:
            return
        gap = time.monotonic() - self._last_request_at
        if gap < self._min_gap:
            time.sleep(self._min_gap - gap)
        self._last_request_at = time.monotonic()

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def _post_raw(self, payload: dict) -> dict:
        self._throttle()
        resp = self._client.post(RA_ENDPOINT, json=payload)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        if resp.status_code >= 400:
            raise RAClientError(
                f"RA GraphQL error {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def post(self, query: str, variables: dict) -> dict:
        key = self.cache_key(query, variables)
        if not self.refresh:
            cached = self._read_cache(key)
            if cached is not None:
                return cached
        body = self._post_raw({"query": query, "variables": variables})
        if "errors" in body and body["errors"]:
            raise RAClientError(f"RA GraphQL errors: {body['errors']}")
        self._write_cache(key, body)
        return body

    # ---------- high level ----------

    def search(self, term: str, indices: list[str] | None = None) -> list[dict]:
        idx = indices or ["CLUB", "PROMOTER"]
        body = self.post(queries.SEARCH, {"searchTerm": term, "indices": idx})
        return body.get("data", {}).get("search", []) or []

    # RA's GraphQL has a per-entity `events(year, type)` field on Promoter
    # and Venue. This is the correct way to pull historical events for a
    # festival — the `eventListings.filters.clubs` filter that we used
    # previously is silently ignored by the server and returns all global
    # events in the date range.

    def fetch_events_for_promoter_year(
        self,
        promoter_id: str,
        year: int,
        limit: int = 500,
    ) -> list[dict]:
        body = self.post(
            queries.GET_PROMOTER_EVENTS,
            {"id": str(promoter_id), "year": year, "limit": limit},
        )
        promoter = (body.get("data") or {}).get("promoter") or {}
        return promoter.get("events") or []

    def fetch_events_for_venue_year(
        self,
        venue_id: str,
        year: int,
        limit: int = 500,
    ) -> list[dict]:
        body = self.post(
            queries.GET_VENUE_EVENTS,
            {"id": str(venue_id), "year": year, "limit": limit},
        )
        venue = (body.get("data") or {}).get("venue") or {}
        return venue.get("events") or []

    def fetch_events_for_entity(
        self,
        ra_slug: str,
        ra_id: str,
        first_year: int = 2005,
        last_year: int | None = None,
    ) -> Iterator[dict]:
        """Yield raw `Event` dicts for a promoter or venue across a year range.

        `ra_slug` is expected to start with `promoters/` or `clubs/` (the
        latter maps to RA's `venue(id)` root field).
        """
        last = last_year if last_year is not None else date.today().year
        kind = ra_slug.split("/", 1)[0].lower() if ra_slug else "promoters"
        if kind == "events":
            yield from self._fetch_single_event(ra_id)
            return
        for year in range(first_year, last + 1):
            if kind == "clubs":
                events = self.fetch_events_for_venue_year(ra_id, year)
            else:
                events = self.fetch_events_for_promoter_year(ra_id, year)
            logger.debug("%s/%s  %d → %d events", kind, ra_id, year, len(events))
            for ev in events:
                yield ev

    def _fetch_single_event(self, event_id: str) -> list[dict]:
        """Fetch one RA event by ID and return it shaped like a promoter events list."""
        body = self.post(queries.GET_EVENT_DETAIL, {"id": event_id})
        ev = (body.get("data") or {}).get("event")
        if not ev:
            logger.warning("event %s not found", event_id)
            return []
        return [ev]

    def fetch_event_detail(self, event_id: str) -> dict:
        return self.post(queries.GET_EVENT_DETAIL, {"id": event_id})
