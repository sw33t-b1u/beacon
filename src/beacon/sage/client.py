"""SAGE Analysis API client — fetches actor observation data + recent incidents.

Two endpoints are consumed:

- `GET /asset-exposure` — actor-tag observation count for risk_scorer
  likelihood boost. Fail-open (returns 0 on error).
- `GET /api/incidents` — recent IR-registered incidents for actor_triage
  IR-boost (Initiative G Phase 6). Fail-loud (raises on error; caller
  handles fail-soft + data_quality.degraded flag).

The two error-handling policies differ deliberately: risk_scorer treats
SAGE as advisory; actor_triage propagates IR-availability into the PIR's
data_quality block so analysts know when the IR-boost was skipped.
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
