# Crypto Kafka Streaming Pipeline

## Overview

This project implements a real-time crypto trade streaming and analytics
platform using a modern **lakehouse architecture** with **Apache Iceberg**.
It ingests live BTCUSDT trade data from Binance, streams events through
Kafka, persists Hive-partitioned Parquet files in MinIO, catalogs tables
with **Hive Metastore**, transforms data with dbt and Teradata, orchestrates
refreshes with Airflow, and visualises analytics through a Streamlit dashboard.

The system demonstrates event-driven ingestion, lakehouse-style storage with
ICEBERG ACID transactions and time-travel queries, analytical modelling,
containerised deployment, orchestration, and observability.

------------------------------------------------------------------------

## What This Project Demonstrates

- Event-driven streaming architecture
- Kafka-based durable ingestion with DLQ handling
- S3-compatible object storage (MinIO) with Hive-partitioned Parquet
- **Apache Iceberg** open table format with ACID transactions and time-travel queries
- **Hive Metastore 3.1.3** as metadata catalog with MySQL backend
- Enterprise data warehousing with Teradata Vantage
- Native Object Store (NOS) — Teradata reads Iceberg tables directly from MinIO/S3
- dbt modelling best practices (staging + marts) with dbt-teradata adapter
- Data quality testing
- Observability and latency tracking
- Containerised services (Docker Compose) with health checks
- Airflow orchestration (scheduled dbt runs + nightly tests)
- Interactive analytics dashboard

------------------------------------------------------------------------

## Architecture

``` mermaid
flowchart TD
    A[Binance WebSocket<br>BTCUSDT Trades] --> B[Producer Container]
    B --> C[Kafka Broker<br>KRaft Mode]
    C --> D[Consumer Container]
    D --> E[MinIO Object Store<br>Hive-partitioned Parquet]
    E --> HM[Hive Metastore<br>MySQL Backend]
    HM --> F[Iceberg Tables<br>s3://iceberg]
    F --> G[Teradata NOS<br>ext.trades foreign table]
    G --> H[dbt Staging Models]
    H --> I[dbt Mart Models]
    I --> J[Streamlit Dashboard]
    I --> K[Pipeline Observability Tables]
    L[Airflow Scheduler] -- "*/5 min dbt run" --> H
    L -- "02:00 UTC dbt test" --> H
```

------------------------------------------------------------------------

## Technology Stack

- Python 3.11
- uv / uvx (package management and execution)
- Binance WebSocket API
- **Apache Kafka** (Confluent 7.6.1, KRaft mode)
- Confluent Kafka Python Client
- **MinIO** (S3-compatible object store, RELEASE.2024-10-29T16-01-48Z)
- Polars + boto3 (Parquet writing to MinIO)
- **Apache Iceberg** (open table format with ACID transactions)
- **Hive Metastore 3.1.3** (metadata catalog, custom Docker image)
- **MySQL 8.0.39** (Hive metastore backend)
- **Teradata Vantage** (analytical engine)
- **Teradata NOS** (Native Object Store — reads Iceberg tables from MinIO/S3)
- dbt-core + **dbt-teradata**
- **Apache Airflow 2.9** with LocalExecutor (PostgreSQL 17 backend)
- Streamlit + Plotly (dashboard)
- **Docker Compose** (full stack orchestration)

------------------------------------------------------------------------

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed
- **Docker Desktop running** (all infrastructure services are containerized)
- **Teradata Vantage** instance accessible (Teradata Express, Vantage Trial,
  or a managed instance). The NOS feature must be enabled for Iceberg table access.
- A `.env` file at the project root (copy from `.env.example`)
- At least 6GB free disk space for Docker volumes (Kafka, MinIO, MySQL, Hive)

------------------------------------------------------------------------

## Quickstart — Fully Containerised

The simplest way to run the full pipeline. Everything runs in Docker —
no local Python environment needed for the pipeline itself.

### 1. Copy the environment file and set Teradata credentials

```bash
cp .env.example .env
```

Edit `.env` and set `TERADATA_HOST`, `TERADATA_USER`, `TERADATA_PASSWORD`
to point at your Teradata instance.

### 2. Start the pipeline (infra + producer + consumer)

```bash
docker compose -f docker/compose.yml up -d --build
```

This starts seven containers:

- **crypto-kafka** — Kafka broker (KRaft mode) on port 9092
- **crypto-minio** — MinIO S3 API on port 9000, web console on port 9001
- **crypto-minio-init** — one-shot: creates `crypto-trades` and `iceberg` buckets
- **crypto-mysql-metastore** — MySQL 8.0.39 backend for Hive metastore
- **crypto-hive-metastore** — Hive Metastore 3.1.3 on port 9083 (Iceberg catalog)
- **crypto-producer** — streams Binance trades into Kafka
- **crypto-consumer** — reads from Kafka, writes Parquet files to MinIO

