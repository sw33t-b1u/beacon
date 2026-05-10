You are a cybersecurity analyst assistant. Convert the following business strategy document into a structured JSON object conforming to the BusinessContext schema used for cyber threat intelligence (CTI) prioritization.

## Context

The document describes an organization's business environment. Your goal is to extract all information relevant to cyber risk assessment: strategic objectives, critical projects, crown jewels (high-value data/IP), detailed technical asset inventory, supply chain dependencies, and recent security incidents.

## Output Schema

Return ONLY valid JSON (no markdown fences, no explanation) with this exact structure:

```json
{
  "organization": {
    "name": "string",
    "unit_name": "string — department or team name if the document describes a sub-unit; otherwise empty string",
    "unit_type": "one of: company | division | department | team",
    "industry": "one of: manufacturing | finance | energy | healthcare | defense | technology | logistics | government | education | other",
    "sub_industries": ["string"],
    "geography": ["string — country or region names"],
    "employee_count_range": "string (e.g. '1000-5000')",
    "revenue_range_usd": "string (e.g. '1B-10B')",
    "stock_listed": true,
    "regulatory_context": ["string — e.g. APPI, ISO27001, GDPR, TISAX, FISC, PCI-DSS"]
  },
  "strategic_objectives": [
    {
      "id": "OBJ-001",
      "title": "string",
      "description": "string",
      "timeline": "string — e.g. '2025-2027'",
      "sensitivity": "one of: low | medium | high | critical",
      "key_decisions": ["string — specific decisions being made, e.g. M&A candidates, partner selection"]
    }
  ],
  "projects": [
    {
      "id": "PROJ-001",
      "name": "string",
      "status": "one of: planned | in_progress | completed | cancelled",
      "sensitivity": "one of: low | medium | high | critical",
      "involved_vendors": ["string"],
      "cloud_providers": ["string — GCP | AWS | Azure | Oracle Cloud | IBM Cloud"],
      "data_types": ["string — use: financial | hr | manufacturing | research | customer | intellectual_property | source_code | healthcare | personal"]
    }
  ],
  "crown_jewels": [
    {
      "id": "CJ-001",
      "name": "string — the data or IP asset (e.g. 'Customer PII Database', 'Product CAD Data')",
      "system": "string — the system that stores/processes it",
      "business_impact": "one of: low | medium | high | critical",
      "exposure_risk": "one of: low | medium | high | critical"
    }
  ],
  "critical_assets": [
    {
      "id": "CA-001",
      "name": "string — asset name",
      "type": "one of: server | database | network_device | application | endpoint | storage | identity_system | ot_device | cloud_service | other",
      "function": "string — what this asset does in the business context",
      "hostname": "string — optional hostname, empty if unknown",
      "os_platform": "string — optional OS, e.g. 'Windows Server 2022', 'RHEL 9', empty if unknown",
      "network_zone": "one of: internet | dmz | corporate | ot | cloud | restricted | unknown",
      "criticality": "one of: low | medium | high | critical",
      "data_types": ["string — same values as projects.data_types"],
      "managing_vendor": "string — vendor managing/operating this asset; empty if fully internal",
      "supply_chain_role": "string — describe supply chain function if applicable (e.g. 'tier1_supplier_edi_gateway'); empty otherwise",
      "dependencies": ["string — IDs of other critical_assets this depends on"],
      "exposure_risk": "one of: low | medium | high | critical"
    }
  ],
  "supply_chain": {
    "critical_vendors": ["string — all critical third-party vendors and suppliers"],
    "cloud_providers": ["string"],
    "ot_connectivity": false
  },
  "recent_incidents": [
    {
      "year": 2024,
      "type": "string — e.g. phishing | ransomware | data_breach | bec | insider_threat | supply_chain | ddos | other",
      "impact": "one of: low | medium | high | critical"
    }
  ],
  "identities": [
    {
      "id": "string — short stable identifier (e.g. id-finance-team, id-cfo, id-erp-admin)",
      "name": "string — preserve original language",
      "identity_class": "one of: individual | group | system | organization | class | unknown",
      "sectors": [],
      "roles": [],
      "description": ""
    }
  ],
  "has_access": [
    {
      "identity_id": "string — must match an entry in identities[].id",
      "asset_id": "string — must match an entry in critical_assets[].id",
      "access_level": "one of: read | write | admin | deny",
      "role": "string — free-form per-edge label (e.g. ERP admin)",
      "granted_at": "ISO date or empty",
      "revoked_at": "ISO date or empty"
    }
  ],
  "user_accounts": [
    {
      "id": "string — short stable identifier (e.g. ua-alice-corp, ua-svc-jenkins)",
      "account_login": "string — full account login (alice@corp.example.com, root, svc-jenkins)",
      "display_name": "string — preserve original language",
      "account_type": "STIX 2.1 §6.4 account-type-ov value: '' | unix | windows-local | windows-domain | ldap | tacacs | radius | nis | openid | facebook | skype | twitter | kavi",
      "is_privileged": false,
      "is_service_account": false,
      "identity_id": "string — optional, must match identities[].id when set",
      "description": ""
    }
  ],
  "account_on_asset": [
    {
      "user_account_id": "string — must match user_accounts[].id",
      "asset_id": "string — must match critical_assets[].id",
      "first_seen": "ISO date or empty",
      "last_seen": "ISO date or empty"
    }
  ]
}
```

