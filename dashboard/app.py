from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import teradatasql

# Teradata database that holds the dbt mart tables
MARTS_DB = "marts"


def _td_connect() -> teradatasql.TeradataConnection:
    return teradatasql.connect(
        host=os.getenv("TERADATA_HOST", "localhost"),
        user=os.getenv("TERADATA_USER", "dbc"),
        password=os.getenv("TERADATA_PASSWORD", "dbc"),
    )


@st.cache_data(ttl=15)
def query_df(sql: str) -> pd.DataFrame:
    con = _td_connect()
    try:
        return pd.read_sql(sql, con)
    finally:
        con.close()


def table_exists(database: str, table: str) -> bool:
    con = _td_connect()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM DBC.TablesV"
            f" WHERE DatabaseName = '{database}'"
            f"   AND TableName   = '{table}'"
            "    AND TableKind   = 'T'"
        )
        return cur.fetchone()[0] > 0
    finally:
        con.close()


st.set_page_config(page_title="Crypto Streaming Dashboard", layout="wide")
st.title("Crypto Kafka Streaming Pipeline — Dashboard")

required = ["fct_candles_1m", "fct_orderflow_1m", "fct_trades_1m"]
missing = [t for t in required if not table_exists(MARTS_DB, t)]
if missing:
    st.error(
        f"Missing mart tables in Teradata database `{MARTS_DB}`: {', '.join(missing)}.\n\n"
        "Run dbt to create them:\n"
        "`uvx --from . crypto-dbt run`"
    )
    st.stop()

# Sidebar controls
st.sidebar.header("Controls")

pairs_df = query_df(f"SELECT DISTINCT pair FROM {MARTS_DB}.fct_candles_1m ORDER BY 1")
pairs = pairs_df["pair"].tolist() if not pairs_df.empty else ["BTCUSDT"]
pair = st.sidebar.selectbox("Pair", pairs, index=0)

lookback_minutes = st.sidebar.selectbox("Lookback window", [30, 60, 180, 360, 720, 1440], index=2)
end_ts = datetime.now(timezone.utc)
start_ts = end_ts - timedelta(minutes=int(lookback_minutes))
start_str = start_ts.strftime("%Y-%m-%d %H:%M:%S")

st.sidebar.caption(f"Time window (UTC): {start_ts.strftime('%Y-%m-%d %H:%M')} → {end_ts.strftime('%H:%M')}")

# Pipeline health
st.subheader("Pipeline Health")
if table_exists(MARTS_DB, "fct_pipeline_health_5m"):
    health = query_df(f"SELECT * FROM {MARTS_DB}.fct_pipeline_health_5m ORDER BY pair")
    st.dataframe(health, use_container_width=True)
else:
    st.info("`fct_pipeline_health_5m` not found (optional).")

col1, col2 = st.columns([2, 1])

# Candles
candles_sql = (
    f"SELECT * FROM {MARTS_DB}.fct_candles_1m"
    f" WHERE pair = '{pair}'"
    f"   AND minute_bucket >= TIMESTAMP '{start_str}'"
    f" ORDER BY minute_bucket"
)
candles = query_df(candles_sql)

with col1:
    st.subheader("Candles (1m): OHLC + VWAP")
    if candles.empty:
        st.warning("No candle data found in the selected window. Let the pipeline run a bit and refresh.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=candles["minute_bucket"],
            open=candles["open_price"],
            high=candles["high_price"],
            low=candles["low_price"],
            close=candles["close_price"],
            name="OHLC",
        ))
        fig.add_trace(go.Scatter(
            x=candles["minute_bucket"],
            y=candles["vwap"],
            mode="lines",
            name="VWAP",
        ))
        fig.update_layout(
            height=520,
            xaxis_title="Minute (UTC)",
            yaxis_title="Price (USDT)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Latest candle stats")
    if not candles.empty:
        latest = candles.iloc[-1]
        st.metric("Trade count (1m)", int(latest["trade_count"]))
        st.metric("Total qty (1m)",   float(latest["total_qty"]))
        st.metric("Notional USDT (1m)", float(latest["notional_usdt"]))
        st.metric("VWAP", float(latest["vwap"]))
    else:
        st.info("No data in window.")

# Order flow
st.subheader("Order Flow (1m): Buy/Sell Imbalance")
orderflow_sql = (
    f"SELECT * FROM {MARTS_DB}.fct_orderflow_1m"
    f" WHERE pair = '{pair}'"
    f"   AND minute_bucket >= TIMESTAMP '{start_str}'"
    f" ORDER BY minute_bucket"
)
of = query_df(orderflow_sql)
if of.empty:
    st.warning("No orderflow data found in the selected window.")
else:
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=of["minute_bucket"], y=of["qty_imbalance"], name="Qty imbalance"))
    fig2.add_trace(go.Scatter(x=of["minute_bucket"], y=of["buy_qty_ratio"], mode="lines", name="Buy qty ratio"))
    fig2.update_layout(height=360, xaxis_title="Minute (UTC)", legend=dict(orientation="h"))
    st.plotly_chart(fig2, use_container_width=True)

# Trades summary
st.subheader("Trades Summary (1m)")
trades_sql = (
    f"SELECT TOP 200 * FROM {MARTS_DB}.fct_trades_1m"
    f" WHERE pair = '{pair}'"
    f"   AND minute_bucket >= TIMESTAMP '{start_str}'"
    f" ORDER BY minute_bucket DESC"
)
trades = query_df(trades_sql)
st.dataframe(trades, use_container_width=True)

st.caption("Tip: Keep producer/consumer running and refresh the page to see new minutes appear.")
