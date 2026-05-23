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
| Local snapshot | `ref/enterprise-attack-19.1.json` (53 MB) — project-root `ref/` only, never copied into BEACON repo |

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
| Local snapshot | `ref/cu-gir.json` — project-root `ref/` only, never copied into BEACON repo |

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

**NOT used:** The CU-GIRH PDF handbook (`ref/CU-GIRH_v7.{md,pdf}`) is
licensed under CC-BY-NC-ND 4.0 (NoDerivatives + NonCommercial) and is
strictly more restrictive. It serves as background reading for human
reviewers only. No CU-GIRH handbook text is reproduced in any committed
BEACON artifact.

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
| Local snapshot | `ref/2025-dbir-data-breach-investigations-report.{md,pdf}` — project-root only |

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
| Local snapshot | `ref/20250822_Cost-of-a-Data-Breach-Report-2025.{md,pdf}` — project-root only |

**How BEACON uses it:**
Statistical citation in `schema/content_ja.json` `trigger_actions`
(`ai_adoption_exposure`: "IBM CoDB 2025"). No verbatim text reproduced.

**Required attribution:** "IBM Cost of a Data Breach Report 2025."

---

## Other Annual Threat Reports

The following reports are stored in `ref/` as background reading for BEACON
maintainers. No content from these reports is reproduced in committed BEACON
artifacts; they inform BEACON's threat taxonomy and trigger keyword design.

| Report | Publisher | Approx. License |
|---|---|---|
| CrowdStrike Global Threat Report 2025 | CrowdStrike | Proprietary (citation permitted) |
| Mandiant M-Trends 2026 | Google / Mandiant | Proprietary (citation permitted) |
| Microsoft Digital Defense Report 2025 | Microsoft | Proprietary (citation permitted) |
| ENISA Threat Landscape 2025 | ENISA | CC BY 4.0 |
| ENISA Public Administration Threat Landscape 2024 | ENISA | CC BY 4.0 |
| Dragos OT Cybersecurity Report 2026 | Dragos | Proprietary (citation permitted) |
| Cloudflare 2026 Threat Report | Cloudflare | Proprietary (citation permitted) |
| WEF Global Cybersecurity Outlook 2026 | WEF | Proprietary |
| APWG eCrime Trends Q4 2025 | APWG | Proprietary |
| IOCTA 2026 | Europol | Proprietary |
| IRPF 3.17.2025 | Various | See report |

---

## Maintenance

When a new external reference is added to any committed BEACON artifact,
add a row to this document before merging. If the license requires
attribution text to appear in distributed output, add it to
`src/beacon/generator/report_builder.py` footer generation.
