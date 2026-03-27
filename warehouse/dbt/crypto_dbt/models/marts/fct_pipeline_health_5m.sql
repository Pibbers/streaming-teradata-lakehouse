{{ config(materialized='table', schema='marts') }}

with base as (
  select
    pair,
    trade_ts_utc,
    ingested_at_utc
  from {{ ref('stg_trades') }}
  where trade_ts_utc is not null
),

windowed as (
  select
    pair,
    -- Teradata does not support the SQL FILTER clause on aggregates.
    -- Use CASE WHEN inside SUM as the equivalent.
    SUM(CASE
          WHEN trade_ts_utc >= CURRENT_TIMESTAMP - INTERVAL '5' MINUTE
          THEN 1 ELSE 0
        END)                    as trades_last_5m,
    MAX(trade_ts_utc)           as max_trade_ts_utc,
    MAX(ingested_at_utc)        as max_ingested_at_utc
  from base
  group by 1
)

select
  pair,
  trades_last_5m,
  max_trade_ts_utc,
  max_ingested_at_utc,

  -- Teradata timestamp subtraction returns an INTERVAL DAY TO SECOND.
  -- Convert to total integer seconds via EXTRACT on each component.
  (  EXTRACT(DAY    FROM (CURRENT_TIMESTAMP - max_trade_ts_utc)) * 86400
   + EXTRACT(HOUR   FROM (CURRENT_TIMESTAMP - max_trade_ts_utc)) * 3600
   + EXTRACT(MINUTE FROM (CURRENT_TIMESTAMP - max_trade_ts_utc)) * 60
   + CAST(EXTRACT(SECOND FROM (CURRENT_TIMESTAMP - max_trade_ts_utc)) AS INTEGER)
  )                             as seconds_since_last_trade,

  (  EXTRACT(DAY    FROM (CURRENT_TIMESTAMP - max_ingested_at_utc)) * 86400
   + EXTRACT(HOUR   FROM (CURRENT_TIMESTAMP - max_ingested_at_utc)) * 3600
   + EXTRACT(MINUTE FROM (CURRENT_TIMESTAMP - max_ingested_at_utc)) * 60
   + CAST(EXTRACT(SECOND FROM (CURRENT_TIMESTAMP - max_ingested_at_utc)) AS INTEGER)
  )                             as seconds_since_last_ingest

from windowed
