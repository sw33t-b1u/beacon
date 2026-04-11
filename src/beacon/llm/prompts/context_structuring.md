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

## Document

{{DOCUMENT}}
