from __future__ import annotations

from datetime import datetime, timezone


def trade_partitions(trade_ts_ms: int) -> tuple[str, str]:
    """
    Returns (trade_date, hour) in UTC from epoch milliseconds.
    """
    dt = datetime.fromtimestamp(trade_ts_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H")