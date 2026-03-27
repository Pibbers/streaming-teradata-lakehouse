{{ config(materialized='table', schema='marts') }}

with base as (
  select
    pair,
    trade_ts_utc,
    price,
    qty
  from {{ ref('stg_trades') }}
  where trade_ts_utc is not null
),

bucketed as (
  select
    pair,
    -- TRUNC(ts, 'MI') is the Teradata equivalent of date_trunc('minute', ts)
    TRUNC(trade_ts_utc, 'MI') as minute_bucket,
    trade_ts_utc,
    price,
    qty
  from base
),

agg as (
  select
    pair,
    minute_bucket,
    COUNT(*)                               as trade_count,
    SUM(qty)                               as total_qty,
    SUM(price * qty)                       as notional_usdt,
    SUM(price * qty) / NULLIF(SUM(qty), 0) as vwap,
    MIN(price)                             as low_price,
    MAX(price)                             as high_price
  from bucketed
  group by 1, 2
),

-- Teradata does not have arg_min / arg_max.
-- Use ROW_NUMBER() to tag the earliest and latest row per bucket,
-- then collapse with MIN(CASE …) which is a standard aggregate.
ranked as (
  select
    pair,
    minute_bucket,
    price,
    ROW_NUMBER() OVER (PARTITION BY pair, minute_bucket ORDER BY trade_ts_utc ASC)  as rn_asc,
    ROW_NUMBER() OVER (PARTITION BY pair, minute_bucket ORDER BY trade_ts_utc DESC) as rn_desc
  from bucketed
),

open_close as (
  select
    pair,
    minute_bucket,
    MIN(CASE WHEN rn_asc  = 1 THEN price END) as open_price,
    MIN(CASE WHEN rn_desc = 1 THEN price END) as close_price
  from ranked
  group by 1, 2
)

select
  a.pair,
  a.minute_bucket,
  o.open_price,
  a.high_price,
  a.low_price,
  o.close_price,
  a.vwap,
  a.trade_count,
  a.total_qty,
  a.notional_usdt
from agg a
join open_close o
  on a.pair = o.pair
  and a.minute_bucket = o.minute_bucket
