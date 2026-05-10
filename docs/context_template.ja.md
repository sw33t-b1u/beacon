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

---

## Identities and Access

> **このセクションの目的** — SAGE 0.6.0+ では identity-asset の
> アクセス関係を first-class なグラフエッジ (`HasAccess`) として保持
> する。脅威アクターがロール / チームを侵害した際、アナリストが 1 hop
> でリスクのある資産にピボットできるようになる。準拠フレームワーク:
> **NIST SP 800-53 AC-2 / AC-3、NIST SP 800-207 (Zero Trust)、
> ISO/IEC 27001:2022 A.5.16 / A.5.18、CIS Controls v8 #5 / #6**。

### 粒度のガイド

- **デフォルトはロール / チーム / グループ単位** (例: "電子マネー
  運用チーム", "DBA Group", "CFO")。ISO/IEC 27001 A.5.18 は role-
  based なアクセス権文書化を推奨している。多くの context.md は
  個人を名指しできない。
- **個人を名指しするのは権威ある情報源があり、運用上意味がある場合のみ**
  (単一の named system owner 等)。privacy / 鮮度の観点で原則回避。
- **システム / サービスアカウント** もここに含める (`identity_class:
  system`) — 自動化ユーザ、連携用アカウント、bot 等。

### Identity エントリ

`Critical Assets` を所有・運用する各ロール / チーム / 個人 / システム
ごとに 1 エントリ追加。該当する分だけ繰り返す。

### 1. [Identity 名 — 原文の言語をそのまま]
- **id**: [短く安定した slug、例: `id-finance-team`、`id-cfo`、
  `id-erp-admin`。再生成時にも変えないこと。]
- **identity_class**: [individual | group | system | organization | class | unspecified]
- **sectors**: [任意の STIX 2.1 §6.6 業種値 — 例: `financial-services`]
- **roles**: [短い職能タグ — 例: `operations`, `dba`, `executive`, `auditor`]
- **description**: [任意 — このアイデンティティが何をしているか、スコープ等]

### 2. [Identity 名]
- ...

### Access エントリ (`has_access`)

identity と asset の各ペアで、identity が認証を経た / 運用上のアクセス
を持つ関係を記載。`identity_id` と `asset_id` は両方とも上で宣言済の
エントリを指す必要がある。

### 1. [Identity → Asset]
- **identity_id**: [上記 "Identities" の `id` と一致]
- **asset_id**: [上記 "Critical Assets" の `id` と一致 (例: `CA-001`
  — BEACON が `asset-CA-001` に正規化)]
- **access_level**: [read | write | admin | deny]
- **role**: [任意のフリー形式エッジラベル — 例: "ERP admin",
  "残高管理 DB 運用保守"]
- **granted_at**: [任意の ISO 日付 — 不明なら空欄]
- **revoked_at**: [任意の ISO 日付 — 現役なら空欄]

### 2. [Identity → Asset]
- ...

### 文章から `access_level` を推定する

文書の表現が曖昧な場合は以下のマッピングを使う:

| 文書の表現 | access_level |
|---|---|
| "operates", "maintains", "管理者", "運用保守", root / superuser | `admin` |
| "updates", "modifies", "登録", "編集" | `write` |
| "reviews", "monitors", "閲覧", "参照" | `read` |
| 明示的な禁止 (稀) | `deny` |

### セクションを空のままにする場合

文書がロール-asset アクセス関係を記述していない (例: 資産だけ列挙
された初期コンテキスト) 場合は、このセクション自体を省略してよい。
**資産リストから identities を捏造しない** こと。
`generate_identity_assets.py` は空の `identity_assets.json` artifact
を出力し、TRACE はそれを受け入れる。

### 例 (抜粋)

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
