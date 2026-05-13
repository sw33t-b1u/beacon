"""Tests for element_extractor.py."""

from __future__ import annotations

import json
from pathlib import Path

from beacon.analysis.element_extractor import extract
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"


def _load_ctx(filename: str) -> BusinessContext:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return BusinessContext.model_validate(data)


class TestExtractManufacturing:
    def setup_method(self):
        self.ctx = _load_ctx("sample_context_manufacturing.json")
        self.elements = extract(self.ctx)

    def test_industry(self):
        assert self.elements.org_industry == "manufacturing"

    def test_geographies(self):
        assert "Japan" in self.elements.org_geographies
        assert "Southeast Asia" in self.elements.org_geographies

    def test_ot_connectivity(self):
        assert self.elements.has_ot_connectivity is True

    def test_stock_listed(self):
        assert self.elements.has_stock_listing is True

    def test_crown_jewels_extracted(self):
        assert "CJ-001" in self.elements.crown_jewel_ids
        assert "PLM system" in self.elements.crown_jewel_systems
        assert "critical" in self.elements.crown_jewel_impacts

    def test_project_data_types(self):
        assert "financial" in self.elements.project_data_types
        assert "manufacturing" in self.elements.project_data_types

    def test_project_cloud_providers(self):
        assert "GCP" in self.elements.project_cloud_providers

    def test_active_vendors(self):
        assert "SAP" in self.elements.active_vendors
        assert "Accenture" in self.elements.active_vendors

    def test_source_element_ids(self):
        assert "OBJ-001" in self.elements.source_element_ids
        assert "PROJ-001" in self.elements.source_element_ids
        assert "CJ-001" in self.elements.source_element_ids


class TestTriggerDetection:
    """Each trigger is derived from a recognised external framework — see
    BEACON/docs/triggers.md for the full citation table."""

    def setup_method(self):
        self.ctx = _load_ctx("sample_context_manufacturing.json")

    def test_it_ot_convergence_trigger(self):
        # supply_chain.ot_connectivity=true OR critical_assets[].network_zone=="ot"
        elements = extract(self.ctx)
        assert "it_ot_convergence" in elements.active_triggers

    def test_cloud_dependency_trigger(self):
        # Manufacturing fixture has projects with cloud_providers
        elements = extract(self.ctx)
        assert "cloud_dependency" in elements.active_triggers

    def test_third_party_dependency_trigger(self):
        # supply_chain.critical_vendors and/or critical_assets[].managing_vendor
        elements = extract(self.ctx)
        assert "third_party_dependency" in elements.active_triggers

    def test_regulated_disclosure_scope_trigger_from_listing(self):
        # stock_listed=true on this fixture triggers regulated disclosure scope
        elements = extract(self.ctx)
        assert "regulated_disclosure_scope" in elements.active_triggers

    def test_sectoral_high_risk_trigger(self):
        # industry="manufacturing" is in the high-risk set per ENISA/Verizon/CrowdStrike
        elements = extract(self.ctx)
        assert "sectoral_high_risk" in elements.active_triggers

    def test_external_facing_exposure_trigger(self):
        # If any crown jewel has high/critical exposure_risk OR any critical
        # asset is in internet/dmz zone, trigger fires.
        from beacon.ingest.schema import CrownJewel

        ctx = _load_ctx("sample_context_manufacturing.json")
        ctx.crown_jewels.append(
            CrownJewel(
                id="CJ-X",
                name="Public API",
                business_impact="high",
                exposure_risk="high",
            )
        )
        elements = extract(ctx)
        assert "external_facing_exposure" in elements.active_triggers

    def test_ai_adoption_exposure_trigger(self):
        # Add an AI-themed strategic objective; trigger should fire.
        from beacon.ingest.schema import StrategicObjective

        ctx = _load_ctx("sample_context_manufacturing.json")
        ctx.strategic_objectives.append(
            StrategicObjective(
                id="OBJ-AI",
                title="Generative AI rollout",
                description="Deploy LLM-based copilots in manufacturing planning.",
            )
        )
        elements = extract(ctx)
        assert "ai_adoption_exposure" in elements.active_triggers

    def test_ai_adoption_not_triggered_without_keywords(self):
        # Manufacturing fixture has no AI/ML keywords — should not fire.
        elements = extract(self.ctx)
        assert "ai_adoption_exposure" not in elements.active_triggers

    def test_old_trigger_strings_not_emitted(self):
        # Regression: old vocabulary must never appear in output (BREAKING in 0.10.0).
        elements = extract(self.ctx)
        forbidden = {
            "ot_connectivity",
            "cloud_migration",
            "m_and_a",
            "ipo_or_listing",
            "supply_chain_expansion",
        }
        assert not (forbidden & set(elements.active_triggers))

    def test_no_duplicate_triggers(self):
        elements = extract(self.ctx)
        assert len(elements.active_triggers) == len(set(elements.active_triggers))


