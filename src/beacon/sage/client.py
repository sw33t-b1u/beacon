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

import base64
import binascii
import json
import os
import time
from datetime import date

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Re-fetch an OIDC token this many seconds before its `exp` to avoid
# sending a token that expires mid-flight (BEACON 3.0.2).
_OIDC_EXPIRY_MARGIN_SECONDS = 60


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
        # When a static token is set, it is sent verbatim (preserves
        # local/test/app-token behavior). When unset, the client mints a
        # Google OIDC ID token for Cloud Run service-to-service auth
        # (BEACON 3.0.2).
        self._bearer_token = (
            bearer_token if bearer_token is not None else os.environ.get("SAGE_API_AUTH_TOKEN", "")
        )
        # In-memory only OIDC token cache, keyed by audience. Never persisted
        # to disk. Value is (token, expiry_epoch_seconds).
        self._oidc_cache: dict[str, tuple[str, float]] = {}

    def _auth_headers(self) -> dict[str, str]:
        """Build the Authorization header for a SAGE call.

        Priority:
        (a) static token (constructor arg / SAGE_API_AUTH_TOKEN) — sent verbatim.
        (b) else a Google OIDC ID token minted for audience=self._base_url.
        (c) on any OIDC failure — no header (fail-soft; the server enforces auth).

        A Bearer header is only ever attached over HTTPS so a token can never
        leak over a plaintext connection.
        """
        if not self._base_url.startswith("https://"):
            return {}

        if self._bearer_token:
            return {"Authorization": f"Bearer {self._bearer_token}"}

        oidc = self._fetch_oidc_token()
        if oidc:
            return {"Authorization": f"Bearer {oidc}"}
        return {}

    def _fetch_oidc_token(self) -> str:
        """Return a cached or freshly minted Google OIDC ID token.

        Caches the token in memory keyed by audience until ~60s before its
        `exp` claim. Returns an empty string on any failure (no metadata
        server locally/in tests, or any google-auth error) so the caller
        falls back to header-less requests. Token values are never logged.
        """
        audience = self._base_url
        cached = self._oidc_cache.get(audience)
        if cached is not None:
            token, expiry = cached
            if time.time() < expiry - _OIDC_EXPIRY_MARGIN_SECONDS:
                return token

        try:
            import google.auth.transport.requests
            import google.oauth2.id_token

            request = google.auth.transport.requests.Request()
            token = google.oauth2.id_token.fetch_id_token(request, audience)
        except Exception as exc:  # noqa: BLE001
            # No metadata server (local/test) or any google-auth error.
            # Do not include token material in the log.
            logger.warning("sage_oidc_fetch_failed", url=audience, error=str(exc))
            return ""

        expiry = self._decode_token_exp(token)
        if expiry is not None:
            self._oidc_cache[audience] = (token, expiry)
        return token

    @staticmethod
    def _decode_token_exp(token: str) -> float | None:
        """Read the `exp` claim from a JWT without verifying its signature.

        Used only to schedule cache expiry; no signature verification is
        performed and no verification dependency is introduced. Returns
        None if the claim cannot be read.
        """
        try:
            payload_b64 = token.split(".")[1]
            padding = "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
            exp = payload.get("exp")
            return float(exp) if exp is not None else None
        except (IndexError, ValueError, binascii.Error, TypeError):
            return None

    def get_actor_observation_count(self, threat_actor_tags: list[str]) -> int:
        """Call GET /asset-exposure and count actors whose tags overlap with threat_actor_tags.

        Returns 0 when SAGE API is unreachable or returns an error (fail-open design).
        """
        if not threat_actor_tags:
            return 0

        url = f"{self._base_url}/asset-exposure"
        try:
            resp = httpx.get(url, headers=self._auth_headers(), timeout=5)
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