Browse the MinIO console at [http://localhost:9001](http://localhost:9001)
(user: `minioadmin`, password: `minioadmin`).

Watch live logs:

```bash
docker compose -f docker/compose.yml logs -f producer consumer
```

### 3. Start Airflow (orchestration)

```bash
docker compose -f docker/compose.yml -f docker/compose.airflow.yml up -d --build
```

The Airflow UI is at [http://localhost:8080](http://localhost:8080)
(user: `admin`, password: `admin`).

Two DAGs start automatically:

| DAG | Schedule | Task |
| --- | --- | --- |
| `crypto_dbt_refresh` | Every 5 minutes | `dbt run` — refreshes all mart tables |
| `crypto_dbt_test` | Daily 02:00 UTC | `dbt test` — data-quality validation |

### 4. Initialise Teradata (run once, from the project root)

```bash
uvx --from . crypto-init-db
```

This creates the `ext`, `stg`, and `marts` Teradata databases and the
`ext.trades` NOS foreign table that reads Parquet files directly from MinIO.

### 5. Launch the dashboard

```bash
uvx --from ".[dashboard]" crypto-dashboard
```

------------------------------------------------------------------------

## Quickstart — Host-side Producer/Consumer (development)

Run producer and consumer via `uvx` on the host while infrastructure runs
in Docker. Useful for rapid iteration without rebuilding images.

### 1. Start infrastructure only

```bash
docker compose -f docker/compose.yml up -d kafka minio minio-init
```

### 2. Start producer and consumer

```bash
uvx --from . crypto-producer          # terminal 1
uvx --from . crypto-consumer          # terminal 2
```

### 3. Initialise Teradata and build dbt models

```bash
uvx --from . crypto-init-db
uvx --from . crypto-dbt run
```

Pass any standard dbt flags as usual:

```bash
uvx --from . crypto-dbt run --select fct_candles_1m
uvx --from . crypto-dbt test
```

### 4. Launch the dashboard

```bash
uvx --from ".[dashboard]" crypto-dashboard
```

------------------------------------------------------------------------

## Available Commands

| Command | Description |
| --- | --- |
| `crypto-producer` | Connect to Binance WebSocket and publish trades to Kafka |
| `crypto-consumer` | Consume from Kafka and write Hive-partitioned Parquet to MinIO |
| `crypto-init-db` | Create Teradata databases and NOS foreign table for MinIO access |
| `crypto-query-db` | Print the latest rows from each mart table |
| `crypto-dbt <args>` | Run dbt with project/profiles dirs pre-set |
| `crypto-dashboard` | Launch the Streamlit analytics dashboard (requires `[dashboard]` extras) |

------------------------------------------------------------------------

## Configuration

Copy `.env.example` to `.env`. All values ship with working defaults for
the local Docker setup, except Teradata credentials which must point at
your instance:

```env
KAFKA_BOOTSTRAP=localhost:9092
PARQUET_ROOT=s3://crypto-trades
MINIO_ENDPOINT=http://localhost:9000

TERADATA_HOST=localhost
TERADATA_USER=dbc
TERADATA_PASSWORD=dbc
TERADATA_SCHEMA=crypto_db
```

When producer and consumer run as Docker containers, `KAFKA_BOOTSTRAP` and
`MINIO_ENDPOINT` are overridden automatically in `docker/compose.yml` to
use Docker-internal hostnames (`kafka:29092`, `http://minio:9000`).

------------------------------------------------------------------------

## Data Flow

1. Binance trade stream (`btcusdt@trade`) provides real-time trade events.
2. Producer validates each event against a JSON schema and publishes to
   Kafka topic `crypto.trades.v1`. Invalid events go to the DLQ topic.
3. Consumer reads from Kafka and writes partitioned Parquet to MinIO:
   `s3://crypto-trades/pair=BTCUSDT/trade_date=YYYY-MM-DD/hour=HH/`
4. **Hive Metastore** catalogs Parquet files as Iceberg tables in the
   `s3://iceberg` warehouse location. Iceberg provides ACID transactions,
   schema evolution, and time-travel query capabilities.
5. Teradata reads Iceberg tables directly from MinIO via the `ext.trades` NOS
   foreign table (Native Object Store with inline S3 credentials).
   `pair`, `trade_date`, and `hour` columns are derived from partition structure.
6. Airflow triggers `dbt run` every 5 minutes to rebuild mart tables:
   - `stg_trades` — cleaned staging layer from raw Parquet
   - `fct_trades_1m` — 1-minute trade aggregation (Iceberg table)
   - `fct_candles_1m` — OHLCV + VWAP candles (Iceberg table)
   - `fct_orderflow_1m` — buy/sell imbalance (Iceberg table)
   - `fct_ingestion_latency_1m` — latency percentiles (Iceberg table)
   - `fct_pipeline_health_5m` — trade counts and freshness metrics (Iceberg table)
7. Streamlit reads the mart tables from Teradata for real-time analytics visualisation.

------------------------------------------------------------------------

## Mart Models

### fct_trades_1m

Aggregated trade statistics (count, volume, notional, price range) per minute.

### fct_candles_1m

OHLCV candles with VWAP.  Open and close prices use `ROW_NUMBER()` window
functions (Teradata equivalent of DuckDB's `arg_min` / `arg_max`).

### fct_orderflow_1m

Buy/sell side split: quantity imbalance, notional imbalance, and volume ratios.

### fct_ingestion_latency_1m

Latency between `trade_ts` and `ingested_at`: avg, min, max, p95, p99.
Percentiles use `PERCENTILE_CONT … WITHIN GROUP … OVER` (Teradata ordered
analytical function).

### fct_pipeline_health_5m

Rolling 5-minute trade counts and seconds since last trade / last ingest.

------------------------------------------------------------------------

## Iceberg Features & Benefits

All mart tables are **Apache Iceberg** tables, providing:

| Feature | Benefit |
| --- | --- |
| ACID Transactions | Concurrent writes and reads without corrupting data |
| Schema Evolution | Add, drop, or rename columns without rebuilding tables |
| Time-Travel Queries | Query historical snapshots: `SELECT * FROM table FOR SYSTEM_TIME AS OF '2026-03-26 10:00:00'` |
| Partition Evolution | Change partition scheme without data migration |
| Hidden Partitioning | Efficient pruning without partition column exposure |
| Compaction | Automatic small-file compaction to improve query performance |
| Metadata Versioning | Full history of schema and data changes |

**Hive Metastore Integration**: All Iceberg metadata is tracked in Hive Metastore,
enabling cross-tool compatibility and centralized table discovery.

------------------------------------------------------------------------

## Teradata-Specific SQL Notes

The dbt models use Teradata-native syntax throughout:

| Concept | DuckDB (previous) | Teradata (current) |
| --- | --- | --- |
| Truncate to minute | `date_trunc('minute', ts)` | `TRUNC(ts, 'MI')` |
| First/last value in group | `arg_min(price, ts)` | `ROW_NUMBER()` + `CASE WHEN` |
| Filtered aggregate | `count(*) filter (where …)` | `SUM(CASE WHEN … THEN 1 ELSE 0 END)` |
| Percentiles | `approx_quantile(col, 0.95)` | `PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY col) OVER (PARTITION BY …)` |
| Current timestamp | `now()` | `CURRENT_TIMESTAMP` |
| Timestamp diff | `datediff('second', a, b)` | `EXTRACT(DAY FROM (b-a))*86400 + …` |
| Epoch ms → timestamp | `to_timestamp(ts/1000.0)` | `TIMESTAMP '1970-01-01 00:00:00' + CAST(ts/1000 AS INTEGER) * INTERVAL '1' SECOND` |
| Boolean | `BOOLEAN` | `BYTEINT` (1 = true, 0 = false) |

------------------------------------------------------------------------

## Observability

- Ingestion latency percentiles (p95, p99) surfaced in `fct_ingestion_latency_1m`
- Pipeline freshness metrics in `fct_pipeline_health_5m`
- DLQ handling routes invalid events to `crypto.trades.dlq.v1`
- Airflow UI provides DAG run history, task logs, and failure alerts

------------------------------------------------------------------------

## Infrastructure Versions

All Docker images are pinned to **latest stable versions** for security,
performance, and reliability:

| Component | Version | Updated | Rationale |
| --- | --- | --- | --- |
| Kafka | 7.6.1 | ✓ | Latest Confluent Platform with KRaft stability |
| MinIO | RELEASE.2024-10-29T16-01-48Z | ✓ | Stable S3 API and performance improvements |
| MinIO MC | RELEASE.2025-08-13T08-35-41Z | ✓ | Latest client tools for bucket management |
| MySQL | 8.0.39 | ✓ | Latest patch with security updates |
| PostgreSQL | 17 | ✓ | Major version with improved JSON handling |
| Hive Metastore | 3.1.3 (LTS) | ✓ | Stable production release (4.0 is beta) |
| Apache Iceberg | Latest (bundled in dbt) | ✓ | Latest via dbt-teradata adapter |
| Python | 3.11 | — | Stable LTS version |

**Upgrade Notes**: When updating MinIO to a new version, always use
`docker compose down -v` to remove old volumes (XL metadata format changes).

------------------------------------------------------------------------

## Orchestration

Orchestration runs in Docker via Apache Airflow (LocalExecutor + PostgreSQL).
DAGs are defined in [airflow/dags/crypto_pipeline.py](airflow/dags/crypto_pipeline.py).

The `FERNET_KEY` and `SECRET_KEY` in `docker/compose.airflow.yml` are fixed
development-only values. Generate fresh keys for any non-local deployment:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

------------------------------------------------------------------------

## Repository Structure

```text
crypto-kafka-streaming-pipeline/
│
├── .claude/                    # Agent knowledge base for future developers
│   ├── claude.md               # Project architecture & infrastructure details
│   ├── agents.md               # Agent guidance & troubleshooting
│   └── done-tasks.md           # Historical session logs & issue resolutions
├── .env.example                # Environment variable template
├── pyproject.toml              # Package metadata, dependencies, console scripts
├── docker/
│   ├── compose.yml             # Core infra + Hive metastore + pipeline
│   ├── compose.airflow.yml     # Airflow + PostgreSQL orchestration stack
│   ├── Dockerfile              # Producer / consumer image
│   ├── Dockerfile.airflow      # Airflow image (adds dbt-teradata)
│   ├── Dockerfile.hive-metastore # Hive Metastore with MySQL + S3 support
│   └── hive-site.xml           # Hive configuration template (envsubst)
├── airflow/
│   └── dags/
│       └── crypto_pipeline.py  # dbt refresh (*/5 min) + nightly test DAGs
├── src/
│   └── crypto_pipeline/        # Installable Python package
│       ├── producer/           # Binance WebSocket → Kafka
│       ├── consumer/           # Kafka → Parquet (MinIO)
│       ├── schemas/            # JSON schema for trade events
│       ├── storage/            # Partition path builder
│       ├── utils/              # Timestamp utilities
│       └── _cli.py             # Entry points: init-db, query-db, dbt, dashboard
├── warehouse/
│   ├── dbt/                    # dbt project (staging + Iceberg mart models)
│   ├── duckdb/                 # (optional) DuckDB for local testing
│   └── teradata/               # Teradata DDL: database init + NOS foreign table
├── dashboard/                  # Streamlit analytics dashboard
└── scripts/
    └── test_ws.py              # Dev utility: verify Binance WebSocket connection
```

------------------------------------------------------------------------

## Production Deployment Considerations

- **Hive Metastore HA**: Deploy multiple Hive instances with MySQL replication
- **Iceberg Maintenance**: Configure compaction and delete file handling
- **Kafka**: Replace single-node with multi-broker cluster (replication=3 for HA)
- **MinIO**: Use managed S3 / Azure Blob Storage / GCS or multi-node MinIO
- **Airflow**: Replace LocalExecutor with managed platform (MWAA, Cloud Composer) or Kubernetes
- **Teradata**: Use AUTHORIZATION objects instead of inline NOS credentials
- **Secrets**: Use secrets manager (Vault, AWS Secrets Manager) instead of `.env`
- **Monitoring**: Enable Prometheus/Grafana metrics and centralized logging (CloudWatch, ELK)
- **Sizing**: Plan Teradata `PERMANENT` space based on expected Iceberg table volume
- **Security**: Enable TLS/mTLS between services, implement network isolation
- **Backups**: Implement MinIO S3 versioning and regular database backups

------------------------------------------------------------------------

## Future Enhancements

- **Multi-symbol streaming**: Extend producer to stream multiple trading pairs
- **Incremental dbt models**: Implement `dbt run --select state:modified+`
- **Iceberg Maintenance**: Automated compaction and delete file expiration
- **Real-time alerting**: Latency threshold alerts via Airflow or external monitoring
- **Data retention**: Implement S3 lifecycle policies and Iceberg snapshot retention
- **Schema evolution**: Automated handling of new trade fields via Iceberg
- **Lineage tracking**: dbt artifacts + metadata catalog integration
- **Data quality**: Great Expectations framework for anomaly detection

------------------------------------------------------------------------

## Developer Notes

For agent-based development and troubleshooting, see the **`.claude/`** directory:

- **`.claude/claude.md`** — Complete architecture reference, infrastructure details, and configuration
- **`.claude/agents.md`** — Agent guidance for different roles (data pipeline, infrastructure, dbt)
- **`.claude/done-tasks.md`** — Historical task log with issue resolutions and version updates

These files provide comprehensive knowledge transfer for future development sessions.

------------------------------------------------------------------------

## License

This project is intended for educational and portfolio demonstration purposes.

## Author

Virendra Pratap Singh
Senior Data Architect | Data Engineering | Analytics Platforms
[linkedin.com/in/virendra-pratap-singh-iitg](https://www.linkedin.com/in/virendra-pratap-singh-iitg/)