class TestGeopoliticalExposureTrigger:
    """0.14.0 trigger 8 — fires when any declared geographic touch-point
    is in HIGH_RISK_GEOPOLITICAL_ZONES. Absent block = no signal (does
    NOT fire). See docs/triggers.md §8."""

    def _base_ctx(self):
        from beacon.ingest.schema import BusinessContext, Organization

        return BusinessContext(organization=Organization(name="X", industry="other"))

    def test_absent_block_does_not_fire(self):
        elements = extract(self._base_ctx())
        assert "geopolitical_exposure" not in elements.active_triggers

    def test_hq_in_high_risk_zone_fires(self):
        from beacon.ingest.schema import GeopoliticalExposure

        ctx = self._base_ctx()
        ctx.geopolitical_exposure = GeopoliticalExposure(headquartered_country="UA")
        assert "geopolitical_exposure" in extract(ctx).active_triggers

    def test_operational_country_in_zone_fires(self):
        from beacon.ingest.schema import GeopoliticalExposure

        ctx = self._base_ctx()
        ctx.geopolitical_exposure = GeopoliticalExposure(
            headquartered_country="JP",
            operational_countries=["TW"],
        )
        assert "geopolitical_exposure" in extract(ctx).active_triggers

    def test_supply_chain_origin_in_zone_fires(self):
        from beacon.ingest.schema import GeopoliticalExposure

        ctx = self._base_ctx()
        ctx.geopolitical_exposure = GeopoliticalExposure(
            headquartered_country="JP",
            supply_chain_origin_regions=["CN"],
        )
        assert "geopolitical_exposure" in extract(ctx).active_triggers

    def test_all_low_risk_countries_does_not_fire(self):
        from beacon.ingest.schema import GeopoliticalExposure

        ctx = self._base_ctx()
        ctx.geopolitical_exposure = GeopoliticalExposure(
            headquartered_country="JP",
            operational_countries=["US", "DE"],
            primary_customer_regions=["GB"],
            supply_chain_origin_regions=["KR"],
        )
        assert "geopolitical_exposure" not in extract(ctx).active_triggers


class TestRansomwareResilienceGapTrigger:
    """0.14.0 trigger 9 — fires when business_continuity is absent OR
    when any one of (backup_strategy_documented, backup_offsite_or_immutable,
    incident_response_plan_documented, recovery_test_cadence within 180
    days) is missing. Absent block = conservative gap=True. See
    docs/triggers.md §9."""

    def _base_ctx(self):
        from beacon.ingest.schema import BusinessContext, Organization

        return BusinessContext(organization=Organization(name="X", industry="other"))

    def test_absent_block_fires_conservatively(self):
        elements = extract(self._base_ctx())
        assert "ransomware_resilience_gap" in elements.active_triggers

    def test_fully_documented_posture_does_not_fire(self):
        from beacon.ingest.schema import BusinessContinuity

        ctx = self._base_ctx()
        ctx.business_continuity = BusinessContinuity(
            backup_strategy_documented=True,
            backup_offsite_or_immutable=True,
            incident_response_plan_documented=True,
            recovery_test_cadence_days=90,
        )
        assert "ransomware_resilience_gap" not in extract(ctx).active_triggers

    def test_missing_offsite_backup_fires(self):
        from beacon.ingest.schema import BusinessContinuity

        ctx = self._base_ctx()
        ctx.business_continuity = BusinessContinuity(
            backup_strategy_documented=True,
            backup_offsite_or_immutable=False,
            incident_response_plan_documented=True,
            recovery_test_cadence_days=90,
        )
        assert "ransomware_resilience_gap" in extract(ctx).active_triggers

    def test_stale_recovery_test_fires(self):
        from beacon.ingest.schema import BusinessContinuity

        ctx = self._base_ctx()
        ctx.business_continuity = BusinessContinuity(
            backup_strategy_documented=True,
            backup_offsite_or_immutable=True,
            incident_response_plan_documented=True,
            recovery_test_cadence_days=365,  # > 180 day threshold
        )
        assert "ransomware_resilience_gap" in extract(ctx).active_triggers

    def test_boundary_recovery_cadence_exactly_180_does_not_fire(self):
        from beacon.ingest.schema import BusinessContinuity

        ctx = self._base_ctx()
        ctx.business_continuity = BusinessContinuity(
            backup_strategy_documented=True,
            backup_offsite_or_immutable=True,
            incident_response_plan_documented=True,
            recovery_test_cadence_days=180,
        )
        assert "ransomware_resilience_gap" not in extract(ctx).active_triggers

    def test_missing_ir_plan_fires(self):
        from beacon.ingest.schema import BusinessContinuity

        ctx = self._base_ctx()
        ctx.business_continuity = BusinessContinuity(
            backup_strategy_documented=True,
            backup_offsite_or_immutable=True,
            incident_response_plan_documented=False,
            recovery_test_cadence_days=90,
        )
        assert "ransomware_resilience_gap" in extract(ctx).active_triggers