## Section Recognition Guide

| Document Section | Maps To |
|-----------------|---------|
| Organization Overview / Company Profile | `organization.*` |
| Strategic Objectives / Goals / Vision | `strategic_objectives[]` |
| Current Projects / Initiatives / Programs | `projects[]` |
| Crown Jewels / Critical Data / Key Information Assets | `crown_jewels[]` |
| Critical Assets / IT Assets / Key Systems / Infrastructure | `critical_assets[]` |
| Supply Chain / Vendors / Third Parties / Partners | `supply_chain.*` AND relevant `critical_assets[]` entries |
| Recent Incidents / Security History / Previous Breaches | `recent_incidents[]` |
| Identities and Access / Roles / Teams with Access / RBAC | `identities[]` AND `has_access[]` |
| User Accounts / Login Accounts / Service Accounts | `user_accounts[]` AND `account_on_asset[]` |

## Mapping Rules

### Crown Jewels vs Critical Assets
- **`crown_jewels`** represents *data and information assets* whose loss or compromise would be devastating (e.g., customer PII, product IP, financial records, trade secrets).
- **`critical_assets`** represents *systems and infrastructure* that are operationally critical or high-value attack targets (e.g., ERP servers, domain controllers, OT devices, VPN gateways).
- **Overlap is expected and correct**: if a system hosts crown jewel data, create both a `CrownJewel` entry (emphasizing the data) and a `CriticalAsset` entry (emphasizing the system/infrastructure).

### Critical Assets — What to Extract
Extract every named or described system, server, database, application, network device, OT device, or cloud service that:
- Is explicitly listed as critical or important
- Is described as hosting sensitive data
- Is part of supply chain connectivity
- Is currently being migrated or integrated in an active project

For each, fill in as many technical fields as the document provides. Leave `hostname`, `os_platform` empty if not mentioned.

### Supply Chain in Critical Assets
- If a supplier, vendor, or partner system is described with connectivity details (e.g., "connected to our network", "EDI gateway", "VPN tunnel to supplier"), create a `critical_assets` entry for it with `supply_chain_role` filled in.
- Always add the vendor name to `supply_chain.critical_vendors` as well.
- Cloud providers mentioned in supply chain context should appear in both `supply_chain.cloud_providers` and as `cloud_service` type entries in `critical_assets` if they are described as critical infrastructure.

### OT / ICS / SCADA
- Set `supply_chain.ot_connectivity: true` if the document mentions OT, ICS, SCADA, PLC, DCS, historian, factory network, plant connectivity, or if any `critical_assets` entry has `network_zone: "ot"`.

### Field Defaults
- Missing arrays: `[]`
- Missing strings: `""`
- Missing booleans: `false`
- Unknown network zone: `"unknown"`
- Unknown type: `"other"`

### IDs
Sequential within each array: OBJ-001, OBJ-002 … / PROJ-001, PROJ-002 … / CJ-001, CJ-002 … / CA-001, CA-002 …

