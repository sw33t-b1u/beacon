# BEACON Business Triggers

Japanese translation: [`docs/triggers.ja.md`](triggers.ja.md)

This document is the canonical record of BEACON's ten business triggers,
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

BEACON's ten triggers are a **business-level enumeration** of significant
changes that BEACON can detect from the BusinessContext schema. Each is
corroborated by either a long-standing standard (NIST/ISO/IEC/SEC/EU) or by
two or more independent past-12-month incident-response reports.

A trigger is **descriptive** (records that the org is in this state) and
**prescriptive** (contributes +1 to risk likelihood and escalates intelligence
level from `tactical` to `operational`). NIST SP 800-37 R2 does not
differentiate event-driven trigger weights; BEACON treats all ten
symmetrically.

---

## The ten triggers

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
- *Mandiant M-Trends 2026* — for cloud-related compromises in Mandiant's
  2025 investigations, voice phishing was the most common initial infection
  vector (23%), followed by third-party compromise.
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
- *Dragos 2026 OT Cybersecurity Year in Review (9th Annual)* — tracked
  119 ransomware groups impacting over 3,300 industrial organisations in
  2025 (compared with 1,693 attacks in 2024); three new OT-specific threat
  groups (AZURITE, PYROXENE, SYLVANITE) named in 2025.
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
- *IBM Cost of a Data Breach Report 2025* — third-party vendor and supply
  chain compromise had a USD 4.91 million average breach cost and took the
  longest to identify and contain at 267 days (≈ 9 months).
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
- *CrowdStrike Global Threat Report 2025* — financial services, media,
  manufacturing, and industrials and engineering sectors experiencing
  200–300% YoY increases in observed China-nexus intrusions; government,
  technology, and telecommunications (the top-3 China-nexus targets) saw
  ≈ 50% YoY increases.
- *ENISA Threat Landscape: Finance Sector (Jan 2023 – Jun 2024)* — finance
  was the third-most-targeted EU sector (after public administration and
  transport); 12% of NIS-significant incidents reported in 2023 affected
  the European finance sector.
- *ENISA Sectoral Threat Landscapes* (Public Administration, Energy, Health,
  Transport, Telecom — Public Administration and Finance are the two
  sectoral reports currently in `ref/`; Energy / Health / Transport / Telecom
  remain to be added as their volumes are reissued).

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
- *International AI Safety Report 2026* (chair Y. Bengio) — more evidence
  has emerged of AI systems being used in real-world cyberattacks; in 2025,
  12 companies published or updated Frontier AI Safety Frameworks but most
  risk-management commitments remain voluntary.
- *CrowdStrike Global Threat Report 2025* — vishing operations grew 442%
  H1→H2 2024, AI-driven; AI-generated phishing at scale.
- *ENISA Threat Landscape 2025* — by early 2025, AI-supported phishing
  campaigns represented more than 80% of observed social engineering activity
  worldwide.
- *Trend Micro Security Predictions for 2026 — The AI-fication of
  Cyberthreats* — ransomware predicted to evolve into AI-driven, fully
  automated operations; cloud-native phishing campaigns blending email,
  SMS, voice, and AI-driven tactics.

**Limitations:** the trigger flags AI presence, not absence of governance —
the score elevation is opportunistic. A future revision could AND the AI
signal with regulatory_context lacking AI-governance keywords.

---

### 8. `geopolitical_exposure`

**Definition:** the organisation has headquarters, operational presence,
customer base, or supply-chain origin in a high-risk geopolitical zone —
elevating exposure to state-sponsored, nexus, or conflict-spillover
cyber activity.

**Detection:**

```
any(value in HIGH_RISK_GEOPOLITICAL_ZONES for value in (
    geopolitical_exposure.headquartered_country,
    *geopolitical_exposure.operational_countries,
    *geopolitical_exposure.primary_customer_regions,
    *geopolitical_exposure.supply_chain_origin_regions,
))
```

`HIGH_RISK_GEOPOLITICAL_ZONES` is a frozenset of ISO 3166-1 alpha-2 codes:
`{UA, RU, IL, PS, TW, CN, IR, KP, SY, YE}`. The set is sourced from the
intersection of active-conflict zones and state-sponsored cyber-activity
hubs in the 2025-2026 reporting window. Extension requires explicit
re-review against the ref/ corpus — it is a judgement-laden constant.

