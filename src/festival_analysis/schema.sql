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
  location_country  TEXT,
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
ALTER TABLE artists ADD COLUMN IF NOT EXISTS country        TEXT;
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

-- Country → continent lookup (keyed on RA's location_country strings)
CREATE TABLE IF NOT EXISTS countries (
  country_name TEXT PRIMARY KEY,
  iso2         TEXT,  -- ISO 3166-1 alpha-2 (NULL for non-standard entries like Streamland)
  continent    TEXT   -- 'Europe','North America','South America','Africa','Asia','Oceania','Online'
);

INSERT OR IGNORE INTO countries (country_name, iso2, continent) VALUES
  -- Europe
  ('Albania',                 'AL', 'Europe'),
  ('Andorra',                 'AD', 'Europe'),
  ('Austria',                 'AT', 'Europe'),
  ('Belgium',                 'BE', 'Europe'),
  ('Bulgaria',                'BG', 'Europe'),
  ('Croatia',                 'HR', 'Europe'),
  ('Czech Republic',          'CZ', 'Europe'),
  ('Denmark',                 'DK', 'Europe'),
  ('Finland',                 'FI', 'Europe'),
  ('France',                  'FR', 'Europe'),
  ('Germany',                 'DE', 'Europe'),
  ('Greece',                  'GR', 'Europe'),
  ('Hungary',                 'HU', 'Europe'),
  ('Ireland',                 'IE', 'Europe'),
  ('Italy',                   'IT', 'Europe'),
  ('Kosovo',                  'XK', 'Europe'),  -- XK is widely used but not official ISO
  ('Lithuania',               'LT', 'Europe'),
  ('Malta',                   'MT', 'Europe'),
  ('Netherlands',             'NL', 'Europe'),
  ('Norway',                  'NO', 'Europe'),
  ('Poland',                  'PL', 'Europe'),
  ('Portugal',                'PT', 'Europe'),
  ('Romania',                 'RO', 'Europe'),
  ('Slovenia',                'SI', 'Europe'),
  ('Spain',                   'ES', 'Europe'),
  ('Sweden',                  'SE', 'Europe'),
  ('Switzerland',             'CH', 'Europe'),
  ('United Kingdom',          'GB', 'Europe'),
  -- North America
  ('Canada',                  'CA', 'North America'),
  ('Costa Rica',              'CR', 'North America'),
  ('Mexico',                  'MX', 'North America'),
  ('United States of America','US', 'North America'),
  -- South America
  ('Brazil',                  'BR', 'South America'),
  ('Chile',                   'CL', 'South America'),
  ('Colombia',                'CO', 'South America'),
  ('Peru',                    'PE', 'South America'),
  -- Africa
  ('Ethiopia',                'ET', 'Africa'),
  ('Morocco',                 'MA', 'Africa'),
  ('South Africa',            'ZA', 'Africa'),
  ('Tanzania',                'TZ', 'Africa'),
  -- Asia
  ('China',                   'CN', 'Asia'),
  ('India',                   'IN', 'Asia'),
  ('Israel',                  'IL', 'Asia'),
  ('Japan',                   'JP', 'Asia'),
  ('Singapore',               'SG', 'Asia'),
  ('South Korea',             'KR', 'Asia'),
  ('United Arab Emirates',    'AE', 'Asia'),
  -- Oceania
  ('Australia',               'AU', 'Oceania'),
  -- Online / virtual (RA uses "Streamland" for digital events)
  ('Streamland',              NULL, 'Online');

-- One row per festival × edition_year, collapsing all RA sub-events.
-- For single-weekend festivals each edition is one RA event; for series
-- festivals (Brunch Electronik, PIV, etc.) ra_events counts all occurrences
-- in that calendar year.
CREATE OR REPLACE VIEW editions AS
SELECT
  f.festival_id,
  f.name                            AS festival_name,
  f.size_band,
  fi.edition_year,
  MIN(fi.start_date)                AS start_date,
  MAX(fi.end_date)                  AS end_date,
  -- The modal country/city/continent covers the main festival location
  -- (mode via arg_max on the most common value)
  arg_max(fi.location_country,
    cnt_country)                    AS location_country,
  arg_max(c.continent,
    cnt_country)                    AS location_continent,
  arg_max(fi.location_city,
    cnt_city)                       AS location_city,
  COUNT(DISTINCT fi.festival_event_id) AS ra_events,
  COUNT(DISTINCT le.artist_id)         AS unique_artists
FROM festivals f
JOIN festival_events fi USING (festival_id)
JOIN (
  -- per-edition country counts for mode selection
  SELECT festival_id, edition_year, location_country,
         COUNT(*) AS cnt_country
  FROM festival_events
  GROUP BY festival_id, edition_year, location_country
) cc USING (festival_id, edition_year, location_country)
JOIN (
  -- per-edition city counts for mode selection
  SELECT festival_id, edition_year, location_city,
         COUNT(*) AS cnt_city
  FROM festival_events
  GROUP BY festival_id, edition_year, location_city
) ci USING (festival_id, edition_year, location_city)
LEFT JOIN countries c ON fi.location_country = c.country_name
LEFT JOIN lineup_entries le ON fi.festival_event_id = le.festival_event_id
GROUP BY f.festival_id, f.name, f.size_band, fi.edition_year;

CREATE OR REPLACE VIEW artist_stats AS
SELECT
  a.artist_id,
  a.display_name,
  a.country,
  a.area,
  a.ra_status,
  a.gender,
  a.race,
  COUNT(DISTINCT fi.festival_id)        AS festivals_count,
  COUNT(DISTINCT le.festival_event_id)  AS bookings_count,
  MIN(fi.edition_year)                  AS first_year,
  MAX(fi.edition_year)                  AS last_year,
  MAX(fi.edition_year) - MIN(fi.edition_year) AS years_span
FROM artists a
JOIN lineup_entries le ON a.artist_id = le.artist_id
JOIN festival_events fi ON le.festival_event_id = fi.festival_event_id
GROUP BY
  a.artist_id, a.display_name, a.country, a.area,
  a.ra_status, a.gender, a.race;
