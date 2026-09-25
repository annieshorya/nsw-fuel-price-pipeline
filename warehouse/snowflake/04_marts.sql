-- =====================================================================
-- 04_marts.sql  —  star schema for Power BI (MARTS layer)
--
--                      DIM_DATE
--                         |
--   DIM_STATION —— FCT_CURRENT_PRICE   (API snapshot: latest price per station x fuel)
--        |     \—— FCT_PRICE_CHANGE    (history: one row per price change)
--        |      \— FCT_DAILY_PRICE     (history: one row per station x fuel x day)
--   DIM_FUEL_TYPE
--
-- Re-run this whole file after every new load (it rebuilds the tables).
-- =====================================================================

USE ROLE SYSADMIN;
USE WAREHOUSE FUEL_WH;
USE SCHEMA FUEL_DB.MARTS;

-- ---------------------------------------------------------------------
-- DIM_FUEL_TYPE — readable names + a flag to keep EV charging out of c/L averages
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.DIM_FUEL_TYPE AS
WITH known AS (
  SELECT *
  FROM (VALUES
    ('U91', 'Unleaded 91',          'Petrol',   TRUE, 1),
    ('E10', 'Ethanol 94 (E10)',     'Petrol',   TRUE, 2),
    ('P95', 'Premium Unleaded 95',  'Petrol',   TRUE, 3),
    ('P98', 'Premium Unleaded 98',  'Petrol',   TRUE, 4),
    ('E85', 'Ethanol 105 (E85)',    'Petrol',   TRUE, 5),
    ('DL',  'Diesel',               'Diesel',   TRUE, 6),
    ('PDL', 'Premium Diesel',       'Diesel',   TRUE, 7),
    ('B20', 'Biodiesel 20',         'Diesel',   TRUE, 8),
    ('LPG', 'LPG',                  'Gas',      TRUE, 9),
    ('EV',  'EV charging',          'Electric', FALSE, 10)
  ) AS v(fuel_code, fuel_name, fuel_group, is_liquid_fuel, sort_order)
),
seen AS (   -- any code in the data we have not mapped yet still gets a row
  SELECT fuel_code FROM FUEL_DB.STAGING.STG_API_PRICES    WHERE fuel_code IS NOT NULL
  UNION
  SELECT fuel_code FROM FUEL_DB.STAGING.STG_PRICE_HISTORY WHERE fuel_code IS NOT NULL
)
SELECT
  COALESCE(k.fuel_code, s.fuel_code)                  AS fuel_code,
  COALESCE(k.fuel_name, s.fuel_code || ' (unmapped)') AS fuel_name,
  COALESCE(k.fuel_group, 'Other')                     AS fuel_group,
  COALESCE(k.is_liquid_fuel, TRUE)                    AS is_liquid_fuel,
  COALESCE(k.sort_order, 99)                          AS sort_order
FROM known k
FULL OUTER JOIN seen s ON k.fuel_code = s.fuel_code;


-- ---------------------------------------------------------------------
-- DIM_STATION — one row per station.
--   * API stations: id, name, address and coordinates from the API snapshot.
--   * History stations that could not be matched to exactly one API station
--     (see STAGING.STG_HISTORY_STATION_MAP) are added with an "H-" id and no
--     coordinates, so their prices are not lost.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.DIM_STATION AS
WITH api AS (
  SELECT station_id, station_name, brand, address, suburb, state, postcode,
         latitude, longitude, has_adblue, is_members_only, last_updated_at
  FROM FUEL_DB.STAGING.STG_API_PRICES
  WHERE dq_issue IS NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY station_id ORDER BY last_updated_at DESC) = 1
),
matched AS (   -- API stations that also appear in the price history
  SELECT DISTINCT station_id
  FROM FUEL_DB.STAGING.STG_HISTORY_STATION_MAP
  WHERE match_status = 'matched to API station'
),
hist_only AS (
  SELECT m.station_id, h.station_name, h.brand, h.address, h.suburb, h.postcode,
         h.is_members_only, m.match_status, h.price_updated_at
  FROM FUEL_DB.STAGING.STG_PRICE_HISTORY h
  JOIN FUEL_DB.STAGING.STG_HISTORY_STATION_MAP m
    ON m.hist_station_key = h.hist_station_key
  WHERE h.dq_issue IS NULL
    AND m.match_status <> 'matched to API station'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY m.station_id ORDER BY h.price_updated_at DESC) = 1
)
SELECT
  a.station_id, a.station_name, a.brand, a.address, a.suburb, a.state, a.postcode,
  a.latitude, a.longitude, a.has_adblue, a.is_members_only,
  TRUE                      AS in_api_snapshot,
  mt.station_id IS NOT NULL AS in_price_history,
  'API'                     AS station_source
