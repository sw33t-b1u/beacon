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
