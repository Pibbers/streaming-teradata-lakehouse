"""CLI entry points for utility commands exposed via uvx / uv tool install."""
from __future__ import annotations


def init_db() -> None:
    """Initialise Teradata for use as the data warehouse (run from project root).

    Steps:
      1. Creates the three Teradata databases used by dbt (ext, stg, marts).
      2. Creates (or replaces) the NOS foreign table ext.trades that reads
         Hive-partitioned Parquet files from MinIO via S3-compatible NOS.

    Prerequisites:
      - Teradata must be reachable at TERADATA_HOST with the given credentials.
      - The user must have CREATE DATABASE privilege (or the databases must
        already exist and the user must have ALL access to them).
      - Teradata NOS must be licensed and enabled.
      - MinIO must be reachable from the Teradata system at MINIO_ENDPOINT.
    """
    import os
    import teradatasql
    from dotenv import load_dotenv, find_dotenv
    from pathlib import Path

    load_dotenv(find_dotenv(usecwd=True))

    host     = os.getenv("TERADATA_HOST",     "localhost")
    user     = os.getenv("TERADATA_USER",     "dbc")
    password = os.getenv("TERADATA_PASSWORD", "dbc")

    # MINIO_ENDPOINT is the endpoint from this machine's perspective (used by
    # producer/consumer containers).  TERADATA_NOS_ENDPOINT is the endpoint as
    # seen from the Teradata server — set this to the LAN IP when Teradata is on
    # a separate host that cannot reach "localhost".
    minio_endpoint = os.getenv("MINIO_ENDPOINT",        "http://localhost:9000")
    nos_endpoint   = os.getenv("TERADATA_NOS_ENDPOINT", minio_endpoint)
    access_key     = os.getenv("MINIO_ACCESS_KEY",      "minioadmin")
    secret_key     = os.getenv("MINIO_SECRET_KEY",      "minioadmin")
    bucket         = os.getenv("MINIO_BUCKET",          "crypto-trades")
    subdir         = os.getenv("PARQUET_TOPIC_SUBDIR",  "trades")

    # Symbol directory: NOS LOCATION must end at the symbol level so that
    # $var1 (subdir) and $symbol (pair) in PATHPATTERN are both "consumed" by
    # the LOCATION prefix, leaving only $var3/$var4/$var5 (date/hour/file) as
    # the virtual columns that PARTITION BY needs to declare.
    # Derive from BINANCE_WS_URL (e.g. ".../ws/btcusdt@trade" → "BTCUSDT")
    # or override explicitly with TRADING_PAIR.
    ws_url = os.getenv("BINANCE_WS_URL", "")
    pair_from_url = ws_url.rstrip("/").split("/")[-1].split("@")[0].upper() if ws_url else "BTCUSDT"
    trading_pair = os.getenv("TRADING_PAIR", pair_from_url)

    host_port    = nos_endpoint.replace("https://", "").replace("http://", "")
    nos_location = f"/s3/{host_port}/{bucket}/{subdir}/{trading_pair}/"
    # Authorization object name — lives in the connecting user's database
    auth_name    = f"{user.upper()}.CRYPTO_MINIO_LOCAL_AUTH"

    print(f"Connecting to Teradata at {host} as {user} ...")
    print(f"NOS location:  {nos_location}")
    print(f"NOS auth:      {auth_name}")

    with teradatasql.connect(host=host, user=user, password=password) as con:
        with con.cursor() as cur:

            # ── 1. Create databases (schemas in Teradata) ─────────────────
            for db, perm_bytes in [
                ("ext",   1_000_000_000),
                ("stg",   5_000_000_000),
                ("marts", 5_000_000_000),
            ]:
                try:
                    cur.execute(
                        f"CREATE DATABASE {db}"
                        f" AS PERMANENT = {perm_bytes} BYTES,"
                        f"    SPOOL     = {perm_bytes} BYTES"
                    )
                    print(f"Created database: {db}")
                except teradatasql.OperationalError as exc:
                    if "already exists" in str(exc).lower() or "3803" in str(exc):
                        print(f"Database {db} already exists — skipping")
                    else:
                        raise

            # ── 2. NOS authorization object (holds MinIO credentials) ──────
            try:
                cur.execute(f"""
                    CREATE AUTHORIZATION {auth_name}
                    AS DEFINER TRUSTED
                    USER     '{access_key}'
                    PASSWORD '{secret_key}'
                """)
                print(f"Created authorization: {auth_name}")
            except teradatasql.OperationalError as exc:
                if "already exists" in str(exc).lower() or "3803" in str(exc):
                    print(f"Authorization {auth_name} already exists — skipping")
                else:
                    raise

            # ── 3. NOS foreign table over MinIO Parquet files ─────────────
            # Drop first so the CREATE below is idempotent.
            try:
                cur.execute("DROP TABLE ext.trades")
                print("Dropped existing ext.trades")
            except teradatasql.OperationalError:
                pass  # table didn't exist yet

            cur.execute(f"""
                CREATE MULTISET FOREIGN TABLE ext.trades ,FALLBACK ,
                    EXTERNAL SECURITY {auth_name} ,
                    MAP = TD_MAP1
                (
                    Location       VARCHAR(2048) CHARACTER SET UNICODE CASESPECIFIC,
                    schema_version BIGINT,
                    event_id       VARCHAR(36)   CHARACTER SET UNICODE NOT CASESPECIFIC,
                    source         VARCHAR(10)   CHARACTER SET UNICODE NOT CASESPECIFIC,
                    ingested_at    VARCHAR(32)   CHARACTER SET UNICODE NOT CASESPECIFIC,
                    symbol         VARCHAR(7)    CHARACTER SET UNICODE NOT CASESPECIFIC,
                    trade_id       BIGINT,
                    trade_ts       BIGINT,
                    price          FLOAT,
                    qty            FLOAT,
                    is_buyer_maker BYTEINT
                )
                USING
                (
                    LOCATION    ('{nos_location}')
                    MANIFEST    ('FALSE')
                    PATHPATTERN ('$var1/$symbol/$var3/$var4/$var5')
                    STOREDAS    ('PARQUET')
                )
                NO PRIMARY INDEX
                PARTITION BY ( COLUMN ,var3 DATE FORMAT 'Y4-MM-DD',var4 BYTEINT )
            """)
            print(f"Created foreign table ext.trades → {nos_location}")

            # ── 4. Verify ─────────────────────────────────────────────────
            cur.execute("""
                SELECT DatabaseName, TableName, TableKind
                FROM DBC.TablesV
                WHERE DatabaseName = 'ext'
            """)
            rows = cur.fetchall()
            print("Objects in database 'ext':")
            for row in rows:
                print(" ", row)

    print("Teradata initialized successfully")


