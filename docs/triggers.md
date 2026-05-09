# BEACON Business Triggers

Japanese translation: [`docs/triggers.ja.md`](triggers.ja.md)

This document is the canonical record of BEACON's seven business triggers,
their definitions, detection logic, and external citations. If a trigger is
added, removed, or reweighted, update this file in the same commit.

---

## What is a trigger

A **trigger** is a structural condition derived from `BusinessContext` that
indicates the organisation is in a state which materially elevates cyber
attack surface or threat exposure compared with steady-state operation. The
concept is anchored on **NIST SP 800-37 Rev 2** §F *Event-Driven Triggers /
Significant Changes to the Environment of Operation*:

> "Organizations define event-driven triggers (i.e., indicators or prompts
> that cause a predefined organizational reaction) for both ongoing
> authorization and reauthorization."

BEACON's seven triggers are a **business-level enumeration** of significant
changes that BEACON can detect from the BusinessContext schema. Each is
corroborated by either a long-standing standard (NIST/ISO/IEC/SEC/EU) or by
two or more independent past-12-month incident-response reports.

A trigger is **descriptive** (records that the org is in this state) and
**prescriptive** (contributes +1 to risk likelihood and escalates intelligence
level from `tactical` to `operational`). NIST SP 800-37 R2 does not
differentiate event-driven trigger weights; BEACON treats all seven
symmetrically.

---

## The seven triggers

### 1. `cloud_dependency`

**Definition:** the organisation has structural dependence on public cloud
infrastructure — whether actively migrating, operating workloads, or relying
on cloud-managed services.

**Detection** (`element_extractor._detect_triggers`):

```
projects[*].cloud_providers non-empty
  OR supply_chain.cloud_providers non-empty
  OR critical_assets[*].network_zone == "cloud"
```

**Citations**

- *NIST SP 800-37 Rev 2* — environment-of-operation change concept.
- *CISA Cloud Security Technical Reference Architecture v2* (2023) — "priority
  considerations… when migrating, moving, or expanding their cloud estates."
- *CrowdStrike Global Threat Report 2025* — cloud intrusions +26% YoY; valid
  account abuse 35% of cloud incidents (top vector).
- *Mandiant M-Trends 2026* — IAM misconfigurations and cross-environment
  lateral movement as recurring themes.
- *IBM Cost of a Data Breach Report 2025* — multi-environment data
  distribution as cost amplifier.

**Limitations:** does not distinguish between active migration, mature cloud
operation, and exit/repatriation phases. All are treated as elevated risk;
analysts may wish to adjust per-engagement.

---

### 2. `it_ot_convergence`

**Definition:** the organisation has IT/OT integration points (corporate IT
networks reachable to industrial control / operational technology systems).

**Detection:**

```
supply_chain.ot_connectivity == True
  OR any(critical_assets[*].network_zone == "ot")
```

**Citations**

- *NIST SP 800-82 Rev 3 — Guide to Operational Technology (OT) Security*
  (2023) §1.2 — "increasing pace of integration between OT networks and
  broader connected networks… new cybersecurity risks."
- *ENISA Threat Landscape 2025* — operational technology threats account for
  18.2% of all identified threat categories.
- *IEC 62443 — Industrial Communication Networks Security* — international
  standard for IT/OT zone segmentation requirements.

---

### 3. `third_party_dependency`

**Definition:** the organisation has critical reliance on outside vendors,
suppliers, or managed service providers.

**Detection:**

```
supply_chain.critical_vendors non-empty
  OR any(critical_assets[*].managing_vendor non-empty)
```

**Citations**

- *NIST SP 800-161 Rev 1 — Cybersecurity Supply Chain Risk Management
  Practices* (2024) — "supply chains are global, complex and dynamic, often
  involving multiple tiers of suppliers."
- *Verizon Data Breach Investigations Report 2025* — third-party involvement
  in 30% of breaches, doubled from 15% in the prior report.
- *IBM Cost of a Data Breach Report 2025* — third-party / supply-chain
  compromises ≈ 15% of breaches; took the longest to detect (≈ 9 months).
- *Executive Order 14028 — Improving the Nation's Cybersecurity* — formalised
  software supply chain as a federal cyber priority.

---

### 4. `external_facing_exposure`

**Definition:** the organisation operates critical assets reachable directly
from the internet, or holds crown jewels with high/critical exposure risk.

**Detection:**

```
any(critical_assets[*].network_zone in {"internet", "dmz"})
  OR any(crown_jewels[*].exposure_risk in {"high", "critical"})
```

**Citations**

- *Mandiant M-Trends 2026* — exploitation of internet-facing systems is the
  #1 initial-access vector for the sixth consecutive year (32% of cases
  where Mandiant could identify entry).
- *Verizon DBIR 2025* — vulnerability exploitation now 20% of breaches; edge
  device exploitation up eightfold; median time-to-mass-exploit for new
  edge-device CVEs measured in zero days.
- *CISA Known Exploited Vulnerabilities (KEV) Catalog* — federal mandate
  framework for prioritising remediation of internet-reachable bugs.

---

### 5. `regulated_disclosure_scope`

**Definition:** the organisation is subject to material cybersecurity
incident disclosure obligations imposed by securities, sectoral, or
data-protection regulators.

**Detection:**

