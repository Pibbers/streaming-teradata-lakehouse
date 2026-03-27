from __future__ import annotations


def parquet_partition_path(root: str, subdir: str, pair: str, trade_date: str, hour: str) -> str:
    """
    Return the partition directory as a string, compatible with both
    local filesystem paths and S3/MinIO URLs:

        Local: ./data/parquet/trades/BTCUSDT/2024-01-01/10
        S3:    s3://crypto-trades/trades/BTCUSDT/2024-01-01/10
    """
    return f"{root.rstrip('/')}/{subdir}/{pair}/{trade_date}/{hour}"