class TestIdentityCredentialExposureTrigger:
    """0.14.0 trigger 10 — fires when identity_management is absent OR
    MFA coverage <95% OR PIM/PAM absent OR helpdesk-auth undocumented.
    Absent block = conservative gap=True. See docs/triggers.md §10."""

    def _base_ctx(self):
        from beacon.ingest.schema import BusinessContext, Organization

        return BusinessContext(organization=Organization(name="X", industry="other"))

    def test_absent_block_fires_conservatively(self):
        elements = extract(self._base_ctx())
        assert "identity_credential_exposure" in elements.active_triggers

    def test_fully_mature_iam_does_not_fire(self):
        from beacon.ingest.schema import IdentityManagement

        ctx = self._base_ctx()
        ctx.identity_management = IdentityManagement(
            mfa_coverage_percent=100,
            pim_or_pam_deployed=True,
            helpdesk_authentication_documented=True,
        )
        assert "identity_credential_exposure" not in extract(ctx).active_triggers

    def test_low_mfa_coverage_fires(self):
        from beacon.ingest.schema import IdentityManagement

        ctx = self._base_ctx()
        ctx.identity_management = IdentityManagement(
            mfa_coverage_percent=80,
            pim_or_pam_deployed=True,
            helpdesk_authentication_documented=True,
        )
        assert "identity_credential_exposure" in extract(ctx).active_triggers

    def test_boundary_mfa_at_95_does_not_fire(self):
        from beacon.ingest.schema import IdentityManagement

        ctx = self._base_ctx()
        ctx.identity_management = IdentityManagement(
            mfa_coverage_percent=95,
            pim_or_pam_deployed=True,
            helpdesk_authentication_documented=True,
        )
        assert "identity_credential_exposure" not in extract(ctx).active_triggers

    def test_boundary_mfa_at_94_fires(self):
        from beacon.ingest.schema import IdentityManagement

        ctx = self._base_ctx()
        ctx.identity_management = IdentityManagement(
            mfa_coverage_percent=94,
            pim_or_pam_deployed=True,
            helpdesk_authentication_documented=True,
        )
        assert "identity_credential_exposure" in extract(ctx).active_triggers

    def test_missing_pim_pam_fires(self):
        from beacon.ingest.schema import IdentityManagement

        ctx = self._base_ctx()
        ctx.identity_management = IdentityManagement(
            mfa_coverage_percent=100,
            pim_or_pam_deployed=False,
            helpdesk_authentication_documented=True,
        )
        assert "identity_credential_exposure" in extract(ctx).active_triggers

    def test_undocumented_helpdesk_auth_fires(self):
        from beacon.ingest.schema import IdentityManagement

        ctx = self._base_ctx()
        ctx.identity_management = IdentityManagement(
            mfa_coverage_percent=100,
            pim_or_pam_deployed=True,
            helpdesk_authentication_documented=False,
        )
        assert "identity_credential_exposure" in extract(ctx).active_triggers


