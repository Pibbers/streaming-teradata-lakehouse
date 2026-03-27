# CLAUDE.md — Crypto Kafka Streaming Pipeline

This file is automatically loaded by Claude Code. It provides project context,
architecture decisions, and configuration patterns for AI-assisted development.

---

## Project Summary

Real-time crypto trade streaming and analytics platform:

```
Binance WebSocket → Kafka → Consumer → MinIO (Parquet)
                                           ↓
                               Hive Metastore (Iceberg catalog)
                                           ↓
                            Teradata NOS (ext.trades foreign table)
                                           ↓
                              dbt (stg + mart models)
                                           ↓
                        Streamlit dashboard / Airflow orchestration
```

- Python 3.11, uv/uvx for package management
- All infrastructure runs in Docker Compose
- `warehouse/dbt/crypto_dbt/` is the dbt project
- `warehouse/dbt/profiles.yml` is the dbt profiles file (Teradata adapter)

---

## Technology Stack

| Layer | Technology |
|---|---|
| Streaming | Apache Kafka 7.6.1 (KRaft, single-node) |
| Object storage | MinIO (S3-compatible, Hive-partitioned Parquet) |
| Table format | Apache Iceberg (ACID, time-travel) |
| Metastore | Hive Metastore 3.1.3 + MySQL 8.0.39 backend |
| Warehouse | Teradata Vantage (NOS reads MinIO/S3 directly) |
| Transformation | dbt-core + dbt-teradata |
| Orchestration | Apache Airflow 2.9 (LocalExecutor + PostgreSQL 17) |
| Dashboard | Streamlit + Plotly |

---

## Data Model

### Parquet partition layout in MinIO

```
s3://crypto-trades/trades/BTCUSDT/
    trade_date=YYYY-MM-DD/
        hour=HH/
            *.parquet
```

The consumer writes partitioned files using Polars + boto3 directly to MinIO.
`PARQUET_ROOT` env var controls the bucket (`s3://crypto-trades`).
`PARQUET_TOPIC_SUBDIR` controls the subdirectory (`trades`, default).

### Teradata NOS foreign table (`ext.trades`)

The NOS foreign table reads Parquet files directly from MinIO. Created by
`crypto-init-db`. Key constraints:

- **LOCATION** must end at the symbol directory level, e.g.
  `/s3/<host:port>/crypto-trades/trades/BTCUSDT/`
- **PATHPATTERN** `'$var1/$symbol/$var3/$var4/$var5'` is matched from the
  **bucket root** — not from LOCATION
- **PARTITION BY** only declares the unresolved virtual columns:
  `var3 DATE FORMAT 'Y4-MM-DD', var4 BYTEINT`
- **EXTERNAL SECURITY** uses a named AUTHORIZATION object (not inline
  `ACCESS_ID`/`ACCESS_KEY`) — Teradata error 3701 if inline credentials used
- `TERADATA_NOS_ENDPOINT` must be the **LAN IP** of MinIO as seen from the
  Teradata server (not `localhost`) — set in `.env` as e.g. `http://192.168.1.242:9000`

### dbt schema mapping

The `generate_schema_name.sql` macro prevents dbt from prepending the target
schema to the custom schema. This maps:
- `schema='stg'` → Teradata database `stg`
- `schema='marts'` → Teradata database `marts`

### Mart models

All mart tables in `warehouse/dbt/crypto_dbt/models/marts/` are Iceberg tables:

| Model | Description |
|---|---|
| `stg_trades` | Staging view — casts NOS raw columns, derives `pair`/`trade_date`/`hour` |
| `fct_trades_1m` | Trade aggregates per minute |
| `fct_candles_1m` | OHLCV + VWAP candles |
| `fct_orderflow_1m` | Buy/sell imbalance |
| `fct_ingestion_latency_1m` | Latency percentiles (p95, p99) |
| `fct_pipeline_health_5m` | Trade counts and freshness |

---

## Teradata SQL Patterns

DuckDB → Teradata translations used throughout this project:

| Concept | Teradata syntax |
|---|---|
| Truncate to minute | `TRUNC(ts, 'MI')` |
| First value in group (open price) | `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ts ASC)` + `MIN(CASE WHEN rn=1 THEN col END)` |
| Filtered aggregate | `SUM(CASE WHEN condition THEN 1 ELSE 0 END)` |
| Percentiles | `PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY col) OVER (PARTITION BY ...)` |
| Current time | `CURRENT_TIMESTAMP` |
| Epoch ms → TIMESTAMP | `TIMESTAMP '1970-01-01 00:00:00' + CAST(ts/1000 AS INTEGER) * INTERVAL '1' SECOND` |
| ISO 8601 string → TIMESTAMP | `CAST(REPLACE(ingested_at, 'T', ' ') AS TIMESTAMP(6))` |
| Boolean column | `BYTEINT` (1=true, 0=false) — Teradata has no BOOLEAN for Parquet-sourced data |
| Top N rows | `SELECT TOP n` (not `LIMIT n`) |
| List tables | `SELECT * FROM DBC.TablesV WHERE DatabaseName = '...'` |
| Seconds between timestamps | `EXTRACT(DAY FROM (b-a))*86400 + EXTRACT(HOUR FROM (b-a))*3600 + EXTRACT(MINUTE FROM (b-a))*60 + EXTRACT(SECOND FROM (b-a))` |

