# BEACON — Usage Guide

Japanese translation: [`docs/usage.ja.md`](usage.ja.md)

This guide is for analysts and operators who run BEACON day-to-day. For
environment setup see [docs/setup.md](setup.md). For Cloud Run deployment
see [docs/deploy.md](deploy.md).

---

## Web Dashboard

Start the dashboard:

```bash
uv run beacon web          # default: http://localhost:8000
```

The dashboard has five tabs:

| Tab | Purpose |
|-----|---------|
| **Dashboard** | Pipeline summary: PIR count, collection status, choke-points |
| **PIR** | Generate PIR, review output, auto-load previous runs from StorageBackend |
| **Assets** | Load `assets_*.json` draft, complete org-known fields (owner, security controls, CVE mappings), save to StorageBackend |
| **Collection** | Run TRACE `crawl-single` / `crawl-batch` via subprocess |
| **Threats** | SAGE API proxy: actor search, TTP lookup, threat-summary |
| **Settings** | Configure storage mode, SAGE URL, TRACE path; persisted to `.beacon_settings.json` |

Settings priority chain: **env vars > `.beacon_settings.json` > defaults**.

---

## CLI Commands

All commands are exposed through the `beacon` entry point installed by `uv sync`.

### `beacon pir-generate`

Generate a PIR JSON from a business context document.

As of 2.1.0 this command also emits three companion draft artifacts from the
same parsed context in a single pass:

| Artifact | StorageBackend category | Filename pattern |
|----------|------------------------|-----------------|
| `assets.json` | `assets` | `assets_<YYYYMMDDHHmm>.json` |
| `identity_assets.json` | `assets` | `identity_assets_<YYYYMMDDHHmm>.json` |
| `user_accounts.json` | `assets` | `user_accounts_<YYYYMMDDHHmm>.json` |

`asset_vulnerabilities` and `actor_targets` remain empty in the drafts —
fill them in after running STIX ETL or the dedicated generate commands.

```bash
beacon pir-generate                    # uses input/context.md, full LLM mode
beacon pir-generate --no-llm           # dictionary-only, no Gemini call
beacon pir-generate --no-sage          # skip SAGE actor-triage enrichment
beacon pir-generate --use-sage         # explicitly enable SAGE enrichment
beacon pir-generate --save-context     # save structured BusinessContext to output/
```

### `beacon assets-generate`

Generate `assets.json` from the business context.

```bash
beacon assets-generate
beacon assets-generate --no-llm
```

### `beacon identity-generate`

Generate `identity_assets.json` (Identity nodes + `has_access` edges).

```bash
beacon identity-generate
beacon identity-generate --no-llm
```

### `beacon accounts-generate`

Generate `user_accounts.json` (UserAccount nodes + `account_on_asset` edges).

```bash
beacon accounts-generate
```

### `beacon web`

Launch the web dashboard.

```bash
beacon web                 # http://localhost:8000
beacon web --no-web        # dry-run / validation only (no server started)
```

---

## Key Flags

| Flag | Effect |
|------|--------|
| `--use-sage` | Enable SAGE actor-triage API calls |
| `--no-sage` | Disable SAGE calls (useful when SAGE is unavailable) |
| `--no-llm` | Skip all Gemini / Vertex AI calls; dictionary-only mode |
| `--no-web` | Skip launching the web server |
| `--save-context` | Write the parsed `BusinessContext` JSON to `output/` |

---

## PIR Review Workflow

1. **Generate** — run `beacon pir-generate` or click **Generate** in the PIR tab.
2. **Review** — the PIR tab displays each PIR with its score breakdown. Review
   likelihood, impact, intelligence level, and actor tags.
3. **Approve** — use the **Settings** tab to configure the approval workflow.
   The web dashboard replaces the deprecated `submit_for_review.py` GHE flow.
4. **Export** — approved artifacts are saved via the configured StorageBackend
   (`local` or `gcs`). File names follow the pattern
   `<type>_<YYYYMMDDHHmm>.json` (e.g. `pir_202506011430.json`).

---

## Assets Tab Workflow

The **Assets** tab lets operators complete the org-known draft fields of
`assets.json` in the browser without hand-editing JSON.

### What you can edit here

| Field | Location in assets.json | Notes |
|-------|------------------------|-------|
| `owner` | per asset | Team name or email address |
| `security_control_ids` | per asset | Comma-separated control IDs |
| `security_controls` | top-level list | Define EDR/SIEM/firewall entries |
| `asset_vulnerabilities` | top-level list | CVE id → asset_id from org scanner |

**`actor_targets` is CTI-derived and is not editable here.** It is populated
automatically by SAGE ETL when threat actors are ingested from STIX bundles.

### Step-by-step

1. **Generate** — run `beacon pir-generate` (or use the PIR tab). This stores
   three draft files in the StorageBackend `assets` category:
   `assets_<ts>.json`, `identity_assets_<ts>.json`, `user_accounts_<ts>.json`.

2. **Load draft** — open the **Assets** tab. Under **Stored Assets Drafts**,
   click **Load** next to the `assets_*.json` draft you want to edit. The
   draft is loaded into the browser session.