```
organization.stock_listed == True
  OR any(disclosure-regulation keyword in organization.regulatory_context)
```

The keyword set is sourced from `schema/trigger_keywords.json` →
`disclosure_regulation_keywords`. Default contents: SEC / Form 10-K / 8-K /
Item 106 / NIS2 / HIPAA Breach Notification / PCI-DSS / 金融商品取引法 /
個人情報保護法 / 資金決済法 / APPI.

**Citations**

- *SEC Final Rule 33-11216 — Cybersecurity Risk Management, Strategy,
  Governance, and Incident Disclosure* (2023) — Item 106 mandates public
  companies disclose material cybersecurity processes; 8-K within 4 business
  days for material incidents.
- *EU NIS2 Directive (2022/2555) Article 23* — significant-incident
  notification obligations for essential and important entities.
- *HIPAA Breach Notification Rule (45 CFR §§164.400-414)* — covered entities
  and business associates must notify HHS, individuals, and (sometimes)
  media.

**Limitations:** keyword-based regulatory detection. Industries subject to
sectoral regulators not captured by the default keyword list (e.g.,
state-level NY DFS Part 500) require keyword extension.

---

### 6. `sectoral_high_risk`

**Definition:** the organisation operates in an industry empirically observed
to be disproportionately targeted across multiple recent threat reports.

**Detection:**

```
organization.industry in {finance, healthcare, energy, manufacturing,
                          government, defense, logistics, technology}
```

The constant `_HIGH_RISK_SECTORS` lives in
`src/beacon/analysis/element_extractor.py`. Membership is the empirical
intersection of:

- *ENISA Threat Landscape 2025* sectoral analysis (public administration 38%
  of incidents; manufacturing 59% cybercriminal).
- *Verizon DBIR 2025* industry breakdowns.
- *CrowdStrike Global Threat Report 2025* — technology, financial services,
  manufacturing, retail experiencing 200–300% YoY intrusion increases.
- *ENISA Sectoral Threat Landscapes* (Public Administration, Energy, Health,
  Transport, Telecom).

**Update cadence:** annually, when ENISA / Verizon / CrowdStrike publish
their next-year reports. If the empirical intersection changes, update the
constant and this document in the same commit.

---

### 7. `ai_adoption_exposure`

**Definition:** the organisation is adopting or operating AI/ML systems —
classical ML pipelines, generative AI, LLM agents, or retrieval-augmented
systems — without explicit AI governance evidence in the BusinessContext.

**Detection:**

```
any AI/ML keyword (en+ja) appears in
  strategic_objectives[*].{title,description,key_decisions}
  OR projects[*].{name,data_types}
```

The keyword set is sourced from `schema/trigger_keywords.json` →
`ai_adoption_keywords`. Bilingual (EN/JA) to match Japanese-authored input
documents.

**Citations**

- *IBM Cost of a Data Breach Report 2025* — shadow AI added $670K to average
  breach cost; 63% of breached organisations lacked AI governance policies;
  97% of AI-related breaches involved missing access controls.
- *CrowdStrike Global Threat Report 2025* — vishing operations grew 442%
  H1→H2 2024, AI-driven; AI-generated phishing at scale.
- *ENISA Threat Landscape 2025* — by early 2025, AI-supported phishing
  campaigns represented more than 80% of observed social engineering activity
  worldwide.

**Limitations:** the trigger flags AI presence, not absence of governance —
the score elevation is opportunistic. A future revision could AND the AI
signal with regulatory_context lacking AI-governance keywords.

---

## Weighting

All seven triggers contribute symmetrically to risk scoring:

| Effect | Mechanism |
|--------|-----------|
| Likelihood boost | `+1` if any trigger active, capped at 5. Implemented in `risk_scorer._compute_likelihood`. |
| Intelligence-level escalation | `tactical → operational` if any trigger active and composite < 12. Implemented in `risk_scorer._recommend_level`. |

**Rationale:** NIST SP 800-37 Rev 2 does not assign differential weights to
event-driven triggers — the framework treats them as a homogeneous set of
prompts for organisational re-evaluation. BEACON inherits that property.

The previous BEACON 0.x asymmetric subset
(`{ot_connectivity, m_and_a, ipo_or_listing}`) was an internal heuristic
without external citation; it was removed in 0.10.0.

---

## Update procedure

1. **Annually** (Q1) re-read the most recent ENISA Threat Landscape, Verizon
   DBIR, IBM Cost of a Data Breach, CrowdStrike GTR, and Mandiant M-Trends.
   If a trigger's primary citation no longer holds, or a new
   empirically-supported trigger emerges across ≥2 independent reports,
   propose a revision with citations.
2. **When the BusinessContext schema changes**, re-check that all triggers
   still have a structural detection path. If a referenced field is removed,
   the trigger must be either rewired or retired.
3. **All trigger changes require updating both this document and
   `docs/triggers.ja.md`** in the same commit, plus the relevant
   `tests/test_element_extractor.py` cases.

---

## See also

- `src/beacon/analysis/element_extractor.py:_detect_triggers` — detection logic
- `src/beacon/analysis/risk_scorer.py:_compute_likelihood` /
  `_recommend_level` — weighting
- `schema/trigger_keywords.json` — keyword sets for AI / regulation triggers
- `BEACON/high-level-design.md` §5.3 — risk-scoring narrative
