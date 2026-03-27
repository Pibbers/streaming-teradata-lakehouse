# agents.md — Notes for AI Agents Working in This Repository

This file captures non-obvious findings, debugging patterns, and hard-won
knowledge for agents working on the `streaming-teradata-lakehouse` project.
For architecture and normal usage see [CLAUDE.md](CLAUDE.md).

---

## Hive Metastore Container (`crypto-hive-metastore`)

### Never add `hadoop-common` to `/opt/hive/lib/`

The base image `apache/hive:3.1.3` bundles `hadoop-common-3.1.0.jar` at
`/opt/hadoop/share/hadoop/common/`. Adding any other version of `hadoop-common`
to `/opt/hive/lib/` creates a classpath conflict. Symptom:

```
java.lang.NoSuchMethodError: org.apache.hadoop.security.HadoopKerberosName.setRuleMechanism
```

The JVM loads `UserGroupInformation` from the newer jar, which calls
`setRuleMechanism` — a method that doesn't exist in the older
`HadoopKerberosName`. The container crashes immediately at startup.

**All Hadoop JARs you add must be pinned to version 3.1.0.**

To verify which `hadoop-common` the base image ships:

```bash
docker run --rm --entrypoint bash apache/hive:3.1.3 \
  -c "find /opt/hadoop/share -name 'hadoop-common*.jar'"
```

### `hive.metastore.warehouse.dir` must have a non-empty path component

`s3a://iceberg` is invalid — it has scheme=`s3a`, authority=`iceberg`, and an
**empty path**. Hive's `Warehouse.getDnsPath()` passes that empty string to
`new Path(...)` and throws `IllegalArgumentException`. Use `s3a://iceberg/warehouse`.

### Docker named volume persists `hive-site.xml` across rebuilds

The compose service mounts `hive_metastore_config:/opt/hive/conf`. Rebuilding
the image does **not** update files inside a named volume. After editing
`docker/hive-site.xml`, you must also update the volume contents:

```bash
# Option A — full teardown (loses all volumes)
docker compose -f docker/compose.yml down -v
docker compose -f docker/compose.yml up -d --build

# Option B — update config only, keep other volumes
docker run --rm \
  -v docker_hive_metastore_config:/conf \
  -v $(pwd)/docker/hive-site.xml:/src/hive-site.xml \
  alpine cp /src/hive-site.xml /conf/hive-site.xml
docker compose -f docker/compose.yml restart hive-metastore
```

The entrypoint runs `envsubst` over `/opt/hive/conf/hive-site.xml` at every
container start, expanding `${VAR}` placeholders from environment variables.

### Healthcheck: `nc` is not installed in `apache/hive:3.1.3`

Use bash TCP redirection:

```yaml
test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/localhost/9083"]
```

---

## Teradata OTF (Open Table Format) + Iceberg + Hive Metastore

### Teradata always uses `s3://` scheme, not `s3a://`

When Teradata OTF calls Hive Metastore's `create_database` thrift RPC it derives
the `locationUri` from `STORAGE_LOCATION` and passes it as `s3://...`. Hadoop 3.x
removed the native `s3://` filesystem. Without an alias the metastore throws:

```
UnsupportedFileSystemException: No FileSystem for scheme "s3"
```

Fix — add to `hive-site.xml`:

```xml
<property>
  <name>fs.s3.impl</name>
  <value>org.apache.hadoop.fs.s3a.S3AFileSystem</value>
</property>
```

`S3AFileSystem` always reads credentials from `fs.s3a.*` keys regardless of
whether the URI scheme is `s3://` or `s3a://`.

### How to confirm what Teradata OTF sent to Hive Metastore

Enable Hive audit logging or check the metastore container logs:

```bash
docker logs crypto-hive-metastore 2>&1 | grep -E "create_database|locationUri"
```

The thrift call looks like:
```
create_database: Database(name:test, locationUri:s3://iceberg/warehouse/test.db, ownerName:teradata, ...)
```

This confirms the scheme and lets you verify the path matches your MinIO layout.

### Test that S3A write connectivity works independently of Teradata

Use Beeline inside the container:

```bash
docker exec -it crypto-hive-metastore bash
/opt/hive/bin/beeline -u "jdbc:hive2://"
> CREATE DATABASE IF NOT EXISTS test_ns;
```

If this succeeds, the issue is Teradata-side (e.g. wrong scheme). If it fails,
the issue is Hive/S3A configuration.

### Teradata OTF `CREATE DATABASE` maps to Hive `create_database` RPC

`CREATE DATABASE myiceberg.test` triggers a Hive Metastore `create_database`
call for namespace `test`. The `locationUri` is inferred from `STORAGE_LOCATION`
in the `CREATE DATALAKE` statement:

- `STORAGE_LOCATION('s3://iceberg/warehouse/')` → namespace at `s3://iceberg/warehouse/test.db`

Error `[7825 : 38000] [1212]: Failed to create namespace test in Hive Metastore`
means the thrift call failed server-side. Always check the metastore container
logs for the root cause.

---

## Docker Compose Operational Notes

### Rebuilding a single service without losing volumes

```bash
docker compose -f docker/compose.yml up -d --build hive-metastore
```

This rebuilds only the `hive-metastore` image and recreates its container,
leaving other containers and **all named volumes** untouched.

### Checking container health

```bash
docker compose -f docker/compose.yml ps
# or
docker inspect --format '{{.State.Health.Status}}' crypto-hive-metastore
```

### Viewing recent metastore logs

```bash
docker logs crypto-hive-metastore --tail 100 -f
```

---

## Debugging Checklist — Hive Metastore Won't Start

1. `docker logs crypto-hive-metastore` — look for Java exception class name
2. `NoSuchMethodError` → Hadoop JAR version conflict (see above)
3. `IllegalArgumentException: Can not create a Path` → empty/invalid warehouse dir
4. `Communications link failure` → MySQL not ready yet (healthcheck ordering issue)
5. Container healthy but `CREATE DATABASE` from Teradata fails → check `fs.s3.impl`
   and metastore logs for the exact `locationUri` Teradata is sending

---

## MinIO

### Volume must be removed when upgrading MinIO versions

MinIO uses a metadata format (XL) that is not backwards-compatible across major
releases. Always `docker compose down -v` before upgrading the MinIO image tag.

### Buckets required

- `crypto-trades` — Parquet files written by consumer
- `iceberg` — Iceberg warehouse (Hive Metastore warehouse dir = `s3a://iceberg/warehouse`)

Created automatically by the `minio-init` one-shot container on first `up`.
