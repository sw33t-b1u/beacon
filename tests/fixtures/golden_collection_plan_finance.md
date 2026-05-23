# Collection Plan

Generated: 2026-04-04
Organization: finance | Japan, United States, Singapore
Risk Score: Likelihood=5, Impact=5, Composite=25

---

## Monitoring Status

3 PIR(s) generated (P1/P2 threshold met). This plan covers supplemental collection activities.

**Active Business Triggers:**
- `cloud_dependency`
- `third_party_dependency`
- `external_facing_exposure`
- `regulated_disclosure_scope`
- `sectoral_high_risk`
- `ransomware_resilience_gap`
- `identity_credential_exposure`

---

## Priority Intelligence Requirements

3 PIR(s) generated — active collection required.

### [P1] PIR-2026-001

**Intelligence Level:** strategic
**Decision Point:** Financial fraud and cybercrime against in-scope services
**Valid:** 2026-04-04 → 2027-04-04

**Collection Focus:**
- Monitor new TTPs and infrastructure for: FIN13 / FIN7
- Vulnerability and exploitation reports targeting: financial

**Recommended Sources:**
- IPA Security Alerts [strategic, JP, cross-sector] — cross-sector sector coverage
- JVN (Japan Vulnerability Notes) [operational, JP, cross-sector] — cross-sector sector coverage
- FS-ISAC Threat Intelligence [operational, GLOBAL, finance] — finance sector coverage
- 金融ISAC (Japan Financial ISAC) [operational, JP, finance] — finance sector coverage
- Mandiant / Google Cloud Threat Intelligence [operational, GLOBAL, cross-sector] — matches G0046, G1016 via MITRE ATT&CK external_references
- Microsoft Threat Intelligence [operational, GLOBAL, cross-sector] — matches G0046 via MITRE ATT&CK external_references
- CrowdStrike Intelligence [operational, GLOBAL, cross-sector] — matches G0046 via MITRE ATT&CK external_references

### [P1] PIR-2026-002

**Intelligence Level:** strategic
**Decision Point:** State-sponsored actor activity targeting this unit
**Valid:** 2026-04-04 → 2027-04-04

**Collection Focus:**
- Monitor new TTPs and infrastructure for: APT-C-23 / APT-C-36 / APT1
- Vulnerability and exploitation reports targeting: erp, pki

**Recommended Sources:**
- JPCERT/CC Blog [strategic, JP, cross-sector] — matches G0032, G1054 via MITRE ATT&CK external_references
- IPA Security Alerts [strategic, JP, cross-sector] — cross-sector sector coverage
- CISA Advisories [strategic, US, GLOBAL, cross-sector] — matches G0032, G0094, G1017, G1033 via MITRE ATT&CK external_references
- JVN (Japan Vulnerability Notes) [operational, JP, cross-sector] — cross-sector sector coverage
- FS-ISAC Threat Intelligence [operational, GLOBAL, finance] — finance sector coverage
- 金融ISAC (Japan Financial ISAC) [operational, JP, finance] — finance sector coverage
- Mandiant / Google Cloud Threat Intelligence [operational, GLOBAL, cross-sector] — matches G0006, G0007, G0013, G0016 via MITRE ATT&CK external_references
- Microsoft Threat Intelligence [operational, GLOBAL, cross-sector] — matches G0007, G0010, G0016, G0032 via MITRE ATT&CK external_references
- CrowdStrike Intelligence [operational, GLOBAL, cross-sector] — matches G0006, G0007, G0010, G0016 via MITRE ATT&CK external_references

### [P1] PIR-2026-003

**Intelligence Level:** strategic
**Decision Point:** Generic espionage-motivated intrusion
**Valid:** 2026-04-04 → 2027-04-04

**Collection Focus:**
- Monitor new TTPs and infrastructure for: APT-C-23 / APT-C-36 / APT1

