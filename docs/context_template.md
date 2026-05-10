# [Organization Name] — Security Context Document

> **Usage**: Copy this template to `input/context.md` and fill in each section with
> your organization's actual information.
> `input/context.md` is listed in `.gitignore` and will never be committed.
> Japanese version: `docs/context_template.ja.md`

---

## Organization Overview

- **Name**: [Organization or department name]
- **Industry**: [manufacturing | finance | energy | healthcare | defense | technology | logistics | government | education | other]
- **Sub-Industries**: [e.g., automotive, aerospace, pharmaceutical]
- **Geographies**: [e.g., Japan, Southeast Asia, Germany — regions where the org operates]
- **Employee Count**: [e.g., 1000-5000]
- **Revenue (USD)**: [e.g., 1B-10B]
- **Stock Listed**: [Yes / No]
- **Regulatory Requirements**: [e.g., APPI, ISO27001, TISAX, GDPR, FISC, PCI-DSS, HIPAA]
- **Organizational Scope**: [Entire company / specific department or team name]

---

## Strategic Objectives

List business goals that could influence your threat profile. Include M&A activity,
geographic expansion, IPO plans, or major partnerships — any decision where intelligence
gathering by competitors or state actors would be valuable.

### 1. [Objective Title]
- **Description**: [What the objective aims to achieve]
- **Timeline**: [e.g., 2025-2027]
- **Sensitivity**: [low | medium | high | critical]
- **Key Decisions**: [Specific decisions being made, e.g., M&A candidates under review, partner selection, technology choices]

### 2. [Objective Title]
- **Description**: ...
- **Timeline**: ...
- **Sensitivity**: ...
- **Key Decisions**: ...

---

## Current Projects

List in-progress or planned IT/OT projects with security implications.

### 1. [Project Name]
- **Status**: [planned | in_progress | completed | cancelled]
- **Sensitivity**: [low | medium | high | critical]
- **Involved Vendors**: [e.g., SAP, Accenture, Microsoft]
- **Cloud Providers**: [GCP | AWS | Azure]
- **Data Types**: [financial | hr | manufacturing | research | customer | intellectual_property | source_code | healthcare | personal]
- **Description**: [Brief project summary]

### 2. [Project Name]
- **Status**: ...
- **Sensitivity**: ...

---

## Crown Jewels

List data and information assets whose loss or compromise would be severely damaging
to the business (competitive position, regulatory standing, or operational continuity).

### 1. [Information Asset Name]
- **System**: [Name of the system that stores or processes it]
- **Business Impact if Lost/Compromised**: [low | medium | high | critical]
- **Exposure Risk**: [low | medium | high | critical]
- **Description**: [Why this is a crown jewel — e.g., "10 years of proprietary formulas"]

### 2. [Information Asset Name]
- **System**: ...
- **Business Impact**: ...
- **Exposure Risk**: ...

---

## Critical Assets

List systems and infrastructure that are operationally critical or are attractive
attack targets. **Provide as much technical detail as available.**
Include supply chain-connected systems (supplier/vendor gateways) in this section.

### 1. [Asset Name]
- **Type**: [server | database | network_device | application | endpoint | storage | identity_system | ot_device | cloud_service | other]
- **Function**: [What this asset does — e.g., "SAP S/4HANA managing financial, HR, and manufacturing data"]
- **Hostname**: [e.g., erp-prod-01.internal — leave blank if unknown]
- **OS/Platform**: [e.g., Windows Server 2022, RHEL 9, VMware ESXi — leave blank if unknown]
- **Network Zone**: [internet | dmz | corporate | ot | cloud | restricted]
- **Criticality**: [low | medium | high | critical]
- **Data Types**: [financial | hr | manufacturing | research | customer | intellectual_property | source_code | healthcare | personal]
- **Managing Vendor**: [Vendor managing/operating this asset — leave blank if fully internal]
- **Supply Chain Role**: [Describe supply chain function if applicable, e.g., "Tier-1 supplier EDI gateway"; leave blank otherwise]
- **Dependencies**: [Other systems this depends on]
- **Exposure Risk**: [low | medium | high | critical]