---

## CLI Entry Points (uvx)

All commands are exposed via `pyproject.toml` `[project.scripts]`:

```bash
uvx --from . crypto-producer        # Binance WebSocket → Kafka
uvx --from . crypto-consumer        # Kafka → Parquet (MinIO)
uvx --from . crypto-init-db         # Create Teradata DBs + NOS table (run once)
uvx --from . crypto-query-db        # Print latest rows from mart tables
uvx --from . crypto-dbt run         # Run dbt (forwards any dbt args)
uvx --from ".[dashboard]" crypto-dashboard   # Streamlit dashboard
```

`crypto-dbt` automatically injects `--project-dir warehouse/dbt/crypto_dbt`
and `--profiles-dir warehouse/dbt` unless supplied by the caller.

---

## Environment Variables

Copy `.env.example` to `.env`. Key variables:

```env
# Kafka
KAFKA_BOOTSTRAP=localhost:9092

# MinIO
PARQUET_ROOT=s3://crypto-trades
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=crypto-trades
PARQUET_TOPIC_SUBDIR=trades

# Teradata
TERADATA_HOST=localhost
TERADATA_USER=dbc
TERADATA_PASSWORD=dbc
TERADATA_SCHEMA=crypto_db

# Teradata NOS endpoint (LAN IP of MinIO as seen from Teradata)
# Set this when Teradata is on a separate host from MinIO
TERADATA_NOS_ENDPOINT=http://192.168.1.242:9000

# Trading pair (derived from BINANCE_WS_URL if not set)
TRADING_PAIR=BTCUSDT
BINANCE_WS_URL=wss://stream.binance.com:9443/ws/btcusdt@trade
```

Docker containers override `KAFKA_BOOTSTRAP` → `kafka:29092` and
`MINIO_ENDPOINT` → `http://minio:9000` automatically via `compose.yml`.

---

## Docker Compose

```bash
# Core pipeline (Kafka + MinIO + Hive + producer + consumer)
docker compose -f docker/compose.yml up -d --build

# + Airflow orchestration
docker compose -f docker/compose.yml -f docker/compose.airflow.yml up -d --build
```

Containers:
- `crypto-kafka` — Kafka KRaft, port 9092 (host) / 29092 (internal)
- `crypto-minio` — MinIO S3 API port 9000, console port 9001
- `crypto-minio-init` — one-shot bucket creator (`crypto-trades`, `iceberg`)
- `crypto-mysql-metastore` — MySQL 8.0.39 (Hive backend)
- `crypto-hive-metastore` — Hive Metastore 3.1.3, port 9083
- `crypto-producer` — streams Binance → Kafka
- `crypto-consumer` — Kafka → Parquet on MinIO

---

## Airflow DAGs

Defined in `airflow/dags/crypto_pipeline.py`:

| DAG | Schedule | Task |
|---|---|---|
| `crypto_dbt_refresh` | `*/5 * * * *` | `dbt run` all models |
| `crypto_dbt_test` | `0 2 * * *` | `dbt test` nightly |

Airflow UI: http://localhost:8080 (admin/admin)

---

## Known Issues & Resolutions

### NOS foreign table DDL

| Error | Cause | Fix |
|---|---|---|
| Error 3701 | Inline `ACCESS_ID`/`ACCESS_KEY` in USING clause | Use named AUTHORIZATION object with `EXTERNAL SECURITY` |
| Error 4958 | `PATHSTYLE` option in USING clause | Remove `PATHSTYLE` — not a valid NOS option |
| Error 4857 | LOCATION doesn't go deep enough (stops at `trades/`) | LOCATION must end at the symbol directory (`trades/BTCUSDT/`) |
| NOS can't reach MinIO | `TERADATA_NOS_ENDPOINT` set to `localhost` | Set to the LAN IP of the MinIO host (`http://192.168.1.242:9000`) |

### Hive Metastore / Iceberg (Teradata OTF)

#### Hadoop JAR version conflict (`NoSuchMethodError: HadoopKerberosName.setRuleMechanism`)

