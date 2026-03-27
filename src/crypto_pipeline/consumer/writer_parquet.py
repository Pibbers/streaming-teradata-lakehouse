from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import polars as pl


class ParquetWriter:
    def __init__(
        self,
        parquet_root: str,
        subdir: str,
        s3_client=None,
        s3_bucket: str = "",
    ) -> None:
        self.parquet_root = parquet_root
        self.subdir = subdir
        self._s3 = s3_client
        self._bucket = s3_bucket
        self._is_s3 = parquet_root.startswith("s3://")

    def write(self, df: pl.DataFrame, out_dir: str) -> str:
        fname = f"part-{uuid4().hex}.parquet"

        if self._is_s3:
            # Strip "s3://<bucket>/" prefix to get the S3 key prefix
            prefix = out_dir[len(f"s3://{self._bucket}/"):]
            key = f"{prefix}/{fname}"

            buf = io.BytesIO()
            df.write_parquet(buf, compression="zstd")
            buf.seek(0)
            self._s3.put_object(Bucket=self._bucket, Key=key, Body=buf)
            return f"s3://{self._bucket}/{key}"
        else:
            out_path_dir = Path(out_dir)
            out_path_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_path_dir / fname
            df.write_parquet(str(out_path), compression="zstd")
            return str(out_path)