### Language
- Preserve the original language for: `name`, `unit_name`, `title`, `description`, `function`
- Use English for all Literal/enum fields and `type`, `industry`, `status`, `sensitivity`, `network_zone`, etc.
- `regulatory_context`: use official abbreviations (APPI, GDPR, ISO27001, PCI-DSS, TISAX, FISC, HIPAA, SOX, etc.)

### Sensitivity Inference
- `critical`: data or systems described as "most sensitive", "highest priority", or "if lost, operations halt"
- `high`: described as "confidential", "strategic", "M&A related"
- `medium`: normal business data, limited internal distribution
- `low`: publicly available, non-sensitive

### Identities and Access (Initiative A)
The "Identities and Access" section describes who (which roles, teams,
or individuals) has access to which `critical_assets`. Extract every
named role / team / group / individual mentioned in connection with
asset operation, administration, or data access — and the assets they
touch — into `identities[]` and `has_access[]`.

- **identity_class** —
  - `group` for teams, departments, named groups (the typical case)
  - `individual` only when a specific person is named (rare in
    organizational context docs)
  - `system` for service accounts, automation, integration users
  - `organization` for external partner organizations
  - `class` for abstract role classes ("any administrator")
  - `unknown` when the document is genuinely ambiguous (STIX 2.1
    §6.7 ``identity-class-ov`` value)
- **id** — `id-` prefix + short slug (`id-finance-team`,
  `id-erp-admin`). Stable across regenerations.
- **roles[]** — short job-function tags (`operations`, `dba`,
  `executive`, `auditor`).
- **has_access[*].asset_id** — must match an existing
  `critical_assets[].id` (`CA-...`). If the document mentions access
  to a system that is not in `critical_assets`, first add the system
  to `critical_assets`, then reference its id here.
- **access_level** — infer from the document language:
  - `admin` — "operates", "maintains", "管理者", "運用保守", root /
    superuser access
  - `write` — "updates", "modifies", "登録", "編集"
  - `read` — "reviews", "monitors", "閲覧", "参照"
  - `deny` — explicit prohibition (rare in context docs)
- **role** — free-form description of the per-edge job context
  (preserve original language).
- **granted_at / revoked_at** — leave empty unless an explicit date is
  in the document.

If the section is absent, return `identities: []` and `has_access: []`
(do not invent entries from other sections).

### User Accounts and Asset Mapping (Initiative B)
The "User Accounts" section enumerates individual login identifiers
(`alice@corp.example.com`, `svc-jenkins`, domain SIDs, cloud
principals) and the hosts each is valid on.

- **id** — `ua-` prefix + short slug (`ua-alice-corp`,
  `ua-svc-jenkins`). Stable across regenerations.
- **account_login** — exact login string as it would appear at
  authentication (`alice@corp.example.com`, `root`,
  `S-1-5-21-…`).
- **account_type** — STIX 2.1 §6.4 ``account-type-ov`` only.
  Permitted values: `""` (empty), `unix`, `windows-local`,
  `windows-domain`, `ldap`, `tacacs`, `radius`, `nis`, `openid`,
  `facebook`, `skype`, `twitter`, `kavi`. Use:
  - `unix` — root, daemon, named *nix logins
  - `windows-local` — host-local Windows accounts
  - `windows-domain` — `DOMAIN\\user` or `user@domain.local`
  - `ldap` — directory-bound POSIX/UNIX or generic LDAP accounts
  - `openid` — OIDC-federated accounts
  - **Empty string** when no STIX value applies (Azure AD,
    Google Workspace, Kerberos, generic SaaS, automation /
    pipeline accounts, ambiguous cases). Do NOT invent
    extension values like `azure-ad` or `service` — surface
    those distinctions via `is_service_account` and
    `description` instead.
- **is_privileged** — true for root/admin/Domain Admin/sudoers/
  highly-privileged service accounts. Default false.
- **is_service_account** — true when the account is non-human
  (CI bot, integration user, daemon).
- **identity_id** — optional. When the account is owned by a
  named human role / team in `identities[]`, link via the
  `id-...` slug. Leave empty for shared / generic accounts.

`account_on_asset[*]` records every (account, host) pair the
document describes. The same `account_login` valid on multiple
hosts produces multiple entries.

If the section is absent, return `user_accounts: []` and
`account_on_asset: []` (do not invent accounts from prose).

## Document

{{DOCUMENT}}
