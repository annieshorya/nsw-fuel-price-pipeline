-- =====================================================================
-- 05_data_quality_checks.sql  —  tests + findings (run after 04)
--
-- Section 2 is the "test suite": every row should say PASS.
-- Sections 1 and 3 are findings worth putting in the README and
-- talking about in an interview.
-- =====================================================================

USE ROLE SYSADMIN;
USE WAREHOUSE FUEL_WH;
USE DATABASE FUEL_DB;

-- ---------------------------------------------------------------------
-- 1) How many rows passed, and why the rest were excluded
-- ---------------------------------------------------------------------
SELECT source, outcome, row_count,
       ROUND(100 * RATIO_TO_REPORT(row_count) OVER (PARTITION BY source), 2) AS pct_of_source
FROM MARTS.DQ_SUMMARY
ORDER BY source, row_count DESC;


-- ---------------------------------------------------------------------
-- 2) Automated tests — expect 0 failures everywhere
-- ---------------------------------------------------------------------
WITH tests AS (

  SELECT 'FCT_CURRENT_PRICE has one row per station x fuel' AS test_name, COUNT(*) AS failures
  FROM (SELECT station_id, fuel_code FROM MARTS.FCT_CURRENT_PRICE GROUP BY 1, 2 HAVING COUNT(*) > 1)

  UNION ALL
  SELECT 'DIM_STATION.station_id is unique', COUNT(*)
  FROM (SELECT station_id FROM MARTS.DIM_STATION GROUP BY 1 HAVING COUNT(*) > 1)

  UNION ALL
  SELECT 'FCT_CURRENT_PRICE stations all exist in DIM_STATION', COUNT(*)
  FROM MARTS.FCT_CURRENT_PRICE f
  LEFT JOIN MARTS.DIM_STATION d ON d.station_id = f.station_id
  WHERE d.station_id IS NULL

  UNION ALL
  SELECT 'FCT_PRICE_CHANGE stations all exist in DIM_STATION', COUNT(*)
  FROM MARTS.FCT_PRICE_CHANGE f
  LEFT JOIN MARTS.DIM_STATION d ON d.station_id = f.station_id
  WHERE d.station_id IS NULL

  UNION ALL
  SELECT 'Fuel codes in facts all exist in DIM_FUEL_TYPE', COUNT(*)
  FROM (SELECT fuel_code FROM MARTS.FCT_CURRENT_PRICE UNION SELECT fuel_code FROM MARTS.FCT_PRICE_CHANGE) f
  LEFT JOIN MARTS.DIM_FUEL_TYPE t ON t.fuel_code = f.fuel_code
  WHERE t.fuel_code IS NULL

  UNION ALL
  SELECT 'Price dates in facts all exist in DIM_DATE', COUNT(*)
  FROM (SELECT price_date FROM MARTS.FCT_CURRENT_PRICE UNION SELECT price_date FROM MARTS.FCT_PRICE_CHANGE) f
  LEFT JOIN MARTS.DIM_DATE d ON d.date_day = f.price_date
  WHERE d.date_day IS NULL

  UNION ALL
  SELECT 'No NULL prices in FCT_CURRENT_PRICE', COUNT_IF(price_cents IS NULL)
  FROM MARTS.FCT_CURRENT_PRICE

  UNION ALL
  SELECT 'FCT_DAILY_PRICE has one row per station x fuel x day', COUNT(*)
  FROM (SELECT station_id, fuel_code, price_date FROM MARTS.FCT_DAILY_PRICE GROUP BY 1, 2, 3 HAVING COUNT(*) > 1)

)
SELECT test_name, failures, IFF(failures = 0, 'PASS', 'FAIL') AS result
FROM tests
ORDER BY result, test_name;


-- ---------------------------------------------------------------------
-- 3) Findings (not failures — things the data taught you)
-- ---------------------------------------------------------------------

-- 3a. Stale prices: liquid-fuel prices not updated for 30+ days before the snapshot
SELECT t.fuel_name,
       COUNT(*)                                         AS prices,
       COUNT_IF(f.is_stale)                             AS stale_prices,
       ROUND(100 * COUNT_IF(f.is_stale) / COUNT(*), 1)  AS pct_stale
FROM MARTS.FCT_CURRENT_PRICE f
JOIN MARTS.DIM_FUEL_TYPE t ON t.fuel_code = f.fuel_code
GROUP BY t.fuel_name, t.sort_order
ORDER BY t.sort_order;

-- 3b. Suspected placeholder prices (same price on 3+ fuels at the same second)
SELECT d.station_name, d.suburb, f.fuel_code, f.price_cents, f.last_updated_at
FROM MARTS.FCT_CURRENT_PRICE f
JOIN MARTS.DIM_STATION d ON d.station_id = f.station_id
WHERE f.is_suspect_placeholder
ORDER BY d.station_name, f.fuel_code;

-- 3c. Why stations are keyed on the API id, not name + postcode
SELECT match_key, COUNT(DISTINCT station_id) AS different_stations
FROM STAGING.STG_API_PRICES
WHERE dq_issue IS NULL
GROUP BY match_key
HAVING COUNT(DISTINCT station_id) > 1
ORDER BY different_stations DESC, match_key;

-- 3d. How well history stations matched to API stations (coordinates for the map)
SELECT match_status, COUNT(*) AS history_stations,
       ROUND(100 * RATIO_TO_REPORT(COUNT(*)) OVER (), 1) AS pct
FROM STAGING.STG_HISTORY_STATION_MAP
GROUP BY match_status
ORDER BY history_stations DESC;

-- 3e. Unparseable history timestamps — look at the raw text to see the format
SELECT price_updated_raw, COUNT(*) AS n
FROM STAGING.STG_PRICE_HISTORY
WHERE dq_issue = 'unparseable timestamp'
GROUP BY 1
ORDER BY n DESC
LIMIT 20;