The base image `apache/hive:3.1.3` ships `hadoop-common-3.1.0.jar` at
`/opt/hadoop/share/hadoop/common/`. If you add a newer `hadoop-common` (e.g.
3.3.x) to `/opt/hive/lib/`, both end up on the classpath. `UserGroupInformation`
(loaded from 3.3.x) calls `setRuleMechanism`, which doesn't exist in the 3.1.0
`HadoopKerberosName` — instant crash at startup.

**Rule**: never add `hadoop-common` to `/opt/hive/lib/`. All other Hadoop JARs
added (e.g. `hadoop-aws`) must be version-pinned to **3.1.0** to match the
bundled `hadoop-common`.

Current versions in `docker/Dockerfile.hive-metastore`:

- `hadoop-aws-3.1.0.jar`
- `aws-java-sdk-bundle-1.11.271.jar`

#### Empty warehouse path (`IllegalArgumentException: Can not create a Path from an empty string`)

`hive.metastore.warehouse.dir = s3a://iceberg` has an **empty path component**
(scheme=`s3a`, authority=`iceberg`, path=``). Hive's `Warehouse.getDnsPath()`
passes an empty string to `new Path(...)` and crashes.

**Fix**: value must be `s3a://iceberg/warehouse` (non-empty path).

#### Docker named volume caches stale `hive-site.xml`

The named volume `docker_hive_metastore_config` is mounted at `/opt/hive/conf`.
It persists across image rebuilds. After changing `hive-site.xml` on the host,
you must either:

1. Remove and recreate the volume: `docker compose -f docker/compose.yml down -v && docker compose ... up -d --build`
2. Or copy directly into the running volume:

   ```bash
   docker run --rm \
     -v docker_hive_metastore_config:/conf \
     -v $(pwd)/docker/hive-site.xml:/src/hive-site.xml \
     alpine cp /src/hive-site.xml /conf/hive-site.xml
   ```

Note: the entrypoint runs `envsubst` over `hive-site.xml` at every startup, so
`${VAR}` placeholders are expanded from environment variables each time.

#### Teradata OTF uses `s3://` scheme, not `s3a://` (`UnsupportedFileSystemException`)

When Teradata OTF calls Hive Metastore's `create_database` thrift RPC, it
derives the `locationUri` from `STORAGE_LOCATION` in the `CREATE DATALAKE`
statement and passes `s3://...` (not `s3a://`). Hadoop 3.x removed the legacy
`s3://` filesystem — you must alias it:

```xml
<!-- In hive-site.xml -->
<property>
  <name>fs.s3.impl</name>
  <value>org.apache.hadoop.fs.s3a.S3AFileSystem</value>
</property>
```

`S3AFileSystem` reads credentials from `fs.s3a.*` keys regardless of which
scheme (`s3://` or `s3a://`) was used to invoke it.

#### Healthcheck: `nc` not available in `apache/hive:3.1.3`

Use bash TCP redirection instead of netcat:

```yaml
test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/localhost/9083"]
```

#### Teradata OTF / Iceberg workflow

```sql
-- 1. Create AUTHORIZATION object (once, as DBC or admin)
CREATE AUTHORIZATION MinIOAuth
  AS DEFINER TRUSTED
  USER 'minioadmin' PASSWORD 'minioadmin';

-- 2. Create DATALAKE pointing at Hive Metastore + MinIO
CREATE DATALAKE MyIceberg
  USING (
    LOCATION('/s3/192.168.1.242:9000/iceberg/warehouse/')
    STORAGETYPE('ICEBERG')
    CATALOG('HIVE')
    CATALOGHOST('192.168.1.242:9083')
    EXTERNAL SECURITY MinIOAuth
  );

-- 3. Validate
HELP DATALAKE MyIceberg;

-- 4. Create a namespace (maps to Hive database)
CREATE DATABASE MyIceberg.mydb;

-- 5. Create an Iceberg table
CREATE TABLE MyIceberg.mydb.trades ( ... );
```

`STORAGE_LOCATION` must use `s3://` (not `s3a://`) — Teradata OTF always emits
`s3://`. The `fs.s3.impl` alias above handles the Hive side.

### dbt / Teradata

- `dbt-teradata` requires Python ≥ 3.8 and `teradatasql` driver installed
- Use `REPLACE VIEW` not `CREATE OR REPLACE VIEW` for Teradata views
- The `generate_schema_name.sql` macro is critical — without it dbt prepends
  target schema names, breaking the `ext`/`stg`/`marts` database routing
- Teradata `TIMESTAMP` arithmetic with `INTERVAL` requires the right-hand
  operand to be `INTEGER * INTERVAL '1' SECOND` — casting the epoch division
  result to `INTEGER` before multiplying is required

### MinIO upgrades

When upgrading MinIO to a new version, always run `docker compose down -v`
to remove old volumes (XL metadata format changes between releases).
