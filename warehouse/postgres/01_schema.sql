-- =====================================================================
-- PostgreSQL warehouse: RAW landing schema.
-- Runs automatically the first time the docker-compose Postgres starts.
-- Same design as the Snowflake layer (warehouse/snowflake/02_load_raw.sql):
-- raw columns are all TEXT so a malformed value never blocks a load;
-- typing, cleaning and de-duplication happen in dbt (dbt/fuel_dbt).
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.api_price_snapshot (
    stationid            TEXT,
    brandid              TEXT,
    brand                TEXT,
    code                 TEXT,
    name                 TEXT,
    address              TEXT,
    latitude             TEXT,
    longitude            TEXT,
    isadblueavailable    TEXT,
    fueltype             TEXT,
    price                TEXT,
    lastupdated          TEXT,
    _source_file         TEXT        NOT NULL,   -- lineage: which file / API pull the row came from
    _loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per file loaded, so re-running the loader never duplicates data
CREATE TABLE IF NOT EXISTS raw.load_log (
    source_file  TEXT PRIMARY KEY,
    row_count    INTEGER     NOT NULL,
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
