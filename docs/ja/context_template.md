# [組織名] — セキュリティコンテキスト

> **使い方**: このテンプレートをコピーして `input/context.md` として保存し、各セクションを実際の情報で埋めてください。
> `input/context.md` は `.gitignore` に含まれており、リポジトリには保存されません。

---

## Organization Overview

- **Name**: [組織名または部門名]
- **Industry**: [manufacturing | finance | energy | healthcare | defense | technology | logistics | government | education | other]
- **Sub-Industries**: [例: automotive, aerospace, pharmaceutical — 業種の細分類]
- **Geographies**: [例: Japan, Southeast Asia, Germany — 事業展開地域]
- **Employee Count**: [例: 1000-5000]
- **Revenue (USD)**: [例: 1B-10B]
- **Stock Listed**: [Yes / No]
- **Regulatory Requirements**: [例: APPI, ISO27001, TISAX, GDPR, FISC, PCI-DSS]
- **Organizational Scope**: [全社 / 部門名 — 特定部門のコンテキストであれば部門名を記載]

---

## Strategic Objectives

事業の戦略目標を記載します。M&A・海外展開・IPOなど、CTIの優先度に影響する意思決定を含めてください。

### 1. [目標タイトル]
- **Description**: [何を達成しようとしているか]
- **Timeline**: [例: 2025-2027]
- **Sensitivity**: [low | medium | high | critical]
- **Key Decisions**: [具体的な意思決定事項 — 例: M&A候補のデューデリジェンス、現地パートナー選定]

### 2. [目標タイトル]
- **Description**: ...
- **Timeline**: ...
- **Sensitivity**: ...
- **Key Decisions**: ...

---

## Current Projects

進行中または計画中のITプロジェクト・セキュリティに影響するイニシアチブを記載します。

### 1. [プロジェクト名]
- **Status**: [planned | in_progress | completed | cancelled]
- **Sensitivity**: [low | medium | high | critical]
- **Involved Vendors**: [例: SAP, Accenture, Microsoft]
- **Cloud Providers**: [GCP | AWS | Azure — 使用するクラウド]
- **Data Types**: [financial | hr | manufacturing | research | customer | intellectual_property | source_code | healthcare | personal]
- **Description**: [プロジェクト概要]

### 2. [プロジェクト名]
- **Status**: ...
- **Sensitivity**: ...

---

## Crown Jewels

喪失・漏洩した場合に事業継続や競争優位性に重大な影響を与えるデータ・情報資産を記載します。

### 1. [情報資産名]
- **System**: [格納・処理しているシステム名]
- **Business Impact if Lost/Compromised**: [low | medium | high | critical]
- **Exposure Risk**: [low | medium | high | critical]
- **Description**: [なぜこれがクラウン・ジュエルなのか]

### 2. [情報資産名]
- **System**: ...
- **Business Impact**: ...
- **Exposure Risk**: ...

---

## Critical Assets

業務継続に不可欠な、または攻撃対象として魅力的なシステム・インフラを記載します。
**技術詳細（ホスト名・OS・ネットワークゾーン等）をできる限り記載してください。**
サプライチェーン接続（サプライヤーシステムとの連携）もここに含めます。

### 1. [アセット名]
- **Type**: [server | database | network_device | application | endpoint | storage | identity_system | ot_device | cloud_service | other]
- **Function**: [このアセットが担うビジネス機能 — 例: "SAP S/4HANAによる財務・製造データ管理"]
- **Hostname**: [例: erp-prod-01.internal — 不明な場合は空欄]
- **OS/Platform**: [例: Windows Server 2022, RHEL 9, VMware ESXi 8 — 不明な場合は空欄]
- **Network Zone**: [internet | dmz | corporate | ot | cloud | restricted]
- **Criticality**: [low | medium | high | critical]
- **Data Types**: [financial | hr | manufacturing | research | customer | intellectual_property | source_code | healthcare | personal]
- **Managing Vendor**: [管理・運用しているベンダー — 内製の場合は空欄]
- **Supply Chain Role**: [サプライチェーン接続の説明 — 例: "Tier1サプライヤーEDIゲートウェイ"; 関係なければ空欄]
- **Dependencies**: [依存する他のアセット名]
- **Exposure Risk**: [low | medium | high | critical]

### 2. [サプライヤー/ベンダーシステム名] ※サプライチェーン接続がある場合
- **Type**: [application | cloud_service | network_device | other]
- **Function**: [例: "Tier1自動車サプライヤーのEDIシステム — 部品発注・JIT調整に使用"]
- **Network Zone**: [ot | corporate | cloud — 自社ネットワークから見たゾーン]
- **Criticality**: [high | critical]
- **Managing Vendor**: [ベンダー名]
- **Supply Chain Role**: [例: tier1_supplier_edi_connectivity, erp_integration_hub]
- **Exposure Risk**: [high | critical]

### 3. [追加アセット]
...

---

## Recent Security Incidents

過去のセキュリティインシデントを記載します（攻撃傾向の把握に使用）。

### 1. [年]
- **Type**: [phishing | ransomware | data_breach | bec | insider_threat | supply_chain | ddos | other]
- **Impact**: [low | medium | high | critical]
- **Notes**: [任意 — 概要・対応状況]

### 2. [年]
- **Type**: ...
- **Impact**: ...
