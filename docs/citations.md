# External Citations and License Inventory

This document lists every external data source used by BEACON, its license
terms, and exactly how BEACON uses it. Maintained as required by the
Initiative F decision record (2026-05-23).

---

## MITRE ATT&CK Enterprise

| Attribute | Detail |
|---|---|
| Version | 19.1 (bundled 2026-05-23) |
| License | MITRE ATT&CK Terms of Use |
| Canonical URL | https://attack.mitre.org/ |
| Bundle URL | https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json |

**How BEACON uses it:**
`scripts/derive_source_groups.py` reads the STIX 2.1 bundle at derivation
time, extracts `intrusion-set` external references, and produces
`schema/source_attack_groups.derived.json` — a deterministic mapping of
`source_name` strings to ATT&CK Group IDs. This derived JSON is the only
ATT&CK-derived artifact committed to the BEACON repo. The 53 MB bundle
is never copied.

`schema/content_ja.json` `sources[].evidence_attack_groups` fields are
populated from the derived JSON via `schema/source_aliases.json`; they
carry ATT&CK Group IDs as references, not ATT&CK text.

**Required attribution (MITRE ATT&CK Terms of Use):**
> "The MITRE Corporation (MITRE) hereby grants you a non-exclusive,
> royalty-free license to use ATT&CK® for research, development, and
> commercial purposes. Any copy you make for such purposes is authorized
> provided that you reproduce MITRE's copyright designation and this
> license in any such copy."
>
> © 2024 The MITRE Corporation. ATT&CK® is a registered trademark of
> The MITRE Corporation.

---

## Intel 471 CU-GIR Framework

| Attribute | Detail |
|---|---|
| Version | Current (GitHub distribution) |
| License | Intel 471 CU-GIR Framework License (custom) |
| Canonical URL | https://github.com/intel471/CU-GIR |
| STIX JSON | `STIX/Current/intel471_cu-gir.json` in the repository above |

**License summary (Intel 471 CU-GIR Framework License):**
The license grants a royalty-free, perpetual, worldwide license to
reproduce, prepare derivative works, publicly display, and distribute
the Framework, subject to:
- (a) preserving all proprietary notices and copyright statements, and
- (b) not using the Framework to develop competing CTI products or
  services (BEACON is an open-source PIR-definition tool, not a CTI
  feed vendor, and does not compete with Intel 471's TITAN platform or
  underground monitoring services).

**How BEACON uses it:**
GIR decimal identifiers (e.g. `6.1.3.1`) and category names are used
in `schema/content_ja.json` `intelligence_requirements[].gir_id` entries
as classification references. Descriptions and EEI text in BEACON are
written independently by BEACON authors and do not reproduce CU-GIR text.

**Required attribution:**
> CU-GIR Framework by Intel 471, Inc.
> Licensed under the Intel 471 CU-GIR Framework License.
> Source: https://github.com/intel471/CU-GIR

---

## Verizon Data Breach Investigations Report (DBIR)

| Attribute | Detail |
|---|---|
| Edition used | 2025 |
| License | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA 4.0) |
| Canonical URL | https://www.verizon.com/business/resources/reports/dbir/ |

**How BEACON uses it:**
Statistical citations in `schema/content_ja.json` `trigger_actions` fields
(e.g. "サードパーティ侵害事例 (Verizon DBIR 2025: 30%)"). No verbatim
text is reproduced; only statistics are cited with attribution.

**Required attribution:** "Verizon 2025 Data Breach Investigations Report."

---

## IBM Cost of a Data Breach Report

| Attribute | Detail |
|---|---|
| Edition used | 2025 |
| License | IBM proprietary (non-exclusive use for citation purposes) |
| Canonical URL | https://www.ibm.com/reports/data-breach |

**How BEACON uses it:**
Statistical citation in `schema/content_ja.json` `trigger_actions`
(`ai_adoption_exposure`: "IBM CoDB 2025"). No verbatim text reproduced.

**Required attribution:** "IBM Cost of a Data Breach Report 2025."

---

## NIST Special Publications

| Attribute | Detail |
|---|---|
| Publisher | National Institute of Standards and Technology (US Department of Commerce) |
| License | US government work — public domain under 17 USC §105 |
| Citation policy | Verbatim quotation freely permitted; attribution by SP number is the standard form |

**How BEACON uses each:**

