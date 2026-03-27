-- Teradata database initialisation for the crypto data warehouse.
--
-- Run this as a DBA / privileged user before the first `dbt run`.
-- `crypto-init-db` also runs these statements automatically.
--
-- In Teradata, "schemas" are databases.  dbt-teradata maps each dbt
-- schema to a Teradata database:
--
--   ext   → raw NOS foreign table (ext.trades over MinIO Parquet files)
--   stg   → dbt staging views  (stg.stg_trades)
--   marts → dbt mart tables    (marts.fct_candles_1m, etc.)

CREATE DATABASE ext
  AS PERMANENT = 1000000000 BYTES,
     SPOOL     = 1000000000 BYTES;

CREATE DATABASE stg
  AS PERMANENT = 5000000000 BYTES,
     SPOOL     = 5000000000 BYTES;

CREATE DATABASE marts
  AS PERMANENT = 5000000000 BYTES,
     SPOOL     = 5000000000 BYTES;

-- Grant the dbt runtime user full access to all three databases.
-- Replace 'crypto_user' with the value of TERADATA_USER.
GRANT ALL ON ext   TO crypto_user;
GRANT ALL ON stg   TO crypto_user;
GRANT ALL ON marts TO crypto_user;
