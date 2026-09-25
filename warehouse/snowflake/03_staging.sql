-- =====================================================================
-- 03_staging.sql  —  typed, cleaned, de-duplicated views (STAGING layer)
--
-- Rule of this layer: bad rows are LABELLED (dq_issue column), not
-- silently dropped. Marts keep only rows where dq_issue IS NULL, and
-- 05_data_quality_checks.sql reports how many rows failed and why.
-- These are views, so re-running 04 always picks up newly loaded raw data.
-- =====================================================================

USE ROLE SYSADMIN;
USE WAREHOUSE FUEL_WH;
USE SCHEMA FUEL_DB.STAGING;

-- ---------------------------------------------------------------------
-- API snapshot: one row per station x fuel type
-- Station identity = the API's own station id. (Name + postcode is NOT
-- unique: e.g. there are three different "7-Eleven Blacktown" stations.)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW STAGING.STG_API_PRICES AS
WITH typed AS (
  SELECT
    TRIM(STATIONID)                                                     AS station_id,
    TRIM(CODE)                                                          AS station_code,
    -- strip "(Members Only)" and collapse double spaces ("Shell Reddy  Express Glendale")
    TRIM(REGEXP_REPLACE(REGEXP_REPLACE(NAME, '\\(Members Only\\)', '', 1, 0, 'i'), '\\s+', ' ')) AS station_name,
    CONTAINS(UPPER(NAME), '(MEMBERS ONLY)')                             AS is_members_only,
    TRIM(BRAND)                                                         AS brand,
    TRIM(ADDRESS)                                                       AS address,
    -- "208-212 Pacific Hwy North, Coffs Harbour NSW 2450" → Coffs Harbour / NSW / 2450
    INITCAP(TRIM(REGEXP_SUBSTR(ADDRESS, ',\\s*([^,]*)\\s+(NSW|ACT)\\s+[0-9]{4}\\s*$', 1, 1, 'e', 1))) AS suburb,
    REGEXP_SUBSTR(ADDRESS, '(NSW|ACT)\\s+[0-9]{4}\\s*$', 1, 1, 'e', 1)  AS state,
    REGEXP_SUBSTR(ADDRESS, '([0-9]{4})\\s*$', 1, 1, 'e', 1)             AS postcode,
    TRY_TO_DOUBLE(LATITUDE)                                             AS latitude,
    TRY_TO_DOUBLE(LONGITUDE)                                            AS longitude,
    TRY_TO_BOOLEAN(IS_ADBLUE_AVAILABLE)                                 AS has_adblue,
    UPPER(TRIM(FUELTYPE))                                               AS fuel_code,
    TRY_TO_DECIMAL(PRICE, 7, 2)                                         AS price_cents,
    TRY_TO_TIMESTAMP_NTZ(LASTUPDATED, 'DD/MM/YYYY HH24:MI:SS')          AS last_updated_at,
    _SOURCE_FILE                                                        AS source_file,
    _LOADED_AT                                                          AS loaded_at
  FROM RAW.API_PRICE_SNAPSHOT
),
deduped AS (
  -- if the same station/fuel appears more than once (e.g. two snapshots loaded), keep the newest price
  SELECT *
  FROM typed
  QUALIFY ROW_NUMBER() OVER (
            PARTITION BY station_id, fuel_code
            ORDER BY last_updated_at DESC NULLS LAST, loaded_at DESC) = 1
)
SELECT
  *,
  UPPER(station_name) || '|' || COALESCE(postcode, '????')              AS match_key,   -- used to match history rows
  -- same price on 3+ fuel types at the same second looks like a placeholder, not a real price
  COUNT(*) OVER (PARTITION BY station_id, last_updated_at, price_cents) >= 3 AS is_suspect_placeholder,
  CASE
    WHEN station_id IS NULL                                THEN 'missing station id'
    WHEN latitude IS NULL OR longitude IS NULL             THEN 'missing or invalid coordinates'
    WHEN NOT (latitude  BETWEEN -38 AND -28
          AND longitude BETWEEN 140 AND 154)               THEN 'outside NSW/ACT bounding box'
    WHEN fuel_code IS NULL                                 THEN 'missing fuel type'
    WHEN price_cents IS NULL                               THEN 'unparseable price'
    WHEN last_updated_at IS NULL                           THEN 'unparseable timestamp'
    WHEN fuel_code <> 'EV'
     AND price_cents NOT BETWEEN 50 AND 500                THEN 'price outside 50-500 c/L'
  END                                                                   AS dq_issue
FROM deduped;