Absent block (`geopolitical_exposure is None`) → trigger does **not** fire.
Unlike the two resilience triggers below, lack-of-information here is not
treated as elevated risk (false positives based on missing region data
are not actionable).

**Citations**

- *CrowdStrike Global Threat Report 2025* — "China-nexus activity surged
  150% overall, with some targeted industries suffering 200% to 300% more
  attacks than the previous year" (`ref/CrowdStrikeGlobalThreatReport2025.md`
  line 63-65). Same report, line 922-923: "financial services, media,
  manufacturing, and industrials and engineering sectors, which all
  experienced 200-300% increases in observed China-nexus intrusions".
- *Cloudflare 2026 Threat Report* — "geopolitical leverage"
  (`ref/Cloudflare-2026-threat-report.md` line 77); same report,
  "highly sophisticated state-sponsored pre-positioning" (line 1591).
- *IOCTA 2026 (Europol)* — Russia-based / Russian-speaking cybercrime
  ecosystems are documented across the report; Initial Access Brokers
  ecosystem chapter at `ref/IOCTA-2026.md` line 921.
- *INTERPOL Asia and South Pacific Cyber Threat Assessment 2025/2026* —
  regional CTI dedicated to ASP geopolitical exposure
  (`ref/CYBER_ASP Cyber Threat Assessment Report_2025_2026_v4.md`).
- *Mandiant M-Trends 2026* — "Regional Breakouts" chapter (Americas /
  EMEA / JAPAC) covering regional differentials.

**Limitations:**

- The high-risk zone set is a judgement call. Edge cases (e.g. EU under
  NIS2 wartime advisory, US critical infrastructure) are not in the set.
- HQ-in-zone vs customer-in-zone vs supply-chain-in-zone have different
  risk semantics (active vs passive exposure) but are currently treated
  symmetrically. Differential weighting is a future-revision candidate.
- Set extension or revision should reference the same ref/ corpus to
  avoid drift from empirical evidence into political judgement.

---

### 9. `ransomware_resilience_gap`

**Definition:** the organisation cannot demonstrate ransomware-recovery
readiness — `backup_strategy` / `incident_response_plan` /
`recovery_test_cadence` are missing, undocumented, or stale.
Ransomware is empirically near-universal in the 2025-2026 reporting
window; orgs without resilience evidence face an order-of-magnitude
larger business-continuity impact when (not if) they are hit.

**Detection:**

```
business_continuity is None
  OR NOT (backup_strategy_documented
          AND backup_offsite_or_immutable
          AND incident_response_plan_documented
          AND 0 < recovery_test_cadence_days <= 180)
```

Absent block (`business_continuity is None`) → trigger **fires**
(conservative: undocumented posture is treated as elevated risk, per the
M-Trends 2026 "Ransomware is Now a Resilience Problem" framing). The
180-day recovery-test cadence threshold approximates the NIST SP 800-34 /
ISO 22301 cadence for plan-testing currency.

**Citations**

- *ENISA Threat Landscape 2025* — "ransomware accounting for 83.9% and
  data breaches 16.1% of cybercrime incidents"
  (`ref/ENISA_Threat_Landscape_2025_v1.2.md` line 730). Same report, EU
  cut: "ransomware (81.1%) and data breaches (15.2%)" (line 931).
- *Mandiant M-Trends 2026* — "In 44% of Mandiant's 2025 investigations,
  the intrusion" (`ref/m-trends-2026-en.md` line 1270); chapter
  "Ransomware is Now a Resilience Problem" (TOC entry line 25), which
  is the direct naming source for this trigger.
- *IBM Cost of a Data Breach Report 2025* — ransomware "hit USD 5.08
  million in this year's report"
  (`ref/20250822_Cost-of-a-Data-Breach-Report-2025.md` line 51).
- *Dragos 2026 OT Cybersecurity Year in Review* — "Dragos tracked 119
  ransomware groups targeting industrial organizations"
  (`ref/Dragos-2026-OT-Cybersecurity-Report-A-Year-in-Review.md` line
  1641); same report documents the ~2x year-over-year increase from
  1,693 attacks in 2024 to over 3,300 industrial victims in 2025.
- *CrowdStrike Global Threat Report 2025* — eCrime / ransomware-as-a-service
  ecosystem documented throughout (`ref/CrowdStrikeGlobalThreatReport2025.md`).

**Limitations:**

- "documented" is self-reported and gameable. Verifiable signals (backup
  SaaS vendor, ISO 22301 certification) would harden the trigger; both
  are future-revision candidates.
