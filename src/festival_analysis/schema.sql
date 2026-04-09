CREATE TABLE IF NOT EXISTS festivals (
  festival_id   BIGINT PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  size_band     TEXT,     -- e.g. '3 - M' (see size_bands table)
  ra_slug       TEXT,
  ra_club_id    TEXT,
  notes         TEXT
);

CREATE TABLE IF NOT EXISTS festival_events (
  festival_event_id BIGINT PRIMARY KEY,
  festival_id       BIGINT NOT NULL REFERENCES festivals(festival_id),
  ra_event_id       TEXT,
  edition_year      INTEGER,
  start_date        DATE,
  end_date          DATE,
  location_country  TEXT,   -- iso2 code; join to countries for name/continent
  location_city     TEXT,
  venue_name        TEXT,
  UNIQUE (festival_id, ra_event_id)
);

CREATE TABLE IF NOT EXISTS artists (
  artist_id        BIGINT PRIMARY KEY,
  ra_artist_id     TEXT,
  display_name     TEXT NOT NULL,
  normalized_name  TEXT NOT NULL,
  UNIQUE (normalized_name, ra_artist_id)
);

CREATE TABLE IF NOT EXISTS lineup_entries (
  entry_id          BIGINT PRIMARY KEY,
  festival_event_id BIGINT NOT NULL REFERENCES festival_events(festival_event_id),
  artist_id         BIGINT NOT NULL REFERENCES artists(artist_id),
  raw_billing       TEXT,
  UNIQUE (festival_event_id, artist_id)
);

CREATE TABLE IF NOT EXISTS raw_events (
  cache_key   TEXT PRIMARY KEY,
  festival_id BIGINT,
  fetched_at  TIMESTAMP DEFAULT current_timestamp,
  payload     JSON
);

-- Enrichment columns (idempotent ALTER TABLE)
ALTER TABLE artists ADD COLUMN IF NOT EXISTS country        TEXT;  -- iso2 code
ALTER TABLE artists ADD COLUMN IF NOT EXISTS area           TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS ra_status      TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS instagram_url  TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS soundcloud_url TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS twitter_url    TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS gender         TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS race           TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS enriched_at    TIMESTAMP;

CREATE TABLE IF NOT EXISTS size_bands (
  label        TEXT PRIMARY KEY,
  min_capacity INTEGER NOT NULL,
  max_capacity INTEGER,  -- NULL = no upper bound
  description  TEXT
);

INSERT OR IGNORE INTO size_bands VALUES
  ('1 - XS', 0,     2499,  'under 2,500'),
  ('2 - S',  2500,  9999,  '2,500 – 10,000'),
  ('3 - M',  10000, 29999, '10,000 – 30,000'),
  ('4 - L',  30000, 74999, '30,000 – 75,000'),
  ('5 - XL', 75000, NULL,  '75,000+');

-- Country lookup. `country` is the iso2 code (PK); `name` is the full name.
-- XO = online/virtual (RA "Streamland"); XK = Kosovo (widely-used unofficial code).
-- Seeded from source-data/countries.csv by db.init_schema() — edit the CSV, not this file.
CREATE TABLE IF NOT EXISTS countries (
  country    TEXT PRIMARY KEY,  -- iso2 code
  name       TEXT NOT NULL UNIQUE,
  continent  TEXT,
  population INTEGER
);

-- One row per festival × edition_year, collapsing all RA sub-events.
-- For single-weekend festivals each edition is one RA event; for series
-- festivals (Brunch Electronik, PIV, etc.) ra_events counts all occurrences
-- in that calendar year.
CREATE OR REPLACE VIEW editions AS
SELECT
  f.festival_id,
  f.name                                                    AS festival_name,
  f.size_band,
  fi.edition_year,
  MIN(fi.start_date)                                        AS start_date,
  MAX(fi.end_date)                                          AS end_date,
  -- All location columns use lineup-entry count as the score so that the
  -- sub-event with the most artists (i.e. the main festival day) determines
  -- the reported location — not whichever country has the most RA event pages.
  arg_max(fi.location_country, COALESCE(lc.le_count, 0))   AS location_country,
  arg_max(c.name,              COALESCE(lc.le_count, 0))   AS location_country_name,
  arg_max(c.continent,         COALESCE(lc.le_count, 0))   AS location_continent,
  arg_max(fi.location_city,    COALESCE(lc.le_count, 0))   AS location_city,
  arg_max(fi.ra_event_id,      COALESCE(lc.le_count, 0))   AS primary_event_id,
  COUNT(DISTINCT fi.festival_event_id)                      AS ra_events,
  COUNT(DISTINCT le.artist_id)                              AS unique_artists
FROM festivals f
JOIN festival_events fi USING (festival_id)
LEFT JOIN countries c      ON fi.location_country = c.country
LEFT JOIN lineup_entries le ON fi.festival_event_id = le.festival_event_id
LEFT JOIN (
  SELECT festival_event_id, COUNT(*) AS le_count
  FROM lineup_entries
  GROUP BY festival_event_id
) lc ON fi.festival_event_id = lc.festival_event_id
GROUP BY f.festival_id, f.name, f.size_band, fi.edition_year;

CREATE OR REPLACE VIEW artist_stats AS
SELECT
  a.artist_id,
  a.display_name,
  a.country,        -- iso2 code; join to countries for name/continent
  a.area,
  a.ra_status,
  a.gender,
  a.race,
  COUNT(DISTINCT fi.festival_id)                              AS festivals_count,
  COUNT(DISTINCT le.festival_event_id)                        AS bookings_count,
  COUNT(DISTINCT {'f': fi.festival_id, 'y': fi.edition_year}) AS festival_bookings_count,
  MIN(fi.edition_year)                  AS first_year,
  MAX(fi.edition_year)                  AS last_year,
  MAX(fi.edition_year) - MIN(fi.edition_year) AS years_span
FROM artists a
JOIN lineup_entries le ON a.artist_id = le.artist_id
JOIN festival_events fi ON le.festival_event_id = fi.festival_event_id
GROUP BY
  a.artist_id, a.display_name, a.country, a.area,
  a.ra_status, a.gender, a.race;

CREATE OR REPLACE VIEW edition_lineups AS
SELECT DISTINCT
  le.entry_id,
  fe.festival_id,
  f.name              AS festival_name,
  f.size_band,
  fe.edition_year,
  e.location_country,
  e.location_continent,
  a.artist_id,
  a.display_name,
  a.country           AS artist_country,
  a.area,
  a.ra_status,
  a.gender
FROM lineup_entries le
JOIN festival_events fe USING (festival_event_id)
JOIN festivals f        USING (festival_id)
JOIN artists a          USING (artist_id)
-- editions supplies the main-festival location (arg_max by lineup count).
-- The WHERE keeps only sub-events in that primary country, dropping satellite
-- events in other countries.
JOIN editions e         USING (festival_id, edition_year)
WHERE fe.location_country = e.location_country;
