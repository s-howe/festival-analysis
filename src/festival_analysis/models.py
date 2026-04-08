from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class RAArtist(BaseModel):
    id: str | None = None
    name: str


class RAVenue(BaseModel):
    id: str | None = None
    name: str | None = None
    city: str | None = None
    country: str | None = None


class RAEvent(BaseModel):
    id: str
    title: str | None = None
    event_date: date | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    venue: RAVenue = Field(default_factory=RAVenue)
    artists: list[RAArtist] = Field(default_factory=list)
