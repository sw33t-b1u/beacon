"""Tests for src/beacon/analysis/source_matcher.py."""

from __future__ import annotations

from pathlib import Path

from beacon.analysis.source_matcher import load_sources, select_sources

SCHEMA_DIR = Path(__file__).parent.parent / "schema"
CONTENT_JA_PATH = SCHEMA_DIR / "content_ja.json"

# Inline minimal source fixtures so tests are independent of file content.
_SRC_JPCERT = {
    "name": "JPCERT/CC Blog",
    "tier": "strategic",
    "region": ["JP"],
    "industry_focus": ["cross-sector"],
    "feed_url_hint": "https://blogs.jpcert.or.jp/en/atom.xml",
    "tlp": "TLP:CLEAR",
    "requires_membership": False,
    "evidence_attack_groups": ["G0032", "G1049", "G1054"],
    "evidence_derivation": "auto:scripts/derive_source_groups.py",
}
_SRC_IPA = {
    "name": "IPA Security Alerts",
    "tier": "strategic",
    "region": ["JP"],
    "industry_focus": ["cross-sector"],
    "feed_url_hint": "https://www.ipa.go.jp/security/alert-rss.rdf",
    "tlp": "TLP:CLEAR",
    "requires_membership": False,
    "evidence_attack_groups": [],
    "evidence_derivation": "industry_consensus",
}
_SRC_FS_ISAC = {
    "name": "FS-ISAC",
    "tier": "operational",
    "region": ["GLOBAL"],
    "industry_focus": ["finance"],
    "feed_url_hint": None,
    "tlp": "TLP:AMBER",
    "requires_membership": True,
    "evidence_attack_groups": [],
    "evidence_derivation": "industry_consensus",
}
_SRC_KINYU_ISAC = {
    "name": "金融ISAC",
    "tier": "operational",
    "region": ["JP"],
    "industry_focus": ["finance"],
    "feed_url_hint": None,
    "tlp": "TLP:AMBER",
    "requires_membership": True,
    "evidence_attack_groups": [],
    "evidence_derivation": "industry_consensus",
}
_SRC_MANDIANT = {
    "name": "Mandiant",
    "tier": "operational",
    "region": ["GLOBAL"],
    "industry_focus": ["cross-sector"],
    "feed_url_hint": None,
    "tlp": "TLP:CLEAR",
    "requires_membership": False,
    "evidence_attack_groups": ["G0045", "G0096", "G0032"],
    "evidence_derivation": "auto:scripts/derive_source_groups.py",
}
_SRC_DRAGOS = {
    "name": "Dragos OT",
    "tier": "tactical",
    "region": ["GLOBAL"],
    "industry_focus": ["OT"],
    "feed_url_hint": None,
    "tlp": "TLP:CLEAR",
    "requires_membership": False,
    "evidence_attack_groups": ["G0034", "G0035"],
    "evidence_derivation": "auto:scripts/derive_source_groups.py",
}
_SRC_CERT_UA = {
    "name": "CERT-UA",
    "tier": "strategic",
    "region": ["UA"],
    "industry_focus": ["cross-sector"],
    "feed_url_hint": None,
    "tlp": "TLP:CLEAR",
    "requires_membership": False,
    "evidence_attack_groups": ["G0007"],
    "evidence_derivation": "auto:scripts/derive_source_groups.py",
}
_SRC_JVN = {
    "name": "JVN",
    "tier": "operational",
    "region": ["JP"],
    "industry_focus": ["cross-sector"],
    "feed_url_hint": "https://jvn.jp/en/rss/",
    "tlp": "TLP:CLEAR",
    "requires_membership": False,
    "evidence_attack_groups": [],
    "evidence_derivation": "industry_consensus",
}

_ALL_FIXTURES = [
    _SRC_JPCERT,
    _SRC_IPA,
    _SRC_FS_ISAC,
    _SRC_KINYU_ISAC,
    _SRC_MANDIANT,
    _SRC_DRAGOS,
    _SRC_CERT_UA,
    _SRC_JVN,
]

# China-nexus ATT&CK groups: APT10, APT41, Mustang Panda, MirrorFace
_CHINA_NEXUS = ["G0045", "G0096", "G0129", "G1054"]