- The 180-day cadence threshold is a rule-of-thumb; ISO 22301 / NIST
  SP 800-34 do not prescribe a single number. The 180-day choice
  approximates the median of those frameworks' guidance.
- Absent block treated as gap = elevated false-positive rate for orgs
  that do have a plan but have not populated the optional schema block.
  A future `unknown` enum value could distinguish "no info" from
  "documented gap".

---

### 10. `identity_credential_exposure`

**Definition:** the organisation has low identity / credential management
maturity — MFA coverage gap, no PIM/PAM, or undocumented helpdesk-auth
procedure — elevating exposure to access-broker, valid-account-abuse,
vishing, and BEC vectors.

**Detection:**

```
identity_management is None
  OR mfa_coverage_percent < 95
  OR NOT pim_or_pam_deployed
  OR NOT helpdesk_authentication_documented
```

Absent block (`identity_management is None`) → trigger **fires**
(conservative: undocumented IAM posture is the empirical baseline that
makes credential abuse, vishing, and IAB-mediated initial access
profitable). The 95% MFA coverage threshold corresponds to the
"near-universal" coverage level called out across CISA Shields Up
guidance, NIST SP 800-63B, and CIS Controls v8 IG2.

**Citations**

- *CrowdStrike Global Threat Report 2025* — "Meanwhile, valid account
  abuse was responsible for 35%" of cloud-related incidents
  (`ref/CrowdStrikeGlobalThreatReport2025.md` line 284); vishing growth
  "up 442% between the first and second half of 2024" (line 58); access
  broker advertisements "increased 50% year-over-year".
- *Mandiant M-Trends 2026* — "cloud-related compromises was voice
  phishing, at 23%, followed by third-party compromise"
  (`ref/m-trends-2026-en.md` line 1609).
- *IOCTA 2026 (Europol)* — Initial Access Brokers ecosystem chapter
  (`ref/IOCTA-2026.md` line 921); Scattered Spider / ShinyHunters /
  LAPSUS$ documented as acting as IABs around line 1062.
- *APWG Q4 2025 Trends Report* — Fortra "tracks the identity theft
  technique known as 'business e-mail compromise'"
  (`ref/apwg_trends_report_q4_2025.md` line 594); phishing and
  impersonation "accounted for 86 percent of all confirmed threats"
  (line 311).

**Limitations:**

- The 95% MFA coverage threshold is a rule-of-thumb; no single
  authoritative source prescribes a numeric line. Orgs at 90-94% are
  borderline cases analysts may downgrade per engagement.
- Helpdesk-authentication hardening is a recent best practice (UNC3944
  vishing mitigation); standardisation is still in flight, so the
  "documented" boolean is coarse.
- BEC functions partly as an impact magnifier rather than purely a
  trigger source. A future split between cause-side and impact-side
  signals would refine the model.
- Absent block treated as gap = same false-positive risk as the
  ransomware trigger; the `unknown` enum extension would also apply
  here.

---

## Weighting

All ten triggers contribute symmetrically to risk scoring:

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
   DBIR, IBM Cost of a Data Breach, CrowdStrike GTR, Mandiant M-Trends,
   Cloudflare Threat Report, IOCTA, and APWG. If a trigger's primary
   citation no longer holds, or a new empirically-supported trigger emerges
   across ≥2 independent reports, propose a revision with citations.
2. **When the BusinessContext schema changes**, re-check that all ten
   triggers still have a structural detection path. If a referenced field
   is removed, the trigger must be either rewired or retired.
3. **All trigger changes require updating both this document and
   `docs/triggers.ja.md`** in the same commit, plus the relevant
   `tests/test_element_extractor.py` cases.
4. **`HIGH_RISK_GEOPOLITICAL_ZONES` revisions** must cite specific
   ref/ corpus evidence (e.g. CrowdStrike GTR / Cloudflare nation-state
   chapter / IOCTA regional ecosystem) for any country added or removed.
   The set is empirically grounded, not a normative judgement.

---

## See also

- `src/beacon/analysis/element_extractor.py:_detect_triggers` — detection logic
- `src/beacon/analysis/risk_scorer.py:_compute_likelihood` /
  `_recommend_level` — weighting
- `schema/trigger_keywords.json` — keyword sets for AI / regulation triggers
- `BEACON/high-level-design.md` §5.3 — risk-scoring narrative
