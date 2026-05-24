# Progress Notes

## Current State

The data collection and enrichment pipeline is complete. The DuckDB database at
`data/festival.duckdb` contains:

| Table / View        | Rows    |
|---------------------|---------|
| festivals           | 134     |
| festival_events     | 5,339   |
| artists             | 13,370  |
| lineup_entries      | 67,414  |
| editions (view)     | 1,018   |
| edition_lineups (view) | 61,872 |

- Year range: 2005–2026
- Enriched artists (RA profile data): 12,897 / 13,370
- Countries lookup: 126 entries

---

## Schema

### Tables

**`festivals`** — one row per festival  
`festival_id, name, size_band, ra_slug, ra_club_id, notes`

**`festival_events`** — one row per RA event page (a single day or stage at a festival)  
`festival_event_id, festival_id, ra_event_id, edition_year, start_date, end_date, location_country (iso2), location_city, venue_name`

> Note: series festivals (e.g. Brunch Electronik, FUSE) have many sub-events per year;
> single-weekend festivals typically have one per year. Satellite events (e.g. Dimensions
> UK warmup parties) are stored here but filtered in the `edition_lineups` view.

**`artists`** — one row per unique artist  
`artist_id, ra_artist_id, display_name, normalized_name, country (iso2), area, ra_status, instagram_url, soundcloud_url, twitter_url, gender, race, enriched_at`

**`lineup_entries`** — one row per artist × festival_event booking  
`entry_id, festival_event_id, artist_id, raw_billing`

**`countries`** — iso2 lookup table, seeded from `source-data/countries.csv`  
`country (iso2 PK), name, continent, population`

**`size_bands`** — capacity tier labels  
`label, min_capacity, max_capacity, description`  
Values: `1 - XS` (<2,500), `2 - S` (2,500–10k), `3 - M` (10k–30k), `4 - L` (30k–75k), `5 - XL` (75k+)

**`raw_events`** — raw JSON cache of RA API responses  
`cache_key, festival_id, fetched_at, payload`

### Views

**`editions`** — one row per festival × year, collapsing all RA sub-events  
Key columns: `festival_id, festival_name, size_band, edition_year, start_date, end_date, location_country, location_country_name, location_continent, location_city, primary_event_id, ra_events, unique_artists`

- `location_*` columns are determined by the sub-event with the **most lineup entries**
  (not event count), so satellite club nights don't pollute the main festival's reported location.
- `primary_event_id` is the `ra_event_id` of that largest sub-event — useful for linking
  back to RA or filtering to the headlining event.

**`artist_stats`** — booking statistics per artist  
Key columns: `artist_id, display_name, country, area, ra_status, gender, race, festivals_count, bookings_count, festival_bookings_count, first_year, last_year, years_span`

- `bookings_count` = raw count of RA event pages (inflated for series festival residents)
- `festival_bookings_count` = count of distinct (festival × year) pairs — comparable across
  artist types; FUSE residents drop from ~260 to ~50, broadly-booked artists barely change.

**`edition_lineups`** — one row per festival × year × artist  
Key columns: `entry_id, festival_id, festival_name, size_band, edition_year, location_country, location_continent, artist_id, display_name, artist_country, area, ra_status, gender`

- `DISTINCT` collapses all sub-events so each artist appears once per edition.
- Filtered to sub-events in the **primary country** (the country of the main festival event)
  to exclude satellite events in other countries.
- Usage: `SELECT * FROM edition_lineups WHERE festival_name='Dekmantel' AND edition_year=2023`

---

## Pipeline

### CLI commands

```bash
uv run festival-analysis init-db          # create/recreate schema + seed countries
uv run festival-analysis resolve-slugs    # auto-propose RA slug/club-id mappings
uv run festival-analysis fetch [--festival NAME] [--refresh]   # populate cache + raw_events
uv run festival-analysis ingest [--festival NAME]              # parse cache → relational tables
uv run festival-analysis enrich [--refresh] [--batch-size 20]  # fetch RA artist profiles
uv run festival-analysis status           # row counts
```

### Data flow

1. `source-data/festivals.csv` — hand-curated list of 134 festivals with RA slugs/club IDs
2. `fetch` — hits RA GraphQL API, writes raw JSON to `.cache/ra/` and `raw_events` table
3. `ingest` — parses raw JSON, resolves country names → iso2, upserts into relational tables
4. `enrich` — batch-fetches RA artist profiles (country, area, status, social links)

### Key files

| File | Purpose |
|------|---------|
| `source-data/festivals.csv` | Festival list with RA identifiers (hand-curated) |
| `source-data/countries.csv` | Country name → iso2 lookup, seeded into DB on init |
| `src/festival_analysis/schema.sql` | DDL + view definitions |
| `src/festival_analysis/db.py` | DuckDB helpers, upsert functions |
| `src/festival_analysis/ingest.py` | Fetch + parse + store pipeline |
| `src/festival_analysis/enrich.py` | RA artist profile enrichment |
| `src/festival_analysis/ra_client.py` | RA GraphQL client with caching + retry |
| `src/festival_analysis/analysis_utils.py` | `query_db(sql)` helper for notebooks |

---

## Known Data Characteristics

### Satellite events
Some festivals (Dimensions, Love International, Dekmantel) run branded club nights and
collaborations throughout the year under the same RA promoter page. These appear as
`festival_events` rows in non-primary countries. The `editions` view and `edition_lineups`
view both handle this correctly — location and lineups are resolved to the main festival.

For instance-level queries wanting only the main festival, filter by `location_country`
matching the value in `editions`, or join through `edition_lineups` directly.

### Series festivals
FUSE, Brunch Electronik, PIV and similar run many events per year under one promoter page.
Raw `bookings_count` inflates resident artists; use `festival_bookings_count` for fair
cross-artist comparisons.

### Split RA promoter pages (Lighthouse Festival)
Lighthouse has two RA promoter pages (`44654` old, `114674` current). The dataset uses
`114674`. Events linked to `44654` are not accessible via RA's archive API — known gap.

### Artist deduplication
B2B billing strings (e.g. "Ben UFO b2b Pearson Sound") are split into individual artists.
`raw_billing` is preserved on the lineup entry for audit. Aliases are treated as separate
artists.

---

## Outstanding / Next Steps

- **EDA**: see `analysis/eda.ipynb` — distributions, booking counts, geographic breakdowns
- **Gender / race enrichment**: columns exist in `artists` table but are empty; requires
  manual or external data input
- **Analysis ideas** (from `context/rough-plan.md`):
  - Tipping point festivals
  - Artist career arc (rise and fall)
  - Local heroes / cultural exporters
  - Freshness (returners vs new faces)
  - Network graphs (festival similarity, artist co-booking)
