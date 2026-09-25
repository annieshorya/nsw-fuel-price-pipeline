-- =====================================================================
-- 02_load_raw.sql  —  land the files in Snowflake (RAW layer)
--
-- Pattern: file → internal STAGE → COPY INTO a raw table.
-- Raw tables keep every column as text so a bad value never blocks a
-- load; typing and cleaning happen in STAGING (03).
--
-- BEFORE RUNNING PART B/C, upload files to the stage in Snowsight:
--   Data/Catalog » Databases » FUEL_DB » RAW » Stages » LANDING » "+ Files"
--   1. stage2-realtime-pipeline/sample-data/fuelPrice_data.csv   (API snapshot, always)
--   2. Optional, for trends: monthly FuelCheck price-history files saved as CSV,
--      named like fuelcheck_pricehistory_nov2025.csv (lower case). See warehouse/README.md.
-- =====================================================================

USE ROLE SYSADMIN;
USE WAREHOUSE FUEL_WH;
USE SCHEMA FUEL_DB.RAW;

-- ---------------------------------------------------------------------
-- PART A — file format, stage and raw tables (safe to re-run)
-- ---------------------------------------------------------------------
CREATE FILE FORMAT IF NOT EXISTS RAW.CSV_WITH_HEADER
  TYPE = CSV
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'   -- addresses contain commas, so they are quoted
  TRIM_SPACE = TRUE
  EMPTY_FIELD_AS_NULL = TRUE
  NULL_IF = ('', 'NULL', 'null', 'nan', 'NaN');

CREATE STAGE IF NOT EXISTS RAW.LANDING
  FILE_FORMAT = RAW.CSV_WITH_HEADER
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Upload CSVs here, then COPY INTO the raw tables';

-- Live FuelCheck API pull saved by publisher.py (one row per station x fuel type)
CREATE TABLE IF NOT EXISTS RAW.API_PRICE_SNAPSHOT (
  STATIONID            VARCHAR,
  BRANDID              VARCHAR,
  BRAND                VARCHAR,
  CODE                 VARCHAR,
  NAME                 VARCHAR,
  ADDRESS              VARCHAR,
  LATITUDE             VARCHAR,
  LONGITUDE            VARCHAR,
  IS_ADBLUE_AVAILABLE  VARCHAR,
  FUELTYPE             VARCHAR,
  PRICE                VARCHAR,
  LASTUPDATED          VARCHAR,
  _SOURCE_FILE         VARCHAR,        -- which file the row came from (lineage)
  _LOADED_AT           TIMESTAMP_LTZ   -- when it was loaded
);

-- Monthly FuelCheck price-history files (one row per price change)
-- Column order in the NSW files: ServiceStationName, Address, Suburb, Postcode,
-- Brand, FuelCode, PriceUpdatedDate, Price  — check row 1 of your CSV matches.
CREATE TABLE IF NOT EXISTS RAW.PRICE_HISTORY (
  SERVICE_STATION_NAME VARCHAR,
  ADDRESS              VARCHAR,
  SUBURB               VARCHAR,
  POSTCODE             VARCHAR,
  BRAND                VARCHAR,
  FUEL_CODE            VARCHAR,
  PRICE_UPDATED_DATE   VARCHAR,
  PRICE                VARCHAR,
  _SOURCE_FILE         VARCHAR,
  _LOADED_AT           TIMESTAMP_LTZ
);

-- What is sitting in the stage right now?
LIST @RAW.LANDING;

-- ---------------------------------------------------------------------
-- PART B — load the API snapshot
-- COPY remembers which files it already loaded (for 64 days), so running
-- this twice does NOT duplicate rows. Check "errors_seen" in the result.
-- ---------------------------------------------------------------------
COPY INTO RAW.API_PRICE_SNAPSHOT
FROM (
  SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
         METADATA$FILENAME, CURRENT_TIMESTAMP()
  FROM @RAW.LANDING
)
PATTERN = '.*fuelPrice_data.*[.]csv'
ON_ERROR = 'CONTINUE';

SELECT COUNT(*) AS api_rows FROM RAW.API_PRICE_SNAPSHOT;   -- expect 10,432 for the repo sample file

-- ---------------------------------------------------------------------
-- PART C — load the monthly price-history CSVs (optional, for trend pages)
-- ---------------------------------------------------------------------
COPY INTO RAW.PRICE_HISTORY
FROM (
  SELECT $1, $2, $3, $4, $5, $6, $7, $8,
         METADATA$FILENAME, CURRENT_TIMESTAMP()
  FROM @RAW.LANDING
)
PATTERN = '.*price_?history.*[.]csv'
ON_ERROR = 'CONTINUE';

SELECT _SOURCE_FILE, COUNT(*) AS rows_loaded
FROM RAW.PRICE_HISTORY
GROUP BY 1
ORDER BY 1;

-- Peek at the raw text before cleaning (look at the date format!)
SELECT * FROM RAW.PRICE_HISTORY LIMIT 20;

-- If a load went wrong: TRUNCATE TABLE RAW.PRICE_HISTORY;  (this also clears COPY's
-- "already loaded" memory for that table), fix the file, re-upload, and re-run the COPY.
