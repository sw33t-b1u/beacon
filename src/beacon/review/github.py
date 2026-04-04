"""GHE (GitHub / GitHub Enterprise) Issue creation client for PIR review workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class IssueResult:
    issue_number: int
    html_url: str
    pir_id: str


class GHEClient:
    """Thin HTTP client for creating GitHub/GHE Issues."""

    def __init__(self, token: str, repo: str, api_base: str = "https://api.github.com"):
        if not token:
            raise ValueError("GHE_TOKEN is not set. Cannot create Issues without authentication.")
        if not repo:
            raise ValueError("GHE_REPO is not set. Specify as 'owner/repo'.")
        self._token = token
        self._repo = repo
        self._api_base = api_base.rstrip("/")

    def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> dict:
        """POST /repos/{owner}/{repo}/issues and return the response JSON."""
        url = f"{self._api_base}/repos/{self._repo}/issues"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        logger.info("creating_ghe_issue", repo=self._repo, title=title)
        resp = httpx.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def add_comment(self, issue_number: int, body: str) -> None:
        """POST /repos/{owner}/{repo}/issues/{issue_number}/comments."""
        url = f"{self._api_base}/repos/{self._repo}/issues/{issue_number}/comments"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        resp = httpx.post(url, json={"body": body}, headers=headers, timeout=15)
        resp.raise_for_status()


def build_issue_body(pir: dict) -> str:
    """Build the Markdown body for a PIR review Issue."""
    risk = pir.get("risk_score", {})
    likelihood = risk.get("likelihood", "?")
    impact = risk.get("impact", "?")
    composite = risk.get("composite", "?")

    threat_tags = " ".join(f"`{t}`" for t in pir.get("threat_actor_tags", []))

    asset_rows = "\n".join(
        f"| {r['tag']} | {r['criticality_multiplier']} |" for r in pir.get("asset_weight_rules", [])
    )
    asset_table = f"| Tag | Multiplier |\n|-----|---|\n{asset_rows}" if asset_rows else "_None_"

    collection_items = "\n".join(f"- {item}" for item in pir.get("collection_focus", []))

    return f"""## PIR Review Request
**Generated:** {pir.get("valid_from", "N/A")} | **Valid Until:** {pir.get("valid_until", "N/A")}
**Risk Score:** L={likelihood}, I={impact}, Composite={composite}

### Description
{pir.get("description", "_No description_")}

### Rationale
{pir.get("rationale", "_No rationale_")}

### Threat Actor Tags
{threat_tags or "_None_"}

### Asset Weight Rules
{asset_table}

### Collection Focus
{collection_items or "_None_"}

## Review Checklist
- [ ] Description is accurate
- [ ] Threat actor tags are appropriate
- [ ] Asset weight rules are correct
- [ ] Approved for SAGE deployment
"""


def submit_pirs_for_review(
    pirs: list[dict],
    client: GHEClient,
    collection_plan_text: str | None = None,
) -> list[IssueResult]:
    """Create a GHE Issue for each PIR.  Returns created IssueResult list."""
    results: list[IssueResult] = []

    for pir in pirs:
        pir_id = pir.get("pir_id", "PIR-UNKNOWN")
        level = pir.get("intelligence_level", "unknown")
        title = f"[PIR Review] {pir_id} — {level}"
        body = build_issue_body(pir)

        issue_data = client.create_issue(title, body, labels=["pir-review"])
        issue_number = issue_data["number"]
        html_url = issue_data["html_url"]

        # Attach collection plan as comment if provided
        if collection_plan_text:
            comment_body = f"## Collection Plan\n\n```\n{collection_plan_text}\n```"
            client.add_comment(issue_number, comment_body)

        logger.info("issue_created", pir_id=pir_id, issue_number=issue_number, url=html_url)
        results.append(IssueResult(issue_number=issue_number, html_url=html_url, pir_id=pir_id))

    return results