### 2. [Supplier/Vendor System — if supply chain connectivity exists]
- **Type**: [application | cloud_service | network_device | other]
- **Function**: [e.g., "Tier-1 automotive supplier EDI system for parts ordering and JIT delivery coordination"]
- **Network Zone**: [ot | corporate | cloud — as seen from your network]
- **Criticality**: [high | critical]
- **Managing Vendor**: [Vendor name]
- **Supply Chain Role**: [e.g., tier1_supplier_edi_connectivity, erp_integration_hub]
- **Exposure Risk**: [high | critical]

### 3. [Additional Asset]
...

---

## Recent Security Incidents

List past security incidents to help calibrate threat likelihood.

### 1. [Year]
- **Type**: [phishing | ransomware | data_breach | bec | insider_threat | supply_chain | ddos | other]
- **Impact**: [low | medium | high | critical]
- **Notes**: [Optional — brief description or outcome]

### 2. [Year]
- **Type**: ...
- **Impact**: ...

---

## Identities and Access

> **Why this section matters** — SAGE 0.6.0+ stores identity-asset
> access as a first-class graph edge (`HasAccess`). When a threat
> actor compromises a role / team, analysts can pivot in one hop to
> the assets at risk. Frameworks: **NIST SP 800-53 AC-2 / AC-3, NIST
> SP 800-207 (Zero Trust), ISO/IEC 27001:2022 A.5.16 / A.5.18, CIS
> Controls v8 #5 / #6**.

### Granularity guidance

- **Default to roles, teams, and groups** (e.g. "電子マネー運用チーム",
  "DBA Group", "CFO"). ISO/IEC 27001 A.5.18 explicitly recommends
  role-based access documentation. Most context.md docs do not name
  individuals.
- **Name individuals only when authoritatively known** and the
  individual's mention is operationally meaningful (e.g. a single
  named system owner). Avoid for privacy / staleness reasons.
- **System / service accounts** belong here too (`identity_class:
  system`) — list the automation user, the integration account, the
  bot.

### Identity entries

For each role / team / individual / system that owns or operates
listed `Critical Assets`, add an entry. Repeat for as many as apply.

### 1. [Identity Name — preserve original language]
- **id**: [short stable slug, e.g. `id-finance-team`, `id-cfo`,
  `id-erp-admin`. Keep stable across regenerations.]
- **identity_class**: [individual | group | system | organization | class | unspecified]
- **sectors**: [optional STIX 2.1 §6.6 industry sectors — e.g. `financial-services`]
- **roles**: [short job-function tags — e.g. `operations`, `dba`, `executive`, `auditor`]
- **description**: [optional — what this identity does, scope, etc.]

### 2. [Identity Name]
- ...

### Access entries (`has_access`)

For each identity-asset pair where the identity has authenticated /
operational access to the asset, add an entry. Both `identity_id`
and `asset_id` must point to entries you've already declared above.

### 1. [Identity → Asset]
- **identity_id**: [must match an `id` from "Identities" above]
- **asset_id**: [must match an `id` from "Critical Assets" above
  (e.g. `CA-001` — BEACON normalizes to `asset-CA-001`)]
- **access_level**: [read | write | admin | deny]
- **role**: [optional free-form per-edge label — e.g. "ERP admin",
  "残高管理 DB 運用保守"]
- **granted_at**: [optional ISO date — leave blank if unknown]
- **revoked_at**: [optional ISO date — leave blank if still active]

### 2. [Identity → Asset]
- ...

### Inferring `access_level` from prose

When the document language is ambiguous, use these mappings:

| Document language | access_level |
|---|---|
| "operates", "maintains", "管理者", "運用保守", root / superuser | `admin` |
| "updates", "modifies", "登録", "編集" | `write` |
| "reviews", "monitors", "閲覧", "参照" | `read` |
| explicit prohibition (rare) | `deny` |

### When to leave the section empty

If the document does not describe role-asset access relationships
(e.g. early-stage context with only assets listed), leave the
section out entirely. Do **not** invent identities from the asset
list — `generate_identity_assets.py` will emit an empty
`identity_assets.json` artifact, which TRACE accepts.

### Example (excerpt)

