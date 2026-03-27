-- NOS (Native Object Store) foreign table pointing to MinIO S3-compatible storage.
--
-- This DDL is executed automatically by `crypto-init-db`.  You can also run
-- it manually whenever the MinIO endpoint or credentials change.
--
-- Prerequisites
-- ─────────────
-- 1. Teradata NOS must be licensed and enabled on your system.
-- 2. The Teradata system must be able to reach the MinIO endpoint over the
--    network.  Set TERADATA_NOS_ENDPOINT to the LAN IP of the MinIO host
--    (not localhost) when Teradata runs on a separate machine.
-- 3. The AUTHORIZATION object below must exist before creating the table.
--    `crypto-init-db` creates it automatically from MINIO_ACCESS_KEY /
--    MINIO_SECRET_KEY.

-- Step 1: create the authorization object that holds MinIO credentials.
CREATE AUTHORIZATION SYSDBA.CRYPTO_MINIO_LOCAL_AUTH
AS DEFINER TRUSTED
USER     'minioadmin'
PASSWORD 'minioadmin';

-- Step 2: create the foreign table.
-- PATHPATTERN segments are matched from the bucket root (not from LOCATION):
--   $var1    — subdir                   (e.g. trades)
--   $symbol  — trading pair directory  (e.g. BTCUSDT)
--   $var3    — date partition           (e.g. 2024-01-15, type DATE)
--   $var4    — hour partition           (e.g. 10, type BYTEINT)
--   $var5    — parquet filename
CREATE MULTISET FOREIGN TABLE ext.trades ,FALLBACK ,
    EXTERNAL SECURITY SYSDBA.CRYPTO_MINIO_LOCAL_AUTH ,
    MAP = TD_MAP1
(
    Location       VARCHAR(2048) CHARACTER SET UNICODE CASESPECIFIC,
    schema_version BIGINT,
    event_id       VARCHAR(36)   CHARACTER SET UNICODE NOT CASESPECIFIC,
    source         VARCHAR(10)   CHARACTER SET UNICODE NOT CASESPECIFIC,
    ingested_at    VARCHAR(32)   CHARACTER SET UNICODE NOT CASESPECIFIC,
    symbol         VARCHAR(7)    CHARACTER SET UNICODE NOT CASESPECIFIC,
    trade_id       BIGINT,
    trade_ts       BIGINT,
    price          FLOAT,
    qty            FLOAT,
    is_buyer_maker BYTEINT
)
USING
(
    -- Replace host:port with the MinIO LAN IP as seen from the Teradata server.
    LOCATION    ('/s3/192.168.1.242:9000/crypto-trades/trades/')
    MANIFEST    ('FALSE')
    PATHPATTERN ('$var1/$symbol/$var3/$var4/$var5')
    STOREDAS    ('PARQUET')
)
NO PRIMARY INDEX
PARTITION BY ( COLUMN ,var3 DATE FORMAT 'Y4-MM-DD',var4 BYTEINT );
