"""Pydantic v2 input schema for BusinessContext."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Organization(BaseModel):
    name: str
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
    supply_chain: SupplyChain = Field(default_factory=SupplyChain)
    recent_incidents: list[RecentIncident] = Field(default_factory=list)
