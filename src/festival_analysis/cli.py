from __future__ import annotations

import logging

import typer

from . import db, enrich as enrich_mod, ingest as ingest_mod
from .config import DB_PATH, FESTIVALS_CSV
from .ra_client import RAClient
from .resolve import resolve_all

app = typer.Typer(help="Festival analysis data collection CLI")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command("init-db")
def init_db_cmd(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """Create the DuckDB schema."""
    _setup_logging(verbose)
    con = db.connect()
    db.init_schema(con)
    typer.echo(f"initialised {DB_PATH}")


@app.command("resolve-slugs")
def resolve_slugs_cmd(
    refresh: bool = typer.Option(False, "--refresh", help="Bypass cache"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Auto-propose RA slug/club id mappings into source-data/festivals.csv."""
    _setup_logging(verbose)
    with RAClient(refresh=refresh) as client:
        out = resolve_all(client)
    typer.echo(f"wrote {out} — review and edit before running ingest")


@app.command("fetch")
def fetch_cmd(
    festival: str | None = typer.Option(None, "--festival"),
    since: int | None = typer.Option(
        None, "--since", help="Single year to fetch (e.g. 2024)"
    ),
    through: int | None = typer.Option(
        None, "--through", help="Inclusive upper bound when used with --since"
    ),
    refresh: bool = typer.Option(False, "--refresh"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Populate the on-disk RA cache (and raw_events table) without parsing."""
    _setup_logging(verbose)
    first, last = _year_range(since, through)
    ingest_mod.run(
        festival_filter=festival,
        refresh=refresh,
        first_year=first,
        last_year=last,
    )


@app.command("ingest")
def ingest_cmd(
    festival: str | None = typer.Option(None, "--festival"),
    since: int | None = typer.Option(None, "--since"),
    through: int | None = typer.Option(None, "--through"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Parse cached RA responses into the relational tables."""
    _setup_logging(verbose)
    first, last = _year_range(since, through)
    ingest_mod.run(festival_filter=festival, first_year=first, last_year=last)


def _year_range(since: int | None, through: int | None) -> tuple[int, int | None]:
    """--since alone = single year; --since + --through = inclusive range;
    neither = full history (2005..today, handled downstream)."""
    if since is None:
        return 2005, None
    if through is None:
        return since, since
    return since, through


@app.command("run")
def run_cmd(
    refresh: bool = typer.Option(False, "--refresh"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """init-db + ingest in one shot (assumes festivals.csv is already curated)."""
    _setup_logging(verbose)
    con = db.connect()
    db.init_schema(con)
    ingest_mod.run(refresh=refresh)


@app.command("enrich")
def enrich_cmd(
    refresh: bool = typer.Option(False, "--refresh", help="Re-fetch already-enriched artists"),
    batch_size: int = typer.Option(20, "--batch-size", help="Artists per GraphQL request"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Fetch RA artist profiles (country, genres, social links) for all known artists."""
    _setup_logging(verbose)
    enrich_mod.run(refresh=refresh, batch_size=batch_size)


@app.command("status")
def status_cmd() -> None:
    """Print row counts and resolution stats."""
    con = db.connect()
    db.init_schema(con)
    for table in ("festivals", "festival_instances", "artists", "lineup_entries", "raw_events"):
        count = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        typer.echo(f"{table:<20} {count}")
    resolved = con.execute(
        "SELECT count(*) FROM festivals WHERE ra_club_id IS NOT NULL"
    ).fetchone()[0]
    total = con.execute("SELECT count(*) FROM festivals").fetchone()[0]
    typer.echo(f"festivals with ra_club_id: {resolved}/{total}")
    typer.echo(f"festivals.csv: {FESTIVALS_CSV}")


if __name__ == "__main__":
    app()
