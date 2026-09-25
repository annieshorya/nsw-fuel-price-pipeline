-- =====================================================================
-- 06_powerbi_access.sql  —  a read-only role + token for Power BI
--
-- Why a token? New Snowflake accounts require MFA for people who sign in
-- with a password, and Power BI can't answer an MFA prompt. A programmatic
-- access token (PAT) is used in place of the password instead.
--
-- Run as ACCOUNTADMIN. Copy the token from the result of the LAST
-- statement straight away — Snowflake only shows it once.
-- =====================================================================

USE ROLE ACCOUNTADMIN;

-- 1) Read-only role that can only see the MARTS schema
CREATE ROLE IF NOT EXISTS BI_READER COMMENT = 'Read-only access to FUEL_DB.MARTS for Power BI';
GRANT USAGE  ON WAREHOUSE FUEL_WH                     TO ROLE BI_READER;
GRANT USAGE  ON DATABASE  FUEL_DB                     TO ROLE BI_READER;
GRANT USAGE  ON SCHEMA    FUEL_DB.MARTS               TO ROLE BI_READER;
GRANT SELECT ON ALL TABLES    IN SCHEMA FUEL_DB.MARTS TO ROLE BI_READER;
GRANT SELECT ON ALL VIEWS     IN SCHEMA FUEL_DB.MARTS TO ROLE BI_READER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA FUEL_DB.MARTS TO ROLE BI_READER;   -- tables rebuilt by 04 stay readable
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA FUEL_DB.MARTS TO ROLE BI_READER;
GRANT ROLE BI_READER TO ROLE SYSADMIN;                                   -- keep the role hierarchy tidy

-- 2) Give the role to you
SET my_user = CURRENT_USER();
GRANT ROLE BI_READER TO USER IDENTIFIER($my_user);
-- If that errors (e.g. your username has special characters), use:
-- GRANT ROLE BI_READER TO USER "your_username";

-- 3) Let a token work without an IP allow-list (fine for a personal trial,
--    NOT what you'd do for a client — there you'd add a network policy).
CREATE AUTHENTICATION POLICY IF NOT EXISTS FUEL_DB.PUBLIC.PAT_DEV_POLICY
  PAT_POLICY = (NETWORK_POLICY_EVALUATION = ENFORCED_NOT_REQUIRED)
  COMMENT = 'Dev only: allow programmatic access tokens without a network policy';
ALTER USER IDENTIFIER($my_user) SET AUTHENTICATION POLICY FUEL_DB.PUBLIC.PAT_DEV_POLICY;

-- 4) Create the token, locked to the read-only role, valid 30 days.
--    COPY the token_secret value from the result into a password manager.
ALTER USER IDENTIFIER($my_user)
  ADD PROGRAMMATIC ACCESS TOKEN POWERBI_TOKEN
  ROLE_RESTRICTION = 'BI_READER'
  DAYS_TO_EXPIRY   = 30
  COMMENT          = 'Power BI Desktop - fuel dashboard';

-- Housekeeping later:
-- SHOW USER PROGRAMMATIC ACCESS TOKENS FOR USER IDENTIFIER($my_user);
-- ALTER USER IDENTIFIER($my_user) REMOVE PROGRAMMATIC ACCESS TOKEN POWERBI_TOKEN;
