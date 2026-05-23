# BEACON Operations Guide

## MISP cache refresh

### Purpose

BEACON uses a local copy of the [MISP Galaxy](https://github.com/MISP/misp-galaxy)
threat-actor cluster (`cache/misp-threat-actor.json`) as a taxonomy fallback
for actor attribution, target-industry classification, and sophistication scoring.
The cache is loaded by `MispClient` and queried during PIR generation (Initiative D/E).

Keeping the cache fresh ensures that newly-added actors and updated metadata from
the MISP community are reflected in BEACON output without requiring a code change.

### Running the refresh

```bash
# Default: writes to cache/misp-threat-actor.json
uv run python -m cmd.refresh_misp_cache

# Custom output path
uv run python -m cmd.refresh_misp_cache --output /path/to/misp-threat-actor.json

# Validate download without writing to disk
uv run python -m cmd.refresh_misp_cache --dry-run

# All options
uv run python -m cmd.refresh_misp_cache --help
```

### Recommended cron entry (daily at 03:00 local)

```cron
0 3 * * * cd /path/to/beacon && unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy FTP_PROXY ftp_proxy RSYNC_PROXY GRPC_PROXY grpc_proxy NO_PROXY no_proxy; export UV_CACHE_DIR=$TMPDIR/uv-cache; uv run python -m cmd.refresh_misp_cache >> /var/log/beacon/misp_refresh.log 2>&1
```

Create the log directory before enabling the cron entry:

```bash
mkdir -p /var/log/beacon
```

### Failure semantics

The script is designed to be **safe-to-fail**:

- If the download or parse fails, the **existing cache is left untouched**
  (atomic write via `tempfile` + `os.replace` ensures no partial writes).
- The downstream BEACON pipeline continues to use the stale cache and emits a
  structured `warning` log line instead of failing.
- Exit codes: `0` = success, `1` = HTTP/network error, `2` = JSON parse error.

### Alerting guidance

Monitor `/var/log/beacon/misp_refresh.log` for repeated failures. Recommended checks:

1. **Consecutive failures (>3):** search for `"event": "misp_cache_refresh.fetch_failed"`
   or `"misp_cache_refresh.http_error"` across three or more consecutive days.

2. **Cache age:** inspect `_metadata.last_auto_sync` in the cache file:

   ```bash
   python3 -c "import json; d=json.load(open('cache/misp-threat-actor.json')); \
       print(d.get('_metadata', {}).get('last_auto_sync', 'N/A'))"
   ```

   Alert if the timestamp is more than 7 days old.

3. **Log format:** all lines are structured JSON (via `structlog`). Example success line:

   ```json
   {"event": "misp_cache_refresh.done", "output_path": "cache/misp-threat-actor.json",
    "last_auto_sync": "2026-05-23T03:00:01Z", "values_count": 994, "timestamp": "..."}
   ```