-- ---------------------------------------------------------------------
-- Monthly price history: one row per price change event
-- (the history files have no station id, only name / address / postcode)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW STAGING.STG_PRICE_HISTORY AS
WITH typed AS (
  SELECT
    TRIM(REGEXP_REPLACE(REGEXP_REPLACE(SERVICE_STATION_NAME, '\\(Members Only\\)', '', 1, 0, 'i'), '\\s+', ' ')) AS station_name,
    CONTAINS(UPPER(SERVICE_STATION_NAME), '(MEMBERS ONLY)')             AS is_members_only,
    TRIM(REGEXP_REPLACE(ADDRESS, '\\s+', ' '))                          AS address,
    INITCAP(TRIM(SUBURB))                                               AS suburb,
    TO_VARCHAR(TRY_TO_NUMBER(POSTCODE))                                 AS postcode,
    TRIM(BRAND)                                                         AS brand,
    UPPER(TRIM(FUEL_CODE))                                              AS fuel_code,
    PRICE_UPDATED_DATE                                                  AS price_updated_raw,   -- kept for debugging
    -- Excel exports dates in different shapes; try the common ones.
    -- Easiest: format the column as yyyy-mm-dd hh:mm:ss in Excel before saving as CSV.
    COALESCE(
      TRY_TO_TIMESTAMP_NTZ(PRICE_UPDATED_DATE, 'YYYY-MM-DD HH24:MI:SS'),
      TRY_TO_TIMESTAMP_NTZ(PRICE_UPDATED_DATE, 'YYYY-MM-DD HH24:MI'),
      TRY_TO_TIMESTAMP_NTZ(PRICE_UPDATED_DATE, 'DD/MM/YYYY HH24:MI:SS'),
      TRY_TO_TIMESTAMP_NTZ(PRICE_UPDATED_DATE, 'DD/MM/YYYY HH24:MI'),
      TRY_TO_TIMESTAMP_NTZ(PRICE_UPDATED_DATE, 'DD/MM/YYYY HH12:MI:SS AM'),
      TRY_TO_TIMESTAMP_NTZ(PRICE_UPDATED_DATE, 'DD/MM/YYYY HH12:MI AM')
    )                                                                   AS price_updated_at,
    TRY_TO_DECIMAL(PRICE, 7, 2)                                         AS price_cents,
    _SOURCE_FILE                                                        AS source_file,
    _LOADED_AT                                                          AS loaded_at
  FROM RAW.PRICE_HISTORY
  WHERE COALESCE(SERVICE_STATION_NAME, FUEL_CODE, PRICE) IS NOT NULL    -- skip blank rows Excel leaves at the end
),
deduped AS (
  -- exact duplicate rows (e.g. the same month loaded twice) are removed here.
  -- The course version (Stage 1) ran drop_duplicates on the last monthly file
  -- only, not on the combined data — this fixes that.
  SELECT *
  FROM typed
  QUALIFY ROW_NUMBER() OVER (
            PARTITION BY station_name, address, postcode, fuel_code, price_updated_raw, price_cents
            ORDER BY loaded_at DESC) = 1
)
SELECT
  *,
  UPPER(station_name) || '|' || COALESCE(postcode, '????')              AS match_key,
  UPPER(station_name) || '|' || COALESCE(postcode, '????')
                      || '|' || UPPER(COALESCE(address, ''))            AS hist_station_key,
  CASE
    WHEN station_name IS NULL OR station_name = ''         THEN 'missing station name'
    WHEN postcode IS NULL                                  THEN 'missing or invalid postcode'
    WHEN fuel_code IS NULL                                 THEN 'missing fuel type'
    WHEN price_updated_at IS NULL                          THEN 'unparseable timestamp'
    WHEN price_cents IS NULL                               THEN 'unparseable price'
    WHEN fuel_code <> 'EV'
     AND price_cents NOT BETWEEN 50 AND 500                THEN 'price outside 50-500 c/L'
  END                                                                   AS dq_issue
FROM deduped;


-- ---------------------------------------------------------------------
-- Which API station does each history station belong to?
-- Match on name + postcode, but ONLY when exactly one API station has that
-- name + postcode. Ambiguous or unmatched history stations get their own id
-- ("H-...") so their prices are still kept, just without map coordinates.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW STAGING.STG_HISTORY_STATION_MAP AS
WITH api_keys AS (
  SELECT match_key,
         MIN(station_id)            AS api_station_id,
         COUNT(DISTINCT station_id) AS n_api_stations
  FROM STAGING.STG_API_PRICES
  WHERE dq_issue IS NULL
  GROUP BY match_key
),
hist_stations AS (
  SELECT DISTINCT hist_station_key, match_key
  FROM STAGING.STG_PRICE_HISTORY
  WHERE dq_issue IS NULL
)
SELECT
  h.hist_station_key,
  CASE WHEN a.n_api_stations = 1 THEN a.api_station_id
       ELSE 'H-' || LEFT(MD5(h.hist_station_key), 12)
  END                                                                   AS station_id,
  CASE WHEN a.n_api_stations = 1 THEN 'matched to API station'
       WHEN a.n_api_stations > 1 THEN 'ambiguous (several API stations share name + postcode)'
       ELSE 'no API match'
  END                                                                   AS match_status
FROM hist_stations h
LEFT JOIN api_keys a
  ON a.match_key = h.match_key;


-- Quick look: how many rows passed, and why the rest failed
SELECT 'api' AS source, COALESCE(dq_issue, 'OK') AS outcome, COUNT(*) AS n FROM STAGING.STG_API_PRICES GROUP BY 1, 2
UNION ALL
SELECT 'history', COALESCE(dq_issue, 'OK'), COUNT(*) FROM STAGING.STG_PRICE_HISTORY GROUP BY 1, 2
ORDER BY 1, 3 DESC;
