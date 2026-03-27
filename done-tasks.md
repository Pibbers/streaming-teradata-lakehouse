# done-tasks.md — Completed Work Log

---

## 2026-03-27

### Fix: `crypto-hive-metastore` container crash loop

**Problem**: The Hive Metastore container kept restarting and never reached healthy state.

**Root causes found and fixed**:

1. **Hadoop JAR version conflict** (`NoSuchMethodError: HadoopKerberosName.setRuleMechanism`)
   - `docker/Dockerfile.hive-metastore` was downloading `hadoop-common-3.3.1.jar` and
     `hadoop-shaded-guava-1.1.0.jar` to `/opt/hive/lib/`, conflicting with the
     `hadoop-common-3.1.0.jar` already bundled in the `apache/hive:3.1.3` base image.
   - Also downgraded `hadoop-aws` from 3.3.1 → 3.1.0 and `aws-java-sdk-bundle`
     from 1.11.901 → 1.11.271 to match the bundled Hadoop version.
   - Removed the `hadoop-common` and `hadoop-shaded-guava` downloads entirely.

2. **Empty warehouse path** (`IllegalArgumentException: Can not create a Path from an empty string`)
   - `hive.metastore.warehouse.dir` was set to `s3a://iceberg` (empty path component).
   - Changed to `s3a://iceberg/warehouse` in `docker/hive-site.xml`.

3. **Stale config in Docker named volume**
   - The named volume `docker_hive_metastore_config` persisted the old broken config
     across image rebuilds. Updated the volume contents directly using an Alpine container.

4. **Healthcheck used `nc` which is not installed**
   - Changed healthcheck in `docker/compose.yml` from `nc -z localhost 9083` to
     `bash -c "exec 3<>/dev/tcp/localhost/9083"`.

**Files changed**:
- `docker/Dockerfile.hive-metastore` — removed conflicting JARs, downgraded hadoop-aws
- `docker/hive-site.xml` — fixed warehouse dir path
- `docker/compose.yml` — fixed healthcheck command

---

### Fix: `CREATE DATABASE myiceberg.test` fails with Teradata OTF error 7825/1212

**Problem**: After the Hive Metastore was running and healthy, creating an Iceberg
namespace from Teradata (`CREATE DATABASE myiceberg.test`) failed with:
`Failed [7825 : 38000] [1212]: Failed to create namespace test in Hive Metastore`

**Root cause**: Teradata OTF derives the namespace `locationUri` from `STORAGE_LOCATION`
and passes it to Hive Metastore's `create_database` thrift RPC as `s3://...` (not
`s3a://`). Hadoop 3.x removed the native `s3://` filesystem provider, so Hive threw
`UnsupportedFileSystemException: No FileSystem for scheme "s3"`.

**Fix**: Added `fs.s3.impl = org.apache.hadoop.fs.s3a.S3AFileSystem` to
`docker/hive-site.xml`. This aliases `s3://` to `S3AFileSystem`, which reads
credentials from the existing `fs.s3a.*` keys.

**Files changed**:
- `docker/hive-site.xml` — added `fs.s3.impl` property
- Updated Docker named volume contents to pick up the config change without full teardown

---

### Documentation: updated CLAUDE.md and created agents.md

Added detailed notes on all Hive Metastore issues encountered, Hadoop classpath rules,
Docker named volume behaviour, Teradata OTF `s3://` scheme behaviour, and operational
debugging checklists to `CLAUDE.md` (Known Issues section) and the new `agents.md`.
