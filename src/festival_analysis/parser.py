from __future__ import annotations

from datetime import date, datetime

from .models import RAArtist, RAEvent, RAVenue


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def parse_event_listing(entry: dict) -> RAEvent | None:
    """Parse one entry from `eventListings.data` into an RAEvent."""
    event = entry.get("event") or {}
    event_id = event.get("id")
    if not event_id:
        return None

    venue_raw = event.get("venue") or {}
    area = venue_raw.get("area") or {}
    country = (area.get("country") or {}).get("name")
    venue = RAVenue(
        id=str(venue_raw.get("id")) if venue_raw.get("id") is not None else None,
        name=venue_raw.get("name"),
        city=area.get("name"),
        country=country,
    )

    artists = [
        RAArtist(
            id=str(a.get("id")) if a.get("id") is not None else None,
            name=a.get("name") or "",
        )
        for a in (event.get("artists") or [])
        if a.get("name")
    ]

    return RAEvent(
        id=str(event_id),
        title=event.get("title"),
        event_date=_parse_date(event.get("date") or entry.get("listingDate")),
        venue=venue,
        artists=artists,
    )
