# [Organization Name] — Security Context Document

> **Usage**: Copy this template to `input/context.md` and fill in each section with
> your organization's actual information.
> `input/context.md` is listed in `.gitignore` and will never be committed.
> Japanese version: `docs/ja/context_template.md`

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
