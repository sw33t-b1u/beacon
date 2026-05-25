"""SAGE Analysis API client — fetches actor observation data + recent incidents.

Three categories of endpoints are consumed:

- `GET /asset-exposure` — actor-tag observation count for risk_scorer
  likelihood boost. Fail-open (returns 0 on error).
- `GET /api/incidents` — recent IR-registered incidents for actor_triage
  IR-boost (Initiative G Phase 6). Fail-loud (raises on error; caller
  handles fail-soft + data_quality.degraded flag).
- Threats tab endpoints (Initiative I Phase 3) — all fail-soft (return
  empty list / dict on error so the web UI degrades gracefully):
    - `GET /actors?name=<query>&limit=<n>` — actor name search
    - `GET /actor-ttps?actor_id=<id>&since=<date>&until=<date>` — TTP list
    - `GET /threat-summary?asset=<id>&since=<date>&until=<date>` — threat summary

The two original error-handling policies differ deliberately: risk_scorer
treats SAGE as advisory; actor_triage propagates IR-availability into the
PIR's data_quality block so analysts know when the IR-boost was skipped.
"""

from __future__ import annotations

import os
from datetime import date

import httpx
import structlog

logger = structlog.get_logger(__name__)


class SageAPIClient:
    """Client for SAGE Analysis API.

    `get_actor_observation_count` is fail-open (returns 0 on any failure).
    `get_recent_incidents` is fail-loud (raises httpx exceptions) — callers
    handle fail-soft policy (Initiative G Phase 6 wires data_quality.degraded
    on actor_triage when the call raises).
    """

    def __init__(self, base_url: str, *, bearer_token: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        # Bearer token may be passed explicitly (tests) or sourced from env.
        # SAGE Phase 1 (Decision 10) makes GET routes permissive when token is
        # unset on the server side; BEACON sends the header only when it has one.
        self._bearer_token = (
            bearer_token if bearer_token is not None else os.environ.get("SAGE_API_AUTH_TOKEN", "")
        )

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._bearer_token}"} if self._bearer_token else {}

    def get_actor_observation_count(self, threat_actor_tags: list[str]) -> int:
        """Call GET /asset-exposure and count actors whose tags overlap with threat_actor_tags.

        Returns 0 when SAGE API is unreachable or returns an error (fail-open design).
        """
        if not threat_actor_tags:
            return 0

        url = f"{self._base_url}/asset-exposure"
        try:
            resp = httpx.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as exc:
            logger.warning("sage_api_timeout", url=url, error=str(exc))
            return 0
        except httpx.HTTPError as exc:
            logger.warning("sage_api_error", url=url, error=str(exc))
            return 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("sage_api_unexpected_error", url=url, error=str(exc))
            return 0

        tag_set = set(threat_actor_tags)
        count = 0
        for actor in data.get("actors", []):
            actor_tags = set(actor.get("tags", []))
            if actor_tags & tag_set:
                count += 1

        logger.info("sage_observation_count", count=count, tags=threat_actor_tags)
        return count

    def get_recent_incidents(
        self,
        since: date,
        until: date,
        actor_stix_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Call GET /api/incidents with since/until/actor_stix_id/limit filters.

        Returns the parsed `incidents` list from the response body
        (empty list when SAGE has no matching rows). Raises
        `httpx.HTTPError` / `httpx.TimeoutException` on transport
        failure — the caller (actor_triage IR-boost) catches these and
        sets `data_quality.degraded=True` plus neutral IR factors.
        Auth header is sent when `SAGE_API_AUTH_TOKEN` is configured;
        SAGE GET routes are permissive when the token is unset on the
        server side (per Decision 10).
        """
        params: dict[str, str | int] = {
            "since": since.isoformat(),
            "until": until.isoformat(),
            "limit": limit,
        }
        if actor_stix_id is not None:
            params["actor_stix_id"] = actor_stix_id

        url = f"{self._base_url}/api/incidents"
        resp = httpx.get(url, params=params, headers=self._auth_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # SAGE Phase 2 response shape: {"incidents": [...], "count": N} or bare list
        if isinstance(data, dict):
            incidents = data.get("incidents", [])
        else:
            incidents = data if isinstance(data, list) else []

        logger.info(
            "sage_incidents_fetched",
            url=url,
            count=len(incidents),
            actor_stix_id=actor_stix_id,
            since=since.isoformat(),
            until=until.isoformat(),
        )
        return incidents

    # ------------------------------------------------------------------
    # Threats-tab methods (Initiative I Phase 3) — all fail-soft
    # ------------------------------------------------------------------

    def search_actors(self, name: str, limit: int = 20) -> list[dict]:
        """Search SAGE for threat actors matching *name*.

        Calls ``GET /actors?name={name}&limit={limit}``.
        Returns an empty list on any error (fail-soft — web UI degrades
        gracefully when SAGE is unavailable or slow).
        """
        url = f"{self._base_url}/actors"
        params: dict[str, str | int] = {"name": name, "limit": limit}
        try:
            resp = httpx.get(url, params=params, headers=self._auth_headers(), timeout=5)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as exc:
            logger.warning("sage_search_actors_timeout", url=url, error=str(exc))
            return []
        except httpx.HTTPError as exc:
            logger.warning("sage_search_actors_error", url=url, error=str(exc))
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("sage_search_actors_unexpected", url=url, error=str(exc))
            return []

        actors: list[dict] = []
        if isinstance(data, dict):
            actors = data.get("actors", [])
        elif isinstance(data, list):
            actors = data

        logger.info("sage_search_actors", name=name, count=len(actors))
        return actors

    def get_actor_ttps(
        self,
        actor_id: str,
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict]:
        """Fetch TTPs for a specific actor.

        Calls ``GET /actor-ttps?actor_id={actor_id}&since={since}&until={until}``.
        Returns an empty list on any error (fail-soft).
        """
        url = f"{self._base_url}/actor-ttps"
        params: dict[str, str] = {"actor_id": actor_id}
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        try:
            resp = httpx.get(url, params=params, headers=self._auth_headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as exc:
            logger.warning("sage_actor_ttps_timeout", url=url, actor_id=actor_id, error=str(exc))
            return []
        except httpx.HTTPError as exc:
            logger.warning("sage_actor_ttps_error", url=url, actor_id=actor_id, error=str(exc))
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("sage_actor_ttps_unexpected", url=url, actor_id=actor_id, error=str(exc))
            return []

        ttps: list[dict] = []
        if isinstance(data, dict):
            ttps = data.get("ttps", [])
        elif isinstance(data, list):
            ttps = data

        logger.info("sage_actor_ttps_fetched", actor_id=actor_id, count=len(ttps))
        return ttps

    def get_threat_summary(
        self,
        asset_id: str,
        since: str | None = None,
        until: str | None = None,
    ) -> dict:
        """Fetch threat summary for a given asset.

        Calls ``GET /threat-summary?asset={asset_id}&since={since}&until={until}``.
        Returns an empty dict on any error (fail-soft).
        """
        url = f"{self._base_url}/threat-summary"
        params: dict[str, str] = {"asset": asset_id}
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        try:
            resp = httpx.get(url, params=params, headers=self._auth_headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as exc:
            logger.warning(
                "sage_threat_summary_timeout", url=url, asset_id=asset_id, error=str(exc)
            )
            return {}
        except httpx.HTTPError as exc:
            logger.warning("sage_threat_summary_error", url=url, asset_id=asset_id, error=str(exc))
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sage_threat_summary_unexpected", url=url, asset_id=asset_id, error=str(exc)
            )
            return {}

        if not isinstance(data, dict):
            logger.warning(
                "sage_threat_summary_unexpected_shape", url=url, asset_id=asset_id, shape=type(data)
            )
            return {}

        logger.info("sage_threat_summary_fetched", asset_id=asset_id)
        return data
