{{ config(materialized='view', schema='stg') }}

with src as (
  select *
  from {{ source('ext', 'trades') }}
),

-- Parse and cast raw NOS columns to proper types.
-- The NOS foreign table (ext.trades) exposes raw Parquet columns only;
-- partition-equivalent columns (pair, trade_date, hour) are derived here.
parsed as (
  select
    symbol,
    CAST(trade_id AS BIGINT)                                              as trade_id,
    CAST(price AS FLOAT)                                                  as price,
    CAST(qty AS FLOAT)                                                    as qty,

    -- Parquet BOOLEAN → Teradata BYTEINT (1 = true / buyer is maker,
    --                                     0 = false / buyer is NOT maker)
    CAST(is_buyer_maker AS BYTEINT)                                       as is_buyer_maker,

    -- ingested_at is an ISO 8601 string ("YYYY-MM-DDTHH:MI:SS.ffffff").
    -- Replace the 'T' separator so Teradata can parse it as TIMESTAMP.
    CAST(REPLACE(ingested_at, 'T', ' ') AS TIMESTAMP(6))                 as ingested_at_utc,

    CAST(event_id AS VARCHAR(50))                                         as event_id,
    CAST(schema_version AS INTEGER)                                       as schema_version,
    CAST(source AS VARCHAR(20))                                           as source,

    -- Convert epoch milliseconds to TIMESTAMP (second precision).
    -- INTERVAL arithmetic: INTEGER * INTERVAL '1' SECOND is standard SQL
    -- and is supported by Teradata.
    (TIMESTAMP '1970-01-01 00:00:00'
      + CAST(CAST(trade_ts AS BIGINT) / 1000 AS INTEGER) * INTERVAL '1' SECOND)
                                                                          as trade_ts_utc
  from src
)

select
  -- Partition-equivalent columns derived from the timestamp
  symbol                                                                  as pair,
  CAST(trade_ts_utc AS DATE)                                             as trade_date,
  CAST(EXTRACT(HOUR FROM trade_ts_utc) AS BYTEINT)                      as hour,

  symbol,
  trade_id,
  trade_ts_utc,
  price,
  qty,
  is_buyer_maker,
  ingested_at_utc,
  event_id,
  schema_version,
  source,

  -- Unique key for testing / joins
  (CAST(symbol AS VARCHAR(20)) || ':' || CAST(trade_id AS VARCHAR(20)))  as trade_key

from parsed
where trade_ts_utc is not null