FROM api a
LEFT JOIN matched mt
  ON mt.station_id = a.station_id
UNION ALL
SELECT
  station_id, station_name, brand, address, suburb, NULL, postcode,
  NULL, NULL, NULL, is_members_only,
  FALSE, TRUE,
  'History only: ' || match_status
FROM hist_only;


-- ---------------------------------------------------------------------
-- DIM_DATE — calendar table covering every date in the data
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.DIM_DATE AS
WITH bounds AS (
  SELECT MIN(d) AS start_date, MAX(d) AS end_date
  FROM (
    SELECT last_updated_at::DATE  AS d FROM FUEL_DB.STAGING.STG_API_PRICES    WHERE dq_issue IS NULL
    UNION ALL
    SELECT price_updated_at::DATE AS d FROM FUEL_DB.STAGING.STG_PRICE_HISTORY WHERE dq_issue IS NULL
  )
),
spine AS (
  SELECT DATEADD('day', ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1, b.start_date) AS date_day
  FROM TABLE(GENERATOR(ROWCOUNT => 5000))
  CROSS JOIN bounds b
)
SELECT
  date_day,
  YEAR(date_day)                    AS year,
  QUARTER(date_day)                 AS quarter,
  MONTH(date_day)                   AS month_num,
  MONTHNAME(date_day)               AS month_name,        -- Jan, Feb, ...
  DATE_TRUNC('month', date_day)     AS month_start,
  DAY(date_day)                     AS day_of_month,
  DAYOFWEEKISO(date_day)            AS day_of_week_num,   -- Mon = 1 ... Sun = 7
  DAYNAME(date_day)                 AS day_name,          -- Mon, Tue, ...
  DAYOFWEEKISO(date_day) IN (6, 7)  AS is_weekend
FROM spine
WHERE date_day <= (SELECT end_date FROM bounds);


-- ---------------------------------------------------------------------
-- FCT_CURRENT_PRICE — the API snapshot (grain: station x fuel type)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.FCT_CURRENT_PRICE AS
WITH base AS (
  SELECT *, MAX(last_updated_at) OVER () AS snapshot_as_at   -- roughly when publisher.py pulled the API
  FROM FUEL_DB.STAGING.STG_API_PRICES
  WHERE dq_issue IS NULL
)
SELECT
  station_id,
  fuel_code,
  last_updated_at::DATE                                   AS price_date,
  last_updated_at,
  price_cents,
  DATEDIFF('day', last_updated_at, snapshot_as_at)        AS days_since_update,
  DATEDIFF('day', last_updated_at, snapshot_as_at) > 30   AS is_stale,              -- price not touched in 30+ days
  is_suspect_placeholder,
  snapshot_as_at,
  source_file
FROM base;


-- ---------------------------------------------------------------------
-- FCT_PRICE_CHANGE — price history (grain: one price change event)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.FCT_PRICE_CHANGE AS
SELECT
  m.station_id,
  h.fuel_code,
  h.price_updated_at::DATE        AS price_date,
  h.price_updated_at,
  h.price_cents,
  -- how much the price moved vs. that station's previous price for the same fuel
  h.price_cents - LAG(h.price_cents) OVER (
      PARTITION BY m.station_id, h.fuel_code ORDER BY h.price_updated_at) AS change_cents,
  h.source_file