class TestLikelihoodCapWithTenTriggers:
    """0.14.0 regression — the +1-if-any-trigger / cap-5 likelihood boost
    must remain intact even when all ten triggers fire. Verifies the
    risk_scorer never returns likelihood > 5."""

    def test_likelihood_capped_at_5_with_many_triggers(self):
        from beacon.analysis.risk_scorer import _compute_likelihood
        from beacon.analysis.threat_mapper import ThreatProfile

        # 3 matched categories → base=4; trigger present → +1; cap at 5
        threat = ThreatProfile(
            threat_actor_tags=["t1", "t2", "t3"],
            notable_groups=[],
            priority_ttps=[],
            active_triggers=[f"trigger_{i}" for i in range(10)],
            matched_categories=["a", "b", "c"],
        )
        likelihood = _compute_likelihood(elements=None, threat=threat)
        assert likelihood == 5

    def test_likelihood_boost_is_single_not_per_trigger(self):
        from beacon.analysis.risk_scorer import _compute_likelihood
        from beacon.analysis.threat_mapper import ThreatProfile

        # 0 matched categories → base=1; any trigger → +1 (single, not per-trigger)
        one_trigger = ThreatProfile(
            threat_actor_tags=[],
            notable_groups=[],
            priority_ttps=[],
            active_triggers=["only_one"],
            matched_categories=[],
        )
        ten_triggers = ThreatProfile(
            threat_actor_tags=[],
            notable_groups=[],
            priority_ttps=[],
            active_triggers=[f"t_{i}" for i in range(10)],
            matched_categories=[],
        )
        assert _compute_likelihood(elements=None, threat=one_trigger) == 2
        assert _compute_likelihood(elements=None, threat=ten_triggers) == 2


class TestDedup:
    def test_completed_project_excluded(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        # Add a completed project with different vendors
        from beacon.ingest.schema import Project

        ctx.projects.append(
            Project(
                id="PROJ-999",
                name="Old System",
                status="completed",
                involved_vendors=["OldVendor"],
                cloud_providers=["AWS"],
                data_types=["hr"],
            )
        )
        elements = extract(ctx)
        assert "OldVendor" not in elements.active_vendors


class TestCriticalAssets:
    def setup_method(self):
        self.ctx = _load_ctx("sample_context_manufacturing.json")
        self.elements = extract(self.ctx)

    def test_critical_asset_ids_extracted(self):
        assert "CA-001" in self.elements.critical_asset_ids
        assert "CA-002" in self.elements.critical_asset_ids

    def test_critical_asset_details_populated(self):
        detail = next(d for d in self.elements.critical_asset_details if d.id == "CA-001")
        assert detail.name == "SAP S/4HANA Production"
        assert detail.type == "application"
        assert detail.network_zone == "corporate"
        assert detail.criticality == "critical"
        assert "financial" in detail.data_types

    def test_managing_vendor_added_to_active_vendors(self):
        # CA-001 is managed by Accenture — should appear in active_vendors
        assert "Accenture" in self.elements.active_vendors

    def test_ot_zone_asset_sets_ot_connectivity(self):
        # CA-002 has network_zone="ot" — should trigger has_ot_connectivity even
        # if supply_chain.ot_connectivity were False
        ctx = _load_ctx("sample_context_manufacturing.json")
        ctx.supply_chain.ot_connectivity = False
        elements = extract(ctx)
        assert elements.has_ot_connectivity is True  # detected from CA-002 zone

    def test_supply_chain_role_preserved(self):
        detail = next(d for d in self.elements.critical_asset_details if d.id == "CA-002")
        assert detail.supply_chain_role == "tier1_supplier_edi_connectivity"

    def test_critical_asset_ids_in_source_element_ids(self):
        assert "CA-001" in self.elements.source_element_ids
        assert "CA-002" in self.elements.source_element_ids

    def test_regulatory_context_extracted(self):
        assert "APPI" in self.elements.org_regulatory_context
        assert "ISO27001" in self.elements.org_regulatory_context


class TestCriticalAssetTagMapping:
    """Tests for asset_mapper handling of critical_asset_details."""

    def setup_method(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        self.elements = extract(ctx)

    def test_erp_tag_from_critical_asset_function(self):
        from beacon.analysis.asset_mapper import map_asset_tags

        # CA-001 function mentions "ERP" — should map to erp tag
        tags = map_asset_tags(self.elements)
        assert "erp" in tags

    def test_ot_tag_from_critical_asset_zone(self):
        from beacon.analysis.asset_mapper import map_asset_tags

        # CA-002 has network_zone="ot" — should always add ot tag
        tags = map_asset_tags(self.elements)
        assert "ot" in tags

    def test_financial_tag_from_critical_asset_data_types(self):
        from beacon.analysis.asset_mapper import map_asset_tags

        # CA-001 data_types includes "financial"
        tags = map_asset_tags(self.elements)
        assert "financial" in tags