**Recommended Sources:**
- JPCERT/CC Blog [strategic, JP, cross-sector] — matches G1054 via MITRE ATT&CK external_references
- IPA Security Alerts [strategic, JP, cross-sector] — cross-sector sector coverage
- JVN (Japan Vulnerability Notes) [operational, JP, cross-sector] — cross-sector sector coverage
- FS-ISAC Threat Intelligence [operational, GLOBAL, finance] — finance sector coverage
- 金融ISAC (Japan Financial ISAC) [operational, JP, finance] — finance sector coverage
- Mandiant / Google Cloud Threat Intelligence [operational, GLOBAL, cross-sector] — matches G0006, G0007, G0013, G0016 via MITRE ATT&CK external_references
- Microsoft Threat Intelligence [operational, GLOBAL, cross-sector] — matches G0007, G0010, G0016, G0050 via MITRE ATT&CK external_references
- CrowdStrike Intelligence [operational, GLOBAL, cross-sector] — matches G0006, G0007, G0010, G0016 via MITRE ATT&CK external_references

---

## Threat Watch Items

> Items below are threat categories identified by the BEACON pipeline. Categories already covered by a generated PIR are labelled **[PIR COVERED]**.

### state_sponsored.China **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

### state_sponsored.France **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

### state_sponsored.Iran **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

### state_sponsored.North Korea **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

### state_sponsored.Russia **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

### state_sponsored.South Korea **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

### state_sponsored.Spain **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

### state_sponsored.Vietnam **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

### espionage **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

### financial_crime **[PIR COVERED]**

_Collection focus documented in Priority Intelligence Requirements above._

**Notable Groups to Monitor:**

APT-C-23, APT-C-36, APT1, APT12, APT16, APT17, APT18, APT19, APT28, APT29, APT3, APT30, APT32, APT33, APT37, APT39, APT41, APT42, APT5, Agrius, Ajax Security Team, Andariel, Aoqin Dragon, AppleJeus, BRONZE BUTLER, BlackTech, CURIUM, Charming Kitten, Cinnamon Tempest, Cleaver, Contagious Interview, CopyKittens, Daggerfly, Darkhotel, DragonOK, Dragonfly, Earth Lusca, Elderwood, Ember Bear, FIN13, FIN7, Ferocious Kitten, Fox Kitten, GALLIUM, GCMAN, Gamaredon Group, Gelsemium, HAFNIUM, HEXANE, Higaisa, Inception, IndigoZebra, Indrik Spider, Ke3chang, Kimsuky, Lazarus Group, Leviathan, Lotus Blossom, Machete, Magic Hound, MirrorFace, Mofang, Molerats, Moses Staff, MuddyWater, Mustang Panda, Naikon, Night Dragon, Nomadic Octopus, OilRig, Putter Panda, Rancor, Salt Typhoon, Sandworm Team, Scarlet Mimic, Silent Librarian, Sowbug, Star Blizzard, Suckfly, TA459, TA505, TA577, Threat Group-3390, Thrip, Tonto Team, Tropic Trooper, Turla, UNC3886, VOID MANTICORE, Volt Typhoon, Winter Vivern, Wizard Spider, ZIRCONIUM, admin@338, menuPass

---

## Trigger-Based Collection Actions

Business triggers detected in context. These require targeted collection beyond standard threat monitoring.

### cloud_dependency

- CSP セキュリティアドバイザリ (GCP/AWS/Azure)・cloud IAM 設定ミス事例・cloud-native 攻撃キャンペーン

### third_party_dependency

- 重要ベンダーのセキュリティ評価レポート・SBOM リスク情報・サードパーティ侵害事例 (Verizon DBIR 2025: 30%)

### external_facing_exposure

- CISA KEV カタログ・edge 機器 0-day 情報・インターネット直接公開資産の脆弱性スキャン

### regulated_disclosure_scope

- SEC 33-11216 / NIS2 / 金融庁 / 個人情報保護委員会 開示要件と過去インシデント事例

### sectoral_high_risk

- 業種 ISAC 情報共有・ENISA Sectoral Threat Landscape・業種固有の APT キャンペーン

---

## Recommended Collection Frequency

| Item | Frequency | Owner |
|------|-----------|-------|
| 脅威インテリジェンスフィード収集 | 月次 | CTIチーム |
| APTグループ TTP 更新確認 (APT-C-23, APT-C-36, APT1) | 月次 | CTIチーム |
| BEACON PIR 定期見直し | 四半期 | CISOオフィス |

---

_This document was auto-generated by BEACON. Review with your CTI team before acting on collection priorities._