FROM FUEL_DB.STAGING.STG_PRICE_HISTORY h
JOIN FUEL_DB.STAGING.STG_HISTORY_STATION_MAP m
  ON m.hist_station_key = h.hist_station_key
WHERE h.dq_issue IS NULL;


-- ---------------------------------------------------------------------
-- FCT_DAILY_PRICE — what each station was charging on each day.
-- History only records CHANGES, so averaging FCT_PRICE_CHANGE over-weights
-- stations that change price often. Here each station/fuel gets one row per
-- day, carrying its last known price forward until the next change.
-- (Empty until price history is loaded — that's fine.)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MARTS.FCT_DAILY_PRICE AS
WITH last_of_day AS (   -- if a price changed several times in a day, keep the last one
  SELECT station_id, fuel_code, price_date, price_cents, price_updated_at
  FROM MARTS.FCT_PRICE_CHANGE
  QUALIFY ROW_NUMBER() OVER (
            PARTITION BY station_id, fuel_code, price_date
            ORDER BY price_updated_at DESC) = 1
),
series AS (
  SELECT station_id, fuel_code, MIN(price_date) AS first_date
  FROM last_of_day
  GROUP BY station_id, fuel_code
),
max_day AS (
  SELECT MAX(price_date) AS last_date FROM last_of_day
),
grid AS (               -- every station/fuel x every day from its first price to the end of the data
  SELECT s.station_id, s.fuel_code, d.date_day
  FROM series s
  CROSS JOIN max_day m
  JOIN MARTS.DIM_DATE d
    ON d.date_day BETWEEN s.first_date AND m.last_date
)
SELECT
  g.station_id,
  g.fuel_code,
  g.date_day                                      AS price_date,
  LAST_VALUE(l.price_cents) IGNORE NULLS OVER (
      PARTITION BY g.station_id, g.fuel_code
      ORDER BY g.date_day
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS price_cents,   -- carry forward
  l.price_cents IS NOT NULL                       AS price_changed_that_day
FROM grid g
LEFT JOIN last_of_day l
  ON  l.station_id = g.station_id
  AND l.fuel_code  = g.fuel_code
  AND l.price_date = g.date_day;


-- ---------------------------------------------------------------------
-- DQ_SUMMARY — so Power BI can show a "data quality" page
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW MARTS.DQ_SUMMARY AS
SELECT 'API snapshot' AS source, COALESCE(dq_issue, 'Passed') AS outcome, COUNT(*) AS row_count
FROM FUEL_DB.STAGING.STG_API_PRICES
GROUP BY 1, 2
UNION ALL
SELECT 'Price history', COALESCE(dq_issue, 'Passed'), COUNT(*)
FROM FUEL_DB.STAGING.STG_PRICE_HISTORY
GROUP BY 1, 2;


-- Row counts per table (paste these into the README once you have them)
SELECT 'DIM_STATION'       AS table_name, COUNT(*) AS row_count FROM MARTS.DIM_STATION
UNION ALL SELECT 'DIM_FUEL_TYPE',     COUNT(*) FROM MARTS.DIM_FUEL_TYPE
UNION ALL SELECT 'DIM_DATE',          COUNT(*) FROM MARTS.DIM_DATE
UNION ALL SELECT 'FCT_CURRENT_PRICE', COUNT(*) FROM MARTS.FCT_CURRENT_PRICE
UNION ALL SELECT 'FCT_PRICE_CHANGE',  COUNT(*) FROM MARTS.FCT_PRICE_CHANGE
UNION ALL SELECT 'FCT_DAILY_PRICE',   COUNT(*) FROM MARTS.FCT_DAILY_PRICE;
