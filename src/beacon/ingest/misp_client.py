"""MISP Galaxy threat-actor client with graceful degradation.

ActorAttributes is co-located here rather than in a sibling actor_attributes.py because
it is exclusively consumed by MispClient at this phase. Phase 3 (actor_triage.py) can
import it directly from this module; a split is deferred until actor_triage needs to
import ActorAttributes without pulling in MispClient.

Data flow:
  cache_path provided → load from local JSON (offline / sandbox mode)
  server_url + api_key provided → fetch via PyMISP (optional dep; graceful on ImportError)
  neither → degraded mode; get_actor() always returns None
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict

_log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# STIX 2.1 open vocabulary sets — used for OV validation
# threat-actor-motivation-ov (STIX 2.1 §10.2)
# ---------------------------------------------------------------------------
_MOTIVATION_OV: frozenset[str] = frozenset(
    [
        "accidental",
        "coercion",
        "dominance",
        "ideology",
        "notoriety",
        "organizational-gain",
        "personal-gain",
        "personal-satisfaction",
        "revenge",
        "unpredictable",
    ]
)

# threat-actor-sophistication-ov (STIX 2.1 §10.2)
_SOPHISTICATION_OV: frozenset[str] = frozenset(
    ["none", "minimal", "intermediate", "advanced", "expert", "innovator", "strategic"]
)


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------


class ActorAttributes(BaseModel):
    """Normalized threat-actor attributes drawn from MISP Galaxy.

    All STIX OV fields (primary_motivation, sophistication) are validated
    against the official vocabulary; invalid values are set to None.
    """

    model_config = ConfigDict(extra="allow")

    primary_motivation: str | None = None
    secondary_motivations: list[str] = []
    sophistication: str | None = None
    target_industries: list[str] = []
    target_geographies: list[str] = []
    aliases: list[str] = []
    active: bool | None = None
    degraded: bool = False
    source: Literal["misp_cache", "misp_live", "none"] = "none"
    # MISP cluster UUID — used by actor_triage IR-boost to construct the STIX
    # intrusion-set id sent to SAGE (`intrusion-set--{actor_uuid}`). Optional
    # because the field is only populated when the underlying MISP entry
    # carried a uuid; live-mode entries may omit it.
    actor_uuid: str | None = None


# ---------------------------------------------------------------------------
# Helper: OV validation
# ---------------------------------------------------------------------------


def _validate_ov(value: str | None, vocab: frozenset[str], field: str) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in vocab:
        return normalized
    _log.warning("invalid_stix_ov", field=field, value=value)
    return None


# ---------------------------------------------------------------------------
# MispClient
# ---------------------------------------------------------------------------


class MispClient:
    """Loads MISP Galaxy threat-actor data and resolves actors by name or UUID.

    Priority order:
      1. Local cache file (cache_path) — used in offline / sandbox environments.
      2. Live MISP server (server_url + api_key) via PyMISP optional dependency.
      3. Degraded — no source configured; get_actor() returns None.
    """

    def __init__(
        self,
        cache_path: Path | str | None = None,
        server_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._actors: list[dict] = []
        self._loaded = False
        self._source: Literal["misp_cache", "misp_live", "none"] = "none"

        if cache_path is not None:
            self._load_from_cache(Path(cache_path))
        elif server_url and api_key:
            self._load_from_live(server_url, api_key)

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------

    def _load_from_cache(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._actors = data.get("values", [])
            self._loaded = True
            self._source = "misp_cache"
        except FileNotFoundError:
            _log.warning("misp_cache_not_found", path=str(path))
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            _log.warning("misp_cache_malformed", error=str(exc))

    def _load_from_live(self, server_url: str, api_key: str) -> None:
        try:
            import pymisp  # optional dep — graceful on ImportError

            misp = pymisp.PyMISP(server_url, api_key, ssl=False)
            galaxy = misp.search_galaxy_clusters(
                galaxy_uuid="698774c7-8022-42c4-917f-8d6e4f06ada3",  # MISP threat-actor galaxy
                pythonify=True,
            )
            self._actors = [
                {
                    "uuid": c.uuid,
                    "value": c.value,
                    "description": getattr(c, "description", ""),
                    "meta": getattr(c, "meta", {}),
                }
                for c in (galaxy if isinstance(galaxy, list) else [])
            ]
            self._loaded = True
            self._source = "misp_live"
        except ImportError:
            _log.warning("pymisp_not_installed", hint="pip install pymisp>=2.4")
        except Exception as exc:
            _log.warning("misp_live_fetch_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_actor(self, name_or_uuid: str) -> ActorAttributes | None:
        """Return ActorAttributes for the given actor name, alias, or UUID.

        Matching is case-insensitive. Returns None if not found or if no
        data source was available (degraded mode).
        """
        if not self._actors:
            return None

        needle = name_or_uuid.strip().lower()
        for actor in self._actors:
            if actor.get("uuid", "").lower() == needle:
                return self._parse_actor(actor)
            if actor.get("value", "").lower() == needle:
                return self._parse_actor(actor)
            meta = actor.get("meta") or {}
            for alias in meta.get("synonyms", []):
                if isinstance(alias, str) and alias.lower() == needle:
                    return self._parse_actor(actor)
        return None

    # ------------------------------------------------------------------
    # Internal: parse raw MISP actor dict → ActorAttributes
    # ------------------------------------------------------------------

    def _parse_actor(self, actor: dict) -> ActorAttributes:
        meta: dict = actor.get("meta") or {}

        # primary_motivation: prefer "motivation" / "primary-motivation" meta fields.
        # cfr-type-of-incident ("Espionage", "Financial Crime", …) is NOT a STIX OV
        # value and will normalize to None — that is correct per spec.
        raw_motivation = meta.get("motivation") or meta.get("primary-motivation")
        primary_motivation = _validate_ov(raw_motivation, _MOTIVATION_OV, "primary_motivation")

        secondary_raw: list = meta.get("secondary-motivations", [])
        secondary_motivations = [
            v
            for v in (
                _validate_ov(m, _MOTIVATION_OV, "secondary_motivations")
                for m in (secondary_raw if isinstance(secondary_raw, list) else [])
                if isinstance(m, str)
            )
            if v is not None
        ]

        sophistication = _validate_ov(
            meta.get("sophistication"), _SOPHISTICATION_OV, "sophistication"
        )

        # target_industries: merge cfr-target-category + targeted-sector (deduplicated)
        industries: list[str] = []
        for key in ("cfr-target-category", "targeted-sector"):
            val = meta.get(key)
            if isinstance(val, list):
                industries.extend(v for v in val if isinstance(v, str))
            elif isinstance(val, str):
                industries.append(val)
        seen: set[str] = set()
        target_industries = [x for x in industries if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

        target_geographies: list[str] = []
        victims = meta.get("cfr-suspected-victims", [])
        if isinstance(victims, list):
            target_geographies = [v for v in victims if isinstance(v, str)]

        aliases: list[str] = []
        synonyms = meta.get("synonyms", [])
        if isinstance(synonyms, list):
            aliases = [s for s in synonyms if isinstance(s, str)]

        raw_uuid = actor.get("uuid")
        actor_uuid = raw_uuid if isinstance(raw_uuid, str) and raw_uuid else None

        return ActorAttributes(
            primary_motivation=primary_motivation,
            secondary_motivations=secondary_motivations,
            sophistication=sophistication,
            target_industries=target_industries,
            target_geographies=target_geographies,
            aliases=aliases,
            active=None,
            degraded=False,
            source=self._source,
            actor_uuid=actor_uuid,
        )