class TestSelectSourcesChinaAPTFinanceJapan:
    """Finance × Japan × Chinese-APT PIR — Phase 1.7 acceptance fixture."""

    def _run(self, tiers: list[str]) -> list[str]:
        results = select_sources(
            intelligence_levels=tiers,
            org_region="JP",
            org_industry="finance",
            attack_groups=_CHINA_NEXUS,
            sources=_ALL_FIXTURES,
        )
        return [s["name"] for s in results]

    def test_jpcert_in_strategic(self):
        names = self._run(["strategic"])
        assert "JPCERT/CC Blog" in names

    def test_ipa_in_strategic(self):
        # IPA is industry_consensus — matches without group intersection
        names = self._run(["strategic"])
        assert "IPA Security Alerts" in names

    def test_jvn_in_operational(self):
        names = self._run(["operational"])
        assert "JVN" in names

    def test_fs_isac_in_operational(self):
        names = self._run(["operational"])
        assert "FS-ISAC" in names

    def test_kinyu_isac_in_operational(self):
        names = self._run(["operational"])
        assert "金融ISAC" in names

    def test_mandiant_in_operational(self):
        # Mandiant has G0045/G0096 which intersect with _CHINA_NEXUS
        names = self._run(["operational"])
        assert "Mandiant" in names

    def test_dragos_excluded_ot_industry(self):
        # Dragos is OT industry only — must not appear for finance org
        names = self._run(["strategic", "operational", "tactical"])
        assert "Dragos OT" not in names

    def test_cert_ua_excluded_wrong_region(self):
        # CERT-UA covers only UA, no GLOBAL — must not appear for JP org
        names = self._run(["strategic"])
        assert "CERT-UA" not in names


class TestSelectSourcesTierFilter:
    """Tier criterion must be enforced strictly."""

    def test_strategic_only(self):
        results = select_sources(
            intelligence_levels=["strategic"],
            org_region="JP",
            org_industry="finance",
            attack_groups=[],
            sources=_ALL_FIXTURES,
        )
        for src in results:
            assert src["tier"] == "strategic"

    def test_operational_only(self):
        results = select_sources(
            intelligence_levels=["operational"],
            org_region="JP",
            org_industry="finance",
            attack_groups=[],
            sources=_ALL_FIXTURES,
        )
        for src in results:
            assert src["tier"] == "operational"

    def test_multi_tier(self):
        strategic = select_sources(
            intelligence_levels=["strategic"],
            org_region="GLOBAL",
            org_industry="cross-sector",
            attack_groups=[],
            sources=_ALL_FIXTURES,
        )
        operational = select_sources(
            intelligence_levels=["operational"],
            org_region="GLOBAL",
            org_industry="cross-sector",
            attack_groups=[],
            sources=_ALL_FIXTURES,
        )
        combined = select_sources(
            intelligence_levels=["strategic", "operational"],
            org_region="GLOBAL",
            org_industry="cross-sector",
            attack_groups=[],
            sources=_ALL_FIXTURES,
        )
        assert len(combined) == len(strategic) + len(operational)


class TestSelectSourcesRegionFilter:
    """Region criterion: JP org sees JP + GLOBAL, not UA-only."""

    def test_jp_sees_global_source(self):
        results = select_sources(
            intelligence_levels=["operational"],
            org_region="JP",
            org_industry="cross-sector",
            attack_groups=[],
            sources=[_SRC_MANDIANT],
        )
        assert len(results) == 1

    def test_jp_excludes_ua_source(self):
        results = select_sources(
            intelligence_levels=["strategic"],
            org_region="JP",
            org_industry="cross-sector",
            attack_groups=[],
            sources=[_SRC_CERT_UA],
        )
        assert results == []

    def test_global_org_sees_ua_source(self):
        results = select_sources(
            intelligence_levels=["strategic"],
            org_region="UA",
            org_industry="cross-sector",
            attack_groups=[],
            sources=[_SRC_CERT_UA],
        )
        assert len(results) == 1


