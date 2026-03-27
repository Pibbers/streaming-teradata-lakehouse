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
    price,
    qty
  from base
)

select
  pair,
  minute_bucket,
  COUNT(*)          as trade_count,
  SUM(qty)          as total_qty,
  SUM(price * qty)  as notional_usdt,
  AVG(price)        as avg_price,
  MIN(price)        as min_price,
  MAX(price)        as max_price
from bucketed
group by 1, 2
