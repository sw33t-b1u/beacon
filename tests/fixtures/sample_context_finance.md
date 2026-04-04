# Acme Finance Corp — Security Context Document

## Organization Overview

Acme Finance Corp is a mid-sized regional bank headquartered in Tokyo, Japan, with operations in South Korea and Singapore.
We have approximately 3,000 employees and annual revenue of around USD 2 billion.
The company is publicly listed on the Tokyo Stock Exchange.
We operate under APPI, FISC, and Basel III regulatory requirements.

## Strategic Objectives

### OBJ-001: Digital Transformation
We are accelerating our digital banking transformation through 2026, migrating core banking systems to a hybrid cloud environment (Azure). This project is considered highly sensitive as it involves customer financial data and transaction processing infrastructure.

### OBJ-002: Southeast Asia Expansion
We are exploring partnerships and potential acquisitions in Singapore and South Korea to expand our retail banking footprint. Due diligence processes are currently ongoing for two acquisition candidates.

## Current Projects

### Core Banking Migration (in progress)
- Status: In progress
- Systems: Migrating legacy on-premise core banking to Azure cloud
- Vendors: Microsoft, Accenture, local IT integrator
- Data involved: Financial transaction data, customer PII, credit scoring models
- Sensitivity: Critical

### Mobile Banking App v3 (in progress)
- Status: In progress
- Systems: Customer-facing mobile application
- Cloud: Azure
- Data: Customer personal data, payment data
- Vendors: External development firm

## Crown Jewels

1. **Core Banking System** — transaction ledger and settlement engine; loss would cause operational halt. Business impact: critical.
2. **Customer PII Database** — 2 million customer records including financial history. Business impact: critical. Exposure risk: medium (partially cloud-hosted).
3. **Credit Scoring Models** — proprietary ML models representing significant R&D investment. Business impact: high.

## Supply Chain

We rely on SWIFT for international transactions. Our cloud environment runs entirely on Azure. We do not have direct OT connectivity. Key third-party vendors include Microsoft, Accenture, and a credit bureau data provider.

## Recent Security Incidents

- 2023: Business email compromise attempt (low impact, contained)
- 2024: Phishing campaign targeting treasury team (medium impact, credentials reset)
