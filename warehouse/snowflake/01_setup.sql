-- =====================================================================
-- 01_setup.sql  —  one-off setup: compute, database and schemas
-- Run in a Snowsight SQL worksheet (Projects → Workspaces / Worksheets).
-- Highlight everything and press Ctrl+Shift+Enter to run all.
-- =====================================================================

USE ROLE SYSADMIN;   -- SYSADMIN owns databases and warehouses (ACCOUNTADMIN is for account admin)

-- A small virtual warehouse = the compute that runs queries.
-- XSMALL + auto-suspend after 60s idle keeps the free trial credits alive.
CREATE WAREHOUSE IF NOT EXISTS FUEL_WH
  WAREHOUSE_SIZE      = 'XSMALL'
  AUTO_SUSPEND        = 60
  AUTO_RESUME         = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Compute for the NSW fuel price pipeline';

CREATE DATABASE IF NOT EXISTS FUEL_DB
  COMMENT = 'NSW FuelCheck data: raw → staging → marts';

-- Three layers (same idea as bronze / silver / gold):
CREATE SCHEMA IF NOT EXISTS FUEL_DB.RAW      COMMENT = 'Data exactly as it arrived, all text, plus load metadata';
CREATE SCHEMA IF NOT EXISTS FUEL_DB.STAGING  COMMENT = 'Typed, cleaned, de-duplicated views; bad rows labelled, not dropped';
CREATE SCHEMA IF NOT EXISTS FUEL_DB.MARTS    COMMENT = 'Star schema (facts + dimensions) consumed by Power BI';

USE WAREHOUSE FUEL_WH;
USE DATABASE FUEL_DB;

-- Quick check: should list RAW, STAGING, MARTS (plus INFORMATION_SCHEMA and PUBLIC)
SHOW SCHEMAS IN DATABASE FUEL_DB;
