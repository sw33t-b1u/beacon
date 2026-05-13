"""Pydantic v2 input schema for BusinessContext."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Organization(BaseModel):
    name: str
    unit_name: str = ""  # department / team name (e.g. "Financial Crime Intelligence Team")
    unit_type: Literal["company", "division", "department", "team"] = "company"
    industry: Literal[
        "manufacturing",
        "finance",
        "energy",
        "healthcare",
        "defense",
        "technology",
        "logistics",
        "government",
        "education",
        "other",
    ]
    sub_industries: list[str] = Field(default_factory=list)
    geography: list[str] = Field(default_factory=list)
    employee_count_range: str = ""
    revenue_range_usd: str = ""
    stock_listed: bool = False
    regulatory_context: list[str] = Field(default_factory=list)


class StrategicObjective(BaseModel):
    id: str
    title: str
    description: str = ""
    timeline: str = ""
    sensitivity: Literal["low", "medium", "high", "critical"] = "medium"
    key_decisions: list[str] = Field(default_factory=list)


class Project(BaseModel):
    id: str
    name: str
    status: Literal["planned", "in_progress", "completed", "cancelled"] = "in_progress"
    sensitivity: Literal["low", "medium", "high", "critical"] = "medium"
    involved_vendors: list[str] = Field(default_factory=list)
    cloud_providers: list[str] = Field(default_factory=list)
    data_types: list[str] = Field(default_factory=list)


class CrownJewel(BaseModel):
    id: str
    name: str
    system: str = ""
    business_impact: Literal["low", "medium", "high", "critical"] = "high"
    exposure_risk: Literal["low", "medium", "high", "critical"] = "medium"


class CriticalAsset(BaseModel):
    """Detailed technical asset record — from the Critical Assets section of context.md."""

    id: str
    name: str
    type: Literal[
        "server",
        "database",
        "network_device",
        "application",
        "endpoint",
        "storage",
        "identity_system",
        "ot_device",
        "cloud_service",
        "other",
    ] = "other"
    function: str = ""  # what the asset does in the business context
    hostname: str = ""  # optional — e.g. "erp-prod-01.internal"
    os_platform: str = ""  # optional — e.g. "Windows Server 2022", "RHEL 9"
    network_zone: Literal[
        "internet", "dmz", "corporate", "ot", "cloud", "restricted", "unknown"
    ] = "unknown"
    criticality: Literal["low", "medium", "high", "critical"] = "high"
    data_types: list[str] = Field(default_factory=list)
    managing_vendor: str = ""  # vendor responsible for management/operation
    supply_chain_role: str = ""  # non-empty when asset is part of supply chain connectivity
    dependencies: list[str] = Field(default_factory=list)  # other asset IDs this depends on
    exposure_risk: Literal["low", "medium", "high", "critical"] = "medium"


class SupplyChain(BaseModel):
    critical_vendors: list[str] = Field(default_factory=list)
    cloud_providers: list[str] = Field(default_factory=list)
    ot_connectivity: bool = False


# ---------------------------------------------------------------------------
# Initiative A — Identity-Asset (BEACON 0.11.0)
# ---------------------------------------------------------------------------
# Identity granularity decision (2026-05-10): role / group primary, individuals
# optional. STIX 2.1 §6.7 identity-class-ov vocabulary is honoured directly.
# See docs/initiative_a_identity_asset.md §3 for the design rationale.


class Identity(BaseModel):
    """Person / role / group / organization granted access to assets.

    Maps onto a STIX 2.1 §4.4 identity SDO when emitted to SAGE. ``id`` is
    BEACON-internal (stable string the analyst chooses); SAGE assigns the
    final ``identity--<uuid>`` STIX id at ingest.
    """

    id: str
    name: str
    identity_class: Literal[
        "individual",
        "group",
        "system",
        "organization",
        "class",
        "unknown",
    ] = "group"
    sectors: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    description: str = ""
    # Initiative C Phase 2 (0.13.0): flag-first impersonation prioritization.
    # SAGE 0.9.0 consumes this to apply effective_priority multiplier=1.5;
    # TRACE 1.6.0 PIR L2 gate uses it to boost relevance score for
    # documents that mention flagged identity names.
    is_high_value_impersonation_target: bool = False
    impersonation_risk_factors: list[str] = Field(default_factory=list)


class HasAccess(BaseModel):
    """Identity-to-asset access edge.

    ``identity_id`` references an entry in ``BusinessContext.identities``;
    ``asset_id`` references ``CriticalAsset.id`` (cross-file reference is
    enforced by TRACE's validate_identity_assets, not here).
    """

    identity_id: str
    asset_id: str
    access_level: Literal["read", "write", "admin", "deny"] = "read"
    role: str = ""  # free-form per-edge label (e.g. "ERP admin")
    granted_at: str = ""  # ISO date; empty = unknown
    revoked_at: str = ""  # ISO date; empty = active


# ---------------------------------------------------------------------------
# Initiative B — User-Account SCO (BEACON 0.12.0)
# ---------------------------------------------------------------------------
# Account-level granularity: individual login identifiers (alice@corp,
# svc-jenkins, S-1-5-21-...) tied to Identity (1:N optional) and to host
# Assets (AccountOnAsset edge). Sources: BEACON authoritative
# (`source=beacon`) + TRACE CTI extraction (`source=trace`).
# See docs/initiative_b_user_account.md §3 for the design rationale.


class UserAccount(BaseModel):
    """An individual login account on internal hosts.

    ``account_type`` strictly follows STIX 2.1 §6.4 ``account-type-ov``.
    Empty string is the documented default for "unspecified / no
    suitable spec value". 0.12.1 dropped operationally-named extensions
    (``service`` / ``other`` / ``unix-account`` / ``azure-ad`` etc) —
    operational distinctions move to:

    - ``is_service_account: bool`` (STIX 2.1 §6.4 native property) for
      service / automation accounts.
    - ``description`` for free-form context (e.g. "Azure AD tenant
      contoso.onmicrosoft.com") when STIX has no suitable
      ``account_type`` value.

    Migration (existing user_accounts.json):
    - ``unix-account`` → ``unix`` (rename to spec value)
    - ``service`` → empty string + ensure ``is_service_account: true``
    - ``other`` → empty string
    - ``azure-ad`` / ``google-workspace`` / ``saas`` / ``kerberos`` →
      empty string (STIX has no spec value); add note in
      ``description``.
    """

    id: str
    account_login: str
    display_name: str = ""
    account_type: Literal[
        "",  # unspecified / no suitable STIX vocab value
        "unix",
        "windows-local",
        "windows-domain",
        "ldap",
        "tacacs",
        "radius",
        "nis",
        "openid",
        "facebook",
        "skype",
        "twitter",
        "kavi",
    ] = ""
    is_privileged: bool = False
    is_service_account: bool = False
    identity_id: str = ""  # optional FK to BusinessContext.identities[*].id
    description: str = ""


class AccountOnAsset(BaseModel):
    """User-account ↔ host asset edge.

    Composite key (user_account_id, asset_id). Same login on two hosts
    yields two edges. Lifecycle dates (first_seen / last_seen) support
    ISO/IEC 27001 A.5.16 identity lifecycle review.
    """

    user_account_id: str
    asset_id: str
    first_seen: str = ""  # ISO date or empty
    last_seen: str = ""


class RecentIncident(BaseModel):
    year: int
    type: str
    impact: Literal["low", "medium", "high", "critical"] = "low"


# ---------------------------------------------------------------------------
# Top-level model
# ---------------------------------------------------------------------------


class BusinessContext(BaseModel):
    organization: Organization
    strategic_objectives: list[StrategicObjective] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    crown_jewels: list[CrownJewel] = Field(default_factory=list)
    critical_assets: list[CriticalAsset] = Field(default_factory=list)
    supply_chain: SupplyChain = Field(default_factory=SupplyChain)
    recent_incidents: list[RecentIncident] = Field(default_factory=list)
    identities: list[Identity] = Field(default_factory=list)
    has_access: list[HasAccess] = Field(default_factory=list)
    user_accounts: list[UserAccount] = Field(default_factory=list)
    account_on_asset: list[AccountOnAsset] = Field(default_factory=list)
