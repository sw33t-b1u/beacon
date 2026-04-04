"""SAGE Analysis API client — fetches actor observation data for likelihood scoring."""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger(__name__)


class SageAPIClient:
    """Client for SAGE Analysis API.  Never raises — returns 0 on any failure."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

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
