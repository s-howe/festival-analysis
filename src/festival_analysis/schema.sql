CREATE TABLE IF NOT EXISTS festivals (
  festival_id   BIGINT PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  size          INTEGER,  -- legacy, unused
  size_band     TEXT,     -- e.g. '3 - M' (see size_bands table)
  ra_slug       TEXT,
  ra_club_id    TEXT,
  notes         TEXT
);

CREATE TABLE IF NOT EXISTS festival_instances (
  instance_id      BIGINT PRIMARY KEY,
  festival_id      BIGINT NOT NULL REFERENCES festivals(festival_id),
  ra_event_id      TEXT,
  edition_year     INTEGER,
  start_date       DATE,
  end_date         DATE,
  location_country TEXT,
  location_city    TEXT,
  venue_name       TEXT,
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
  entry_id    BIGINT PRIMARY KEY,
  instance_id BIGINT NOT NULL REFERENCES festival_instances(instance_id),
  artist_id   BIGINT NOT NULL REFERENCES artists(artist_id),
  raw_billing TEXT,
  UNIQUE (instance_id, artist_id)
);

CREATE TABLE IF NOT EXISTS raw_events (
  cache_key   TEXT PRIMARY KEY,
  festival_id BIGINT,
  fetched_at  TIMESTAMP DEFAULT current_timestamp,
  payload     JSON
);

-- Enrichment columns (idempotent ALTER TABLE)
ALTER TABLE artists ADD COLUMN IF NOT EXISTS country        TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS area           TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS ra_status      TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS instagram_url  TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS soundcloud_url TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS twitter_url    TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS gender         TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS race           TEXT;
ALTER TABLE artists ADD COLUMN IF NOT EXISTS enriched_at    TIMESTAMP;

DROP TABLE IF EXISTS artist_genres;

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

CREATE OR REPLACE VIEW artist_stats AS
SELECT
  a.artist_id,
  a.display_name,
  a.country,
  a.area,
  a.ra_status,
  a.gender,
  a.race,
  COUNT(DISTINCT fi.festival_id)  AS festivals_count,
  COUNT(DISTINCT le.instance_id)  AS bookings_count,
  MIN(fi.edition_year)            AS first_year,
  MAX(fi.edition_year)            AS last_year,
  MAX(fi.edition_year) - MIN(fi.edition_year) AS years_span
FROM artists a
JOIN lineup_entries le ON a.artist_id = le.artist_id
JOIN festival_instances fi ON le.instance_id = fi.instance_id
GROUP BY
  a.artist_id, a.display_name, a.country, a.area,
  a.ra_status, a.gender, a.race;