```markdown
## Identities and Access

### 1. 電子マネーシステム部 運用保守エンジニアチーム
- **id**: id-payment-ops
- **identity_class**: group
- **sectors**: financial-services
- **roles**: operations, maintenance
- **description**: Edy 決済処理サーバの 24/7 運用保守

### 2. データベース管理者グループ
- **id**: id-dba
- **identity_class**: group
- **roles**: dba
- **description**: 楽天 ID 連携 DB と残高管理 DB の DBA

### 1. id-payment-ops → CA-001
- **identity_id**: id-payment-ops
- **asset_id**: CA-001
- **access_level**: admin
- **role**: 決済処理サーバ運用保守

### 2. id-dba → CA-002
- **identity_id**: id-dba
- **asset_id**: CA-002
- **access_level**: admin
- **role**: 残高管理 DB DBA
```

---

## User Accounts

> **Why this section matters** — SAGE 0.7.0+ (Initiative B) stores
> individual login identifiers as a `UserAccount` graph node, with
> edges to host `Asset` (`AccountOnAsset`) and optionally to
> `Identity` (`UserAccountBelongsTo`). This drops one level deeper
> than Initiative A's role-asset edge: when CTI reports
> `alice@corp.example.com` was compromised, analysts can pivot to
> the assets where that login is valid.
>
> Frameworks: **NIST SP 800-53 IA-2 / IA-4 / AC-2; NIST SP 800-63B;
> ISO/IEC 27001:2022 A.5.16 / A.8.5; CIS Controls v8 #5**.
> Empirical: Verizon DBIR 2025 (stolen credentials = #1 initial-
> access at 22%); CrowdStrike GTR 2025 (valid-account abuse = #1
> cloud vector at 35%).

### Granularity guidance

- **Individual account identifiers** — one entry per login
  (`alice@corp.example.com`, `root`, `svc-jenkins`, domain SIDs).
  Same login on multiple hosts produces multiple `account_on_asset`
  entries.
- **Service accounts** belong here too — `svc-*`, `_jenkins`,
  `nt service\\*`, automation users. Set `is_service_account: true`.
- **Privileged accounts** — root, Domain Admin, sudoers, highly-
  privileged service accounts. Set `is_privileged: true` (CIS
  Controls v8 #5.4 requires separate inventory).
- **Optional Identity link** — when a human role/team in
  `identities[]` owns the account, set `identity_id`. Leave empty
  for shared / generic / unattributed accounts.

### Account entries

For each named login on `Critical Assets`, add an entry.

### 1. [Account Login]
- **id**: [short stable slug, e.g. `ua-alice-corp`, `ua-svc-jenkins`]
- **account_login**: [exact login string used at authentication]
- **display_name**: [optional human-readable name]
- **account_type**: [unix-account | windows-local | windows-domain | ldap | kerberos | azure-ad | google-workspace | saas | service | other]
- **is_privileged**: [true | false]
- **is_service_account**: [true | false]
- **identity_id**: [optional — must match an `id` from "Identities" above]
- **description**: [optional]

### Account-on-asset entries

For each (account, host) pair, add an entry.

### 1. [Account → Asset]
- **user_account_id**: [must match an `id` from "User Accounts" above]
- **asset_id**: [must match an `id` from "Critical Assets" above (e.g. `CA-005`; BEACON normalizes to `asset-CA-005`)]
- **first_seen**: [optional ISO date]
- **last_seen**: [optional ISO date — leave blank if still active]

### When to leave the section empty

If the document does not describe individual accounts, leave the
section out entirely. Do **not** invent accounts from the asset
list — `generate_user_accounts.py` will emit empty arrays, which
TRACE accepts.

### Example (excerpt)

```markdown
## User Accounts

### 1. ua-payment-ops-admin
- **id**: ua-payment-ops-admin
- **account_login**: ops-admin
- **account_type**: unix-account
- **is_privileged**: true
- **identity_id**: id-payment-ops
- **description**: 決済処理サーバの運用保守用 root-equivalent

### 2. ua-svc-edy-batch
- **id**: ua-svc-edy-batch
- **account_login**: svc-edy-batch
- **account_type**: service
- **is_privileged**: false
- **is_service_account**: true
- **description**: バッチ処理用サービスアカウント

### 1. ua-payment-ops-admin → CA-001
- **user_account_id**: ua-payment-ops-admin
- **asset_id**: CA-001

### 2. ua-svc-edy-batch → CA-001
- **user_account_id**: ua-svc-edy-batch
- **asset_id**: CA-001

### 3. ua-svc-edy-batch → CA-002
- **user_account_id**: ua-svc-edy-batch
- **asset_id**: CA-002
```