class TestSelectSourcesIndustryFilter:
    """Industry criterion: finance org gets finance + cross-sector, not OT-only."""

    def test_finance_org_gets_cross_sector(self):
        results = select_sources(
            intelligence_levels=["strategic"],
            org_region="JP",
            org_industry="finance",
            attack_groups=[],
            sources=[_SRC_JPCERT],
        )
        assert len(results) == 1

    def test_finance_org_gets_finance(self):
        results = select_sources(
            intelligence_levels=["operational"],
            org_region="JP",
            org_industry="finance",
            attack_groups=[],
            sources=[_SRC_KINYU_ISAC],
        )
        assert len(results) == 1

    def test_finance_org_excludes_ot_source(self):
        results = select_sources(
            intelligence_levels=["tactical"],
            org_region="GLOBAL",
            org_industry="finance",
            attack_groups=[],
            sources=[_SRC_DRAGOS],
        )
        assert results == []

    def test_ot_org_gets_ot_source(self):
        results = select_sources(
            intelligence_levels=["tactical"],
            org_region="JP",
            org_industry="OT",
            attack_groups=["G0034"],
            sources=[_SRC_DRAGOS],
        )
        assert len(results) == 1


class TestSelectSourcesGroupFilter:
    """Group intersection and bypass behaviour."""

    def test_group_intersection_match(self):
        # Mandiant has G0096 — matches a Chinese-APT PIR
        results = select_sources(
            intelligence_levels=["operational"],
            org_region="GLOBAL",
            org_industry="cross-sector",
            attack_groups=["G0096"],
            sources=[_SRC_MANDIANT],
        )
        assert len(results) == 1

    def test_group_intersection_no_match(self):
        # Mandiant has G0045/G0096/G0032 — none intersect with DPRK-only G0094
        results = select_sources(
            intelligence_levels=["operational"],
            org_region="GLOBAL",
            org_industry="cross-sector",
            attack_groups=["G0094"],
            sources=[_SRC_MANDIANT],
        )
        assert results == []

    def test_industry_consensus_bypasses_group_filter(self):
        # IPA has evidence_derivation=industry_consensus — matches even with non-empty attack_groups
        results = select_sources(
            intelligence_levels=["strategic"],
            org_region="JP",
            org_industry="cross-sector",
            attack_groups=["G9999"],  # group not in IPA evidence
            sources=[_SRC_IPA],
        )
        assert len(results) == 1

    def test_empty_attack_groups_matches_all(self):
        # Empty attack_groups disables group filter — all tier/region/industry matches included
        results = select_sources(
            intelligence_levels=["strategic"],
            org_region="JP",
            org_industry="cross-sector",
            attack_groups=[],
            sources=[_SRC_JPCERT, _SRC_IPA],
        )
        assert len(results) == 2


class TestLoadSourcesFromFile:
    """load_sources() reads the live content_ja.json."""

    def test_returns_list(self):
        sources = load_sources(CONTENT_JA_PATH)
        assert isinstance(sources, list)

    def test_all_entries_have_required_keys(self):
        required = {
            "name",
            "tier",
            "region",
            "industry_focus",
            "tlp",
            "requires_membership",
            "evidence_attack_groups",
            "evidence_derivation",
        }
        for src in load_sources(CONTENT_JA_PATH):
            assert required <= src.keys(), f"Missing keys in {src.get('name')}"

    def test_jpcert_present_in_live_file(self):
        names = [s["name"] for s in load_sources(CONTENT_JA_PATH)]
        assert any("JPCERT" in n for n in names)

    def test_live_file_china_apt_fixture(self):
        # Phase 1.7 acceptance: finance/JP × Chinese-APT query returns JPCERT/CC
        sources = load_sources(CONTENT_JA_PATH)
        results = select_sources(
            intelligence_levels=["strategic"],
            org_region="JP",
            org_industry="finance",
            attack_groups=_CHINA_NEXUS,
            sources=sources,
        )
        names = [s["name"] for s in results]
        assert any("JPCERT" in n for n in names), (
            "JPCERT/CC must appear for JP finance + Chinese-APT"
        )

    def test_live_file_ot_source_excluded_for_finance(self):
        sources = load_sources(CONTENT_JA_PATH)
        results = select_sources(
            intelligence_levels=["strategic", "operational", "tactical"],
            org_region="JP",
            org_industry="finance",
            attack_groups=[],
            sources=sources,
        )
        for src in results:
            assert "OT" not in src["industry_focus"] or "cross-sector" in src["industry_focus"], (
                f"{src['name']} is OT-only but appeared for finance org"
            )