| SP | Used by | Purpose |
|---|---|---|
| SP 800-30r1 | `src/beacon/analysis/actor_triage.py` (docstring) | Adversary capability + intent assessment tables D-3 / D-4 |
| SP 800-37r2 | `src/beacon/analysis/risk_scorer.py` (comment); `docs/data-model.ja.md` | Event-driven trigger framework for tactical → operational level promotion |
| SP 800-53 | `schema/context_template.ja.md` | AC-2 / AC-3 / IA-2 / IA-4 access control framework |
| SP 800-82r3 | `src/beacon/analysis/element_extractor.py` (comment) | ICS/OT security guidance referenced for IT/OT convergence trigger |
| SP 800-161r1 | `src/beacon/analysis/element_extractor.py` (comment) | Supply chain risk management reference |
| SP 800-207 | `schema/context_template.ja.md` | Zero Trust architecture reference |

**Required attribution:** Standard NIST citation form (e.g., "NIST SP 800-61r3
§2.1, April 2025"). No copyright notice required.

---

## MITRE Cyber Prep / Cyber Threat Level Assessment

| Attribute | Detail |
|---|---|
| Authors | Sergio Bodeau, Jenn Fabius-Greene, Rich Graubart |
| Publisher | The MITRE Corporation |
| Title | *"How Do You Assess Your Organization's Cyber Threat Level?"* |
| License | © The MITRE Corporation. All rights reserved (academic fair use only — short quotes with attribution) |

**How BEACON uses it:**
Methodology foundation for the `Likelihood = Intent × Capability × Opportunity`
formula in `src/beacon/analysis/actor_triage.py`. Cyber Prep defines threat in
terms of *capability, intent, targeting*; BEACON's `Opportunity` factor maps
to Cyber Prep's `Targeting`. Short verbatim quotes of the three-factor
definitions are included in the actor_triage.py docstring as academic
citations under fair use; no bulk reproduction of paper text.

This same citation also anchors Initiative G's `ir_observed` factor:
a confirmed past attack against the organisation is the strongest evidence
of intent, so IR observation is multiplied into the Intent component.

**Required attribution:** "Bodeau, Fabius-Greene, Graubart. 'How Do You Assess
Your Organization's Cyber Threat Level?' The MITRE Corporation." Inline academic
citation acceptable; do NOT reproduce paper text in bulk.

---

## SANS Internet Storm Center / Reading Room

| Attribute | Detail |
|---|---|
| Publisher | SANS Institute |
| License | Citation permitted under SANS fair-use guidelines |

**How BEACON uses it:**
Source for the SANS I-O-C (Intent / Opportunity / Capability) actor-triage triad
cited in `src/beacon/analysis/actor_triage.py` docstring. Short verbatim quote
with attribution.

---

## Other Annual Threat Reports

The following reports are referenced by BEACON for statistical citations.
Per 2026-05-23 policy, verbatim text from these proprietary reports
is NOT reproduced in committed BEACON artifacts; only short statistical
citations with explicit attribution (`source_name (year): statistic`) are used,
and longer paraphrases are preferred over verbatim.

| Report | Publisher | Approx. License |
|---|---|---|
| CrowdStrike Global Threat Report 2025 | CrowdStrike | Proprietary (citation permitted) |
| Mandiant M-Trends 2026 | Google / Mandiant | Proprietary (citation permitted) |
| ENISA Threat Landscape 2025 | ENISA | CC BY 4.0 |
| ENISA Public Administration Threat Landscape 2024 | ENISA | CC BY 4.0 |
| ENISA Finance Threat Landscape 2024 | ENISA | CC BY 4.0 |
| Dragos OT Cybersecurity Report 2026 | Dragos | Proprietary (citation permitted) |
| Cloudflare 2026 Threat Report | Cloudflare | Proprietary (citation permitted) |
| APWG eCrime Trends Q4 2025 | APWG | Proprietary |
| IOCTA 2026 | Europol | Proprietary (typically open with attribution) |
| TrendMicro 2026 Predictions | Trend Micro | Proprietary (citation permitted) |
| CYBER ASP Cyber Threat Assessment 2025/26 | CYBER ASP | See report |
| AI Safety Report 2026 | International AI Safety Initiative | Likely open with attribution |

---

## Maintenance

When a new external reference is added to any committed BEACON artifact,
add a row to this document before merging. If the license requires
attribution text to appear in distributed output, add it to
`src/beacon/generator/report_builder.py` footer generation.