3. **Complete org-known fields**:
   - Fill in the **Owner** column for each asset (team or email).
   - Add **Security Control IDs** (comma-separated) that protect each asset.
   - Paste or edit the **Security Controls** JSON array to define EDR, SIEM,
     firewall entries (each entry needs `id`, `name`, `type`).
   - Paste the **Asset Vulnerabilities** JSON array from your vulnerability
     scanner output. Each entry must have:
     - `vuln_stix_id_ref`: CVE id (format `CVE-<year>-<4+ digits>`)
     - `asset_id`: id of the affected asset
     - `remediation_status` (optional): `open` | `in_progress` | `resolved`

4. **Save** — click **Save to StorageBackend**. A new
   `assets_<YYYYMMDDHHmm>.json` is written to the configured StorageBackend.

5. **Load into SAGE** — from the `SAGE/` directory:

   ```bash
   uv run python cmd/load_assets.py --file output/assets.json
   ```

   SAGE 1.2.0+ creates a stub `Vulnerability` node for any CVE that is not yet
   in Spanner (deterministic uuid5 id matching TRACE's naming). When a STIX
   bundle containing the same CVE is later ingested, SAGE upserts (enriches)
   the existing stub node — no data is lost.

### CVE id validation

CVE ids in `asset_vulnerabilities` are validated client-side (format
`^CVE-\d{4}-\d{4,}$`). The save endpoint rejects any entry with a
malformed id with HTTP 400.

---

## Common Tasks

### Change LLM model tier

Set `VERTEX_MODEL` in `.env` (or export it before running):

```bash
VERTEX_MODEL=gemini-2.0-flash beacon pir-generate
```

Available values depend on your Vertex AI project quota.

### Load a previous PIR result

The PIR tab lists previous runs fetched from the StorageBackend. Select a run
from the dropdown to load it into the review view without regenerating.

Alternatively, pass the path directly:

```bash
beacon pir-generate --input output/pir_202506011430.json --review-only
```

### Switch to GCS storage

```bash
export BEACON_STORAGE=gcs
export BEACON_GCS_BUCKET=my-beacon-bucket
beacon pir-generate
```

See [docs/setup.md](setup.md) for the full list of storage environment
variables.

---

## MISP Cache Refresh

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

---

## SAGE Integration — Manual ETL Verification

This section describes the procedure for deploying BEACON-generated PIRs into SAGE
and verifying that `pir_adjusted_criticality` is updated correctly.

---

### Prerequisites

- SAGE is running and Spanner schema is initialized (`make init-schema` in SAGE/)
- `GCP_PROJECT_ID` and `SPANNER_INSTANCE_ID` are configured in SAGE's environment
- You have write access to the Spanner instance
- `pir_output.json` has been generated by BEACON (`uv run python cmd/generate_pir.py`)

---

### Step 1: Generate PIR

```bash
cd BEACON/
uv run python cmd/generate_pir.py \
  --context path/to/business_context.json \
  --output pir_output.json \
  --collection-plan collection_plan.md
```

Optionally review `pir_output.json` before proceeding:

```bash
cat pir_output.json | python -m json.tool
```

Expected fields in each PIR entry:

| Field | Type | Example |
|-------|------|---------|
| `pir_id` | string | `"PIR-2026-001"` |
| `threat_actor_tags` | list[str] | `["apt-china", "ransomware"]` |
| `asset_weight_rules` | list[dict] | `[{"tag": "plm", "criticality_multiplier": 2.5}]` |
| `valid_from` | ISO date string | `"2026-04-04"` |
| `valid_until` | ISO date string | `"2027-04-04"` |
| `intelligence_level` | string | `"strategic"` |

---

### Step 2: Validate PIR for SAGE Compatibility

PIR validation moved to TRACE in BEACON 0.9.0 (`BEACON/cmd/validate_pir.py`
was deleted in BEACON 0.10.0). The richer validator covers schema plus
referential checks (taxonomy presence, asset-tag match, validity window).

```bash
cd ../TRACE && uv run python cmd/validate_pir.py --pir pir_output.json
# Optionally pass --assets to verify every asset_weight_rules.tag matches
# at least one tag in your assets.json:
cd ../TRACE && uv run python cmd/validate_pir.py --pir pir_output.json --assets assets.json
```

---

### Step 3: Deploy PIR to SAGE

Copy `pir_output.json` to the path configured in SAGE's `PIR_FILE_PATH` environment variable:

```bash
# Default SAGE PIR path (check SAGE/src/sage/config.py for PIR_FILE_PATH)
cp pir_output.json /path/to/sage/config/pir.json

# Or set the env var to point directly to BEACON output:
export PIR_FILE_PATH=/path/to/beacon/pir_output.json
```

---

### Step 4: Run SAGE ETL

From the `SAGE/` directory:

```bash
cd ../SAGE/
uv run python cmd/run_etl.py
```

SAGE ETL will:
1. Load `pir_output.json` via `PIRFilter.from_file()`
2. Filter STIX ThreatActors by `threat_actor_tags` (only relevant actors ingested)
3. Build `Targets` edges automatically from PIR actor × asset tag matching
4. Compute `pir_adjusted_criticality` for all assets using `asset_weight_rules`

ETL log lines to watch for:

```
pir_loaded          count=1
pir_filter_applied  relevant_actors=N  skipped=M
targets_generated   count=K
```

---

### Step 5: Verify `pir_adjusted_criticality`

#### Via SAGE Visualizer

```bash
uv run python cmd/visualize_graph.py
```

Open the generated HTML. Assets targeted by PIR-matched actors should show
elevated criticality scores.

#### Via Spanner CLI (gcloud)

```bash
gcloud spanner databases execute-sql sage-db \
  --instance=$SPANNER_INSTANCE_ID \
  --sql="SELECT id, name, criticality, pir_adjusted_criticality, tags
         FROM Asset
         ORDER BY pir_adjusted_criticality DESC
         LIMIT 20"
```

Expected results: assets whose `tags` overlap with any `asset_weight_rules[].tag`
from the PIR should have `pir_adjusted_criticality > criticality`.

#### Expected multiplier behavior

The formula applied by SAGE (`src/sage/pir/filter.py:adjust_asset_criticality`):

```
pir_adjusted_criticality = min(base_criticality × max_matching_multiplier, 10.0)
```

When a Targets edge also exists (PIR-matched actor → asset):

```
pir_adjusted_criticality = min(base × max_multiplier × 1.5, 10.0)
```

**Example:** Asset with `tags=["plm"]`, `criticality=4.0`, PIR rule `{"tag":"plm","criticality_multiplier":2.5}`:
- No Targets edge: `min(4.0 × 2.5, 10.0) = 10.0`
- With Targets edge: `min(4.0 × 2.5 × 1.5, 10.0) = 10.0` (capped)

---

### Step 6: Verify Targets Edges

```bash
gcloud spanner databases execute-sql sage-db \
  --instance=$SPANNER_INSTANCE_ID \
  --sql="SELECT actor_stix_id, asset_id, confidence, source
         FROM Targets
         WHERE source = 'pir_auto'
         LIMIT 20"
```

Each row represents a threat actor → asset targeting relationship inferred from the PIR.
`confidence` (0–100) reflects tag overlap between the actor and PIR threat_actor_tags.

---

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `pir_adjusted_criticality == criticality` | Asset tags don't overlap with PIR `asset_weight_rules` | Check asset `tags` in Spanner vs PIR `asset_weight_rules[*].tag` |
| No `Targets` rows with `source='pir_auto'` | No actors with matching tags OR no assets with matching tags | Verify actor ingestion completed; check `threat_actor_tags` coverage |
| `pir_loaded count=0` | Wrong `PIR_FILE_PATH` or empty file | Verify path and re-run BEACON |
| PIR validation fails | Missing required field | Re-run BEACON and check `pir_output.json` |

---

### Recommended Update Cadence

| Trigger | Action |
|---------|--------|
| Quarterly review | Re-run BEACON with updated `business_context.json` |
| M&A announcement | Update `business_context.json` with new trigger; re-generate PIR |
| OT system expansion | Add new crown jewels and supply chain entries; re-generate PIR |
| Major threat actor campaign | Update `schema/threat_taxonomy.json`; re-generate PIR |
| New regulatory requirement | Update `organization.regulatory_context`; re-generate PIR |

After regenerating, always validate with `TRACE/cmd/validate_pir.py` before deploying to SAGE.

---

### Identity Asset Handoff (Initiative A + Initiative C Phase 2)

BEACON also emits `identity_assets.json` describing per-identity access on
internal assets. SAGE 0.6.0+ ingests it into the `HasAccess` edge table
(Initiative A). From BEACON 0.13.0 / SAGE 0.9.0 / TRACE 1.6.0 (Initiative C
Phase 2), two additional fields propagate through the handoff:

| Field | Producer | Consumer effect |
|-------|----------|-----------------|
| `is_high_value_impersonation_target: bool` | BEACON 0.13.0+ (LLM-populated when the identity is a publicly-recognizable brand, executive role with public exposure, or critical supplier per HLD §4.3) | SAGE 0.9.0+: `effective_priority` formula on `ImpersonatesIdentity` switches to multiplier=1.5 unconditionally when this flag is true; falls back to `HIGH_VALUE_IMPERSONATION_ROLES` role-tag intersection (15-entry frozenset) when false. TRACE 1.6.0+: PIR L2 relevance score gains a +0.2 boost when the crawled document mentions a flagged identity name. |
| `impersonation_risk_factors: list[str]` | BEACON 0.13.0+ (free-form tags, e.g. `["public-facing-brand", "executive", "trusted-supplier"]`) | Stored on the SAGE `Identity` row for analyst-facing dashboards; not used in `effective_priority` formula. |

Both fields are optional with safe defaults (`False` / `[]`), so BEACON 0.12.x
`identity_assets.json` artifacts remain valid input to SAGE 0.9.0 / TRACE 1.6.0
without migration. See `docs/initiative_c_attributed_impersonates.md` §11 in
the project root for the full Initiative C Phase 2 design.
