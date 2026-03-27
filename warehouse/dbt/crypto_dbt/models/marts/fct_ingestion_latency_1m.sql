{{ config(materialized='table', schema='marts') }}

with base as (
  select
    pair,
    TRUNC(trade_ts_utc, 'MI') as minute_bucket,
    trade_ts_utc,
    ingested_at_utc
  from {{ ref('stg_trades') }}
  where trade_ts_utc is not null
    and ingested_at_utc is not null
),

calc as (
  select
    pair,
    minute_bucket,
    -- Latency in whole seconds between trade event and ingestion.
    -- Teradata interval subtraction → INTERVAL DAY TO SECOND; extract components.
    (  EXTRACT(DAY    FROM (ingested_at_utc - trade_ts_utc)) * 86400
     + EXTRACT(HOUR   FROM (ingested_at_utc - trade_ts_utc)) * 3600
     + EXTRACT(MINUTE FROM (ingested_at_utc - trade_ts_utc)) * 60
     + CAST(EXTRACT(SECOND FROM (ingested_at_utc - trade_ts_utc)) AS INTEGER)
    )                                                           as latency_seconds
  from base
),

-- PERCENTILE_CONT is an ordered analytical function in Teradata; it requires
-- OVER (PARTITION BY ...).  Use DISTINCT to collapse per-row window results
-- down to one row per (pair, minute_bucket).
windowed as (
  select distinct
    pair,
    minute_bucket,
    COUNT(*)                   OVER w                                      as trade_count,
    AVG(CAST(latency_seconds AS FLOAT)) OVER w                             as avg_latency_s,
    MIN(latency_seconds)       OVER w                                      as min_latency_s,
    MAX(latency_seconds)       OVER w                                      as max_latency_s,
    PERCENTILE_CONT(0.95)
      WITHIN GROUP (ORDER BY latency_seconds)
      OVER w                                                                as p95_latency_s,
    PERCENTILE_CONT(0.99)
      WITHIN GROUP (ORDER BY latency_seconds)
      OVER w                                                                as p99_latency_s
  from calc
  window w as (PARTITION BY pair, minute_bucket)
)

select * from windowed
