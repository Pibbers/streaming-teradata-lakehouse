{{ config(materialized='table', schema='marts') }}

with base as (
  select
    pair,
    TRUNC(trade_ts_utc, 'MI') as minute_bucket,
    price,
    qty,
    is_buyer_maker
  from {{ ref('stg_trades') }}
  where trade_ts_utc is not null
),

calc as (
  select
    pair,
    minute_bucket,

    COUNT(*)          as trade_count,
    SUM(qty)          as total_qty,
    SUM(price * qty)  as notional_usdt,

    -- buyer-initiated: buyer is NOT the maker  (is_buyer_maker = 0 / false)
    SUM(CASE WHEN is_buyer_maker = 0 THEN qty          ELSE 0 END) as buy_qty,
    SUM(CASE WHEN is_buyer_maker = 0 THEN price * qty  ELSE 0 END) as buy_notional_usdt,

    -- seller-initiated: buyer IS the maker     (is_buyer_maker = 1 / true)
    SUM(CASE WHEN is_buyer_maker = 1 THEN qty          ELSE 0 END) as sell_qty,
    SUM(CASE WHEN is_buyer_maker = 1 THEN price * qty  ELSE 0 END) as sell_notional_usdt

  from base
  group by 1, 2
)

select
  pair,
  minute_bucket,
  trade_count,
  total_qty,
  notional_usdt,

  buy_qty,
  sell_qty,
  buy_notional_usdt,
  sell_notional_usdt,

  (buy_qty - sell_qty)                             as qty_imbalance,
  (buy_notional_usdt - sell_notional_usdt)         as notional_imbalance,

  buy_qty            / NULLIF(total_qty,      0)   as buy_qty_ratio,
  sell_qty           / NULLIF(total_qty,      0)   as sell_qty_ratio,
  buy_notional_usdt  / NULLIF(notional_usdt,  0)   as buy_notional_ratio,
  sell_notional_usdt / NULLIF(notional_usdt,  0)   as sell_notional_ratio
from calc