def query_db() -> None:
    """Print the latest rows from each mart table (run from project root)."""
    import os
    import teradatasql
    import pandas as pd
    from dotenv import load_dotenv, find_dotenv

    load_dotenv(find_dotenv(usecwd=True))

    host     = os.getenv("TERADATA_HOST",     "localhost")
    user     = os.getenv("TERADATA_USER",     "dbc")
    password = os.getenv("TERADATA_PASSWORD", "dbc")

    # Teradata uses TOP n instead of LIMIT n
    queries = [
        ("Latest candles",
         "SELECT TOP 5 * FROM marts.fct_candles_1m ORDER BY minute_bucket DESC"),
        ("Latest orderflow",
         "SELECT TOP 5 * FROM marts.fct_orderflow_1m ORDER BY minute_bucket DESC"),
        ("Latest trades_1m",
         "SELECT TOP 5 * FROM marts.fct_trades_1m ORDER BY minute_bucket DESC"),
        ("Latest pipeline_health_5m",
         "SELECT TOP 5 * FROM marts.fct_pipeline_health_5m"),
        ("Latest ingestion_latency_1m",
         "SELECT TOP 5 * FROM marts.fct_ingestion_latency_1m ORDER BY minute_bucket DESC"),
    ]

    with teradatasql.connect(host=host, user=user, password=password) as con:
        for title, sql in queries:
            print(f"\n{title}:\n")
            print(pd.read_sql(sql, con))


def run_dbt() -> None:
    """Run dbt with --project-dir and --profiles-dir pre-set for this project.

    Usage (from project root):
        uvx --from . crypto-dbt run
        uvx --from . crypto-dbt test
        uvx --from . crypto-dbt run --select fct_candles_1m

    Any flag you pass is forwarded directly to dbt. --project-dir and
    --profiles-dir are injected automatically unless you supply them yourself.
    """
    import subprocess
    import sys
    from pathlib import Path

    user_args = sys.argv[1:]

    extra: list[str] = []
    if "--project-dir" not in user_args:
        extra += ["--project-dir", "warehouse/dbt/crypto_dbt"]
    if "--profiles-dir" not in user_args:
        extra += ["--profiles-dir", "warehouse/dbt"]

    # The dbt binary lives alongside python inside the uvx-managed environment.
    dbt_bin = Path(sys.executable).parent / "dbt"

    result = subprocess.run([str(dbt_bin)] + user_args + extra)
    sys.exit(result.returncode)


def dashboard() -> None:
    """Launch the Streamlit dashboard.

    Requires the [dashboard] optional dependencies:
        uvx --from "crypto-kafka-streaming-pipeline[dashboard]" crypto-dashboard
    """
    import importlib.resources as ilr
    import sys

    try:
        from streamlit.web import cli as stcli
    except ImportError:
        print(
            "Streamlit is not installed. Install it with:\n"
            '  uvx --from "crypto-kafka-streaming-pipeline[dashboard]" crypto-dashboard\n'
            "or:\n"
            "  uv pip install crypto-kafka-streaming-pipeline[dashboard]"
        )
        sys.exit(1)

    with ilr.as_file(ilr.files("crypto_pipeline").joinpath("dashboard_app.py")) as app_path:
        sys.argv = ["streamlit", "run", str(app_path)] + sys.argv[1:]
        sys.exit(stcli.main())
