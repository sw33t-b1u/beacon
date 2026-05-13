# BEACON ビジネストリガー

English version: [`docs/triggers.md`](triggers.md)

本書は BEACON の 10 のビジネストリガー、それぞれの定義・検出ロジック・
外部出典を記録する canonical な文書である。トリガーの追加・削除・重み
変更は本ファイルを同一 commit で更新すること。

---

## トリガーとは

**トリガー**とは、`BusinessContext` から派生する組織の構造的状態シグナル
であり、定常運用と比較してサイバー攻撃面または脅威曝露が実質的に上昇
していることを示す。

概念的 anchor は **NIST SP 800-37 Rev 2** §F *Event-Driven Triggers /
Significant Changes to the Environment of Operation*:

> "Organizations define event-driven triggers (i.e., indicators or prompts
> that cause a predefined organizational reaction) for both ongoing
> authorization and reauthorization."

BEACON の 10 トリガーは、BusinessContext スキーマで検出可能な範囲における
significant change の **business-level 列挙**である。各トリガーは以下の
いずれかで裏付けられる:

- 長期 standard（NIST / ISO / IEC / SEC / EU 規制）
- 過去 12 ヶ月の独立 ≥2 件の incident-response 報告

トリガーは **記述的**（組織がその状態にあると記録）かつ **規範的**
（likelihood に +1、intelligence level を `tactical` → `operational` に
昇格）である。NIST SP 800-37 R2 は trigger 間の重み差別化を規定して
いないため、BEACON も 10 トリガーを **対称**に扱う。

---

## 10 のトリガー

### 1. `cloud_dependency`

**定義:** 組織がパブリッククラウドに構造的依存している（移行中・運用中・
クラウド管理サービス利用中いずれも該当）。

**検出** (`element_extractor._detect_triggers`):

```
projects[*].cloud_providers が非空
  OR supply_chain.cloud_providers が非空
  OR critical_assets[*].network_zone == "cloud"
```

**出典**

- *NIST SP 800-37 Rev 2* — environment of operation の significant change 概念。
- *CISA Cloud Security Technical Reference Architecture v2* (2023) —
  「クラウド資産の migration / moving / expansion における優先考慮事項」。
- *CrowdStrike Global Threat Report 2025* — cloud intrusions YoY +26%、
  valid account abuse 35%（cloud 系の最多侵入手法）。
- *Mandiant M-Trends 2026* — Mandiant の 2025 年調査における cloud 関連
  侵害では、初期侵入手法の最頻は voice phishing (23%)、次いで第三者経由侵害。
- *IBM Cost of a Data Breach Report 2025* — multi-environment データ分散が
  コスト増幅要因。

**Limitations:** 移行中／運用成熟／撤退の各フェーズを区別しない。
すべて等しく elevated risk として扱うが、案件別にアナリスト判断で
調整する余地あり。

---

### 2. `it_ot_convergence`

**定義:** 組織が IT/OT 統合点を持つ（コーポレート IT 網が産業制御 / OT
系へ到達可能）。

**検出:**

```
supply_chain.ot_connectivity == True
  OR any(critical_assets[*].network_zone == "ot")
```

**出典**

- *NIST SP 800-82 Rev 3 — Guide to Operational Technology (OT) Security*
  (2023) §1.2 — "OT ネットワークと広域接続網の統合の加速… 新規サイバー
  リスク"。
- *Dragos 2026 OT Cybersecurity Year in Review (9th Annual)* — 2025 年に
  119 の ransomware グループが 3,300+ の産業組織に影響 (2024 年は 1,693
  攻撃)。新たに OT 特化の脅威グループ (AZURITE / PYROXENE / SYLVANITE)
  を 3 件 identify。
- *ENISA Threat Landscape 2025* — OT 脅威は全脅威カテゴリの 18.2%。
- *IEC 62443 — Industrial Communication Networks Security* — IT/OT ゾーン
  分離の国際標準。

---

### 3. `third_party_dependency`

**定義:** 組織が外部ベンダー / サプライヤ / マネージドサービス
プロバイダに critical 依存している。

**検出:**

```
supply_chain.critical_vendors が非空
  OR any(critical_assets[*].managing_vendor が非空)
```

**出典**

- *NIST SP 800-161 Rev 1 — Cybersecurity Supply Chain Risk Management
  Practices* (2024) — 「サプライチェーンはグローバルで複雑かつ動的、
  しばしば多層サプライヤを含む」。
- *Verizon Data Breach Investigations Report 2025* — 第三者関与が breach
  の 30%、前年の 15% から倍増。
- *IBM Cost of a Data Breach Report 2025* — 第三者ベンダー / サプライ
  チェーン侵害は平均 breach コスト USD 4.91 million、検出・封じ込めに
  最長で 267 日 (≈ 9 ヶ月)。
- *Executive Order 14028 — Improving the Nation's Cybersecurity* — ソフト
  ウェアサプライチェーンを連邦サイバー優先事項として正式化。

---

### 4. `external_facing_exposure`

**定義:** 組織がインターネット直接到達可能な critical asset を運用、
または high/critical exposure risk の crown jewel を保有。

**検出:**

```
any(critical_assets[*].network_zone in {"internet", "dmz"})
  OR any(crown_jewels[*].exposure_risk in {"high", "critical"})
```

**出典**

- *Mandiant M-Trends 2026* — internet-facing system exploitation は 6 年
  連続で初期侵入手法 #1（侵入経路特定可能ケースの 32%）。
- *Verizon DBIR 2025* — 脆弱性 exploit が breach の 20%、edge デバイス
  exploitation 8 倍、新規 edge CVE の mass-exploit 中央値はゼロ日。
- *CISA Known Exploited Vulnerabilities (KEV) Catalog* — インター
  ネット到達可能脆弱性の優先修復を連邦に義務付ける枠組み。

---

### 5. `regulated_disclosure_scope`

**定義:** 組織が証券・業種・データ保護のいずれかの規制当局による
material サイバー incident 開示義務の対象。

**検出:**

```
organization.stock_listed == True
  OR any(disclosure-regulation キーワード in organization.regulatory_context)
```

キーワードセットは `schema/trigger_keywords.json` →
`disclosure_regulation_keywords` から取得。既定値: SEC / Form 10-K / 8-K /
Item 106 / NIS2 / HIPAA Breach Notification / PCI-DSS / 金融商品取引法 /
個人情報保護法 / 資金決済法 / APPI。

**出典**

- *SEC Final Rule 33-11216 — Cybersecurity Risk Management, Strategy,
  Governance, and Incident Disclosure* (2023) — Item 106 で公開企業に
  material cyber プロセスの開示を義務付け、material incident は 8-K で
  4 営業日以内。
- *EU NIS2 Directive (2022/2555) Article 23* — essential / important entity
  の significant incident 通知義務。
- *HIPAA Breach Notification Rule (45 CFR §§164.400-414)* — covered entity
  と business associate に HHS / 個人 / メディア通知義務。

**Limitations:** キーワード方式の規制検出。既定キーワードに含まれない
業種別規制（NY DFS Part 500 等）はキーワード拡張が必要。

---

### 6. `sectoral_high_risk`

**定義:** 過去 12 ヶ月の主要脅威報告で disproportionately に
標的化されている業種。

**検出:**

```
organization.industry in {finance, healthcare, energy, manufacturing,
                          government, defense, logistics, technology}
```

定数 `_HIGH_RISK_SECTORS` は `src/beacon/analysis/element_extractor.py`。
集合は以下の経験的交集合:

- *ENISA Threat Landscape 2025* セクター分析（公共行政 38%、製造 59% は
  サイバー犯罪由来）。
- *Verizon DBIR 2025* 業種別 breakdown。
- *CrowdStrike Global Threat Report 2025* — 金融 / メディア / 製造 /
  industrials and engineering の 4 sector で China-nexus 侵入が YoY
  +200〜300%。政府 / 技術 / 通信 (China-nexus トップ 3 ターゲット) は
  YoY 約 +50%。
- *ENISA Threat Landscape: Finance Sector (Jan 2023 – Jun 2024)* — finance
  は EU で 3 番目に標的化されたセクター (公共行政・運輸に次ぐ)。2023 年
  の NIS 重大インシデント報告のうち 12% が EU finance sector。
- *ENISA Sectoral Threat Landscapes*（公共行政・エネルギー・医療・運輸・
  通信 — 公共行政 / Finance のみ `ref/` に保持。エネルギー / 医療 /
  運輸 / 通信は次版発行時に追加）。

**更新頻度:** 年次。ENISA / Verizon / CrowdStrike の翌年版発行時に経験的
交集合を再計算し、変動があれば本書と定数を同一 commit で更新。

---

### 7. `ai_adoption_exposure`

**定義:** 組織が AI/ML 系（classical ML パイプライン・生成 AI・LLM
エージェント・RAG 系）を導入または運用中であり、明示的な AI ガバナンス
証跡が BusinessContext に存在しない。

**検出:**

```
AI/ML キーワード（EN+JA）が以下のいずれかに出現:
  strategic_objectives[*].{title, description, key_decisions}
  OR projects[*].{name, data_types}
```

キーワードセットは `schema/trigger_keywords.json` →
`ai_adoption_keywords`。日本語入力ドキュメント対応のため bilingual。

**出典**

- *IBM Cost of a Data Breach Report 2025* — shadow AI が breach コスト
  平均に $670K 上乗せ、breach 組織の 63% が AI ガバナンスポリシー欠如、
  AI 関連 breach の 97% でアクセス制御欠如。
- *International AI Safety Report 2026* (chair Y. Bengio) — AI システム
  が実環境のサイバー攻撃で使用される事例が増加。2025 年に 12 社が
  Frontier AI Safety Frameworks を公開／更新したが、リスク管理コミット
  メントの大半は依然 voluntary。
- *CrowdStrike Global Threat Report 2025* — vishing が H1→H2 2024 で
  +442%、AI 駆動。AI 生成 phishing の量産。
- *ENISA Threat Landscape 2025* — 2025 年初頭時点で AI 支援 phishing
  キャンペーンが世界の社会的工学攻撃観測の 80% 超。
- *Trend Micro Security Predictions for 2026 — The AI-fication of
  Cyberthreats* — ransomware は AI 駆動の完全自動化オペレーションへ進化
  すると予測、cloud-native phishing は email / SMS / voice / AI-driven
  tactics の混合形態に。

**Limitations:** AI の存在を flag するが、ガバナンスの不在を
直接検出するものではなく、score 上昇は予防的（opportunistic）。
将来、AI シグナル AND `regulatory_context` に AI ガバナンス
キーワード欠落、で AND 条件化する余地あり。

---

### 8. `geopolitical_exposure`

**定義:** 組織が高リスク地政学ゾーンに本社・運用拠点・主要顧客地域・
サプライチェーン origin を持つことで、国家関連・nexus・紛争波及型
サイバー活動への曝露が上昇している。

**検出:**

```
HIGH_RISK_GEOPOLITICAL_ZONES に以下のいずれかが含まれる:
  geopolitical_exposure.headquartered_country
  OR geopolitical_exposure.operational_countries の任意要素
  OR geopolitical_exposure.primary_customer_regions の任意要素
  OR geopolitical_exposure.supply_chain_origin_regions の任意要素
```

`HIGH_RISK_GEOPOLITICAL_ZONES` は ISO 3166-1 alpha-2 コードの frozenset:
`{UA, RU, IL, PS, TW, CN, IR, KP, SY, YE}`。2025-2026 reporting window 中の
紛争ゾーンと state-sponsored サイバー活動拠点の交差を経験的に抽出。
集合の拡張・改訂は ref/ コーパスに対する明示的な再 review が必要 —
politically judgemental な constant である。

ブロック未指定（`geopolitical_exposure is None`）の場合、本 trigger は
**fire しない**。下記 §9 / §10 とは対照的に「情報なし = 高リスク」と
扱うのは false-positive が actionable でないため。

**出典**

- *CrowdStrike Global Threat Report 2025* — "China-nexus activity surged
  150% overall, with some targeted industries suffering 200% to 300% more
  attacks than the previous year"（`ref/CrowdStrikeGlobalThreatReport2025.md`
  63-65 行目）。同 922-923 行: "financial services, media, manufacturing,
  and industrials and engineering sectors, which all experienced 200-300%
  increases in observed China-nexus intrusions"。
- *Cloudflare 2026 Threat Report* — "geopolitical leverage"
  （`ref/Cloudflare-2026-threat-report.md` 77 行）、"highly sophisticated
  state-sponsored pre-positioning"（1591 行）。
- *IOCTA 2026 (Europol)* — Russia-based / Russian-speaking cybercrime
  ecosystems を全編に記述; Initial Access Brokers エコシステム章は
  `ref/IOCTA-2026.md` 921 行。
- *INTERPOL Asia and South Pacific Cyber Threat Assessment 2025/2026* —
  ASP 地政学的曝露専用 regional CTI
  （`ref/CYBER_ASP Cyber Threat Assessment Report_2025_2026_v4.md`）。
- *Mandiant M-Trends 2026* — "Regional Breakouts" 章（Americas / EMEA /
  JAPAC）が regional differential を扱う。

**Limitations:**

- 高リスクゾーン集合は judgement call。EU 加盟国の NIS2 wartime advisory
  下や US 重要インフラなど edge case は集合に含まれない。
- HQ 在所・顧客所在・サプライチェーン所在の semantic は本来異なる
  （能動曝露 vs 受動曝露）が、現状は対称に扱っている。差別重みは
  将来 revision 候補。
- 集合の拡張・改訂は同じ ref/ コーパスを参照することで、経験的根拠から
  political judgement への drift を回避する。

---

### 9. `ransomware_resilience_gap`

**定義:** 組織が ransomware 復旧 readiness を `backup_strategy` /
`incident_response_plan` / `recovery_test_cadence` で示せない状態。
2025-2026 reporting window では ransomware はほぼ普遍的脅威であり、
resilience evidence を持たない組織は侵入された際の business
continuity impact が桁違いに大きい。

**検出:**

```
business_continuity is None
  OR NOT (backup_strategy_documented
          AND backup_offsite_or_immutable
          AND incident_response_plan_documented
          AND 0 < recovery_test_cadence_days <= 180)
```

ブロック未指定（`business_continuity is None`）→ trigger **fire**
（保守的: undocumented = 高リスク扱い、M-Trends 2026 "Ransomware is Now
a Resilience Problem" の framing に従う）。180 日 recovery-test cadence
threshold は NIST SP 800-34 / ISO 22301 の plan-testing currency 推奨に
近似。

**出典**

- *ENISA Threat Landscape 2025* — "ransomware accounting for 83.9% and
  data breaches 16.1% of cybercrime incidents"
  （`ref/ENISA_Threat_Landscape_2025_v1.2.md` 730 行）。同 EU 切り口
  931 行: "ransomware (81.1%) and data breaches (15.2%)"。
- *Mandiant M-Trends 2026* — "In 44% of Mandiant's 2025 investigations,
  the intrusion"（`ref/m-trends-2026-en.md` 1270 行）、章 "Ransomware
  is Now a Resilience Problem"（TOC 25 行）— 本 trigger 命名の直接根拠。
- *IBM Cost of a Data Breach Report 2025* — ransomware "hit USD 5.08
  million in this year's report"
  （`ref/20250822_Cost-of-a-Data-Breach-Report-2025.md` 51 行）。
- *Dragos 2026 OT Cybersecurity Year in Review* — "Dragos tracked 119
  ransomware groups targeting industrial organizations"
  （`ref/Dragos-2026-OT-Cybersecurity-Report-A-Year-in-Review.md` 1641
  行）; 2024 年の 1,693 件から 2025 年の 3,300+ 件へほぼ 2 倍化。
- *CrowdStrike Global Threat Report 2025* — eCrime / ransomware-as-a-service
  ecosystem を全編で扱う。

**Limitations:**

- "documented" は self-report で gaming されやすい。verifiable signal
  （backup SaaS ベンダーの導入有無、ISO 22301 認証）への置換が将来 revision
  候補。
- 180 日 cadence threshold は rule-of-thumb。ISO 22301 / NIST SP 800-34
  は単一数値を規定しておらず、180 は両者の中央値近似。
- 「ブロック未指定 = gap」は false positive を生む。schema に
  `unknown` enum を追加して "情報なし" と "documented gap" を区別する
  ことが将来検討候補。

---

### 10. `identity_credential_exposure`

**定義:** 組織の identity / credential 管理成熟度が低い状態 — MFA
カバレッジ gap・PIM/PAM 不在・helpdesk authentication 未文書化 — により
access-broker・valid account abuse・vishing・BEC への曝露が上昇する。

**検出:**

```
identity_management is None
  OR mfa_coverage_percent < 95
  OR NOT pim_or_pam_deployed
  OR NOT helpdesk_authentication_documented
```

ブロック未指定（`identity_management is None`）→ trigger **fire**
（保守的: undocumented IAM 姿勢は経験的に credential abuse / vishing /
IAB 主導 initial access の baseline）。95% MFA カバレッジ threshold は
CISA Shields Up guidance / NIST SP 800-63B / CIS Controls v8 IG2 で示される
"near-universal" 水準に対応。

**出典**

- *CrowdStrike Global Threat Report 2025* — "Meanwhile, valid account
  abuse was responsible for 35%"（cloud incidents の 35%）
  （`ref/CrowdStrikeGlobalThreatReport2025.md` 284 行）; vishing growth
  "up 442% between the first and second half of 2024"（58 行）;
  access broker 広告 "increased 50% year-over-year"。
- *Mandiant M-Trends 2026* — "cloud-related compromises was voice
  phishing, at 23%, followed by third-party compromise"
  （`ref/m-trends-2026-en.md` 1609 行）。
- *IOCTA 2026 (Europol)* — Initial Access Brokers エコシステム章
  （`ref/IOCTA-2026.md` 921 行）; Scattered Spider / ShinyHunters /
  LAPSUS$ を IAB として記述（1062 行）。
- *APWG Q4 2025 Trends Report* — Fortra "tracks the identity theft
  technique known as 'business e-mail compromise'"
  （`ref/apwg_trends_report_q4_2025.md` 594 行）; phishing と impersonation
  "accounted for 86 percent of all confirmed threats"（311 行）。

**Limitations:**

- 95% MFA カバレッジ threshold は rule-of-thumb で、authoritative source
  は単一数値を規定していない。90-94% の組織は engagement 単位で analyst
  judgement を要する borderline ケース。
- Helpdesk authentication の強化は recent best practice（UNC3944 vishing
  mitigation）で標準化途上。"documented" boolean は coarse。
- BEC は trigger source というより impact magnifier の側面が強い。
  cause-side と impact-side のシグナル分離が将来 refinement 候補。
- ブロック未指定 = gap 扱いは §9 と同じ false positive risk を持つ。
  `unknown` enum 拡張も同様に適用可能。

---

## 重み付け

10 トリガーすべて対称に risk scoring に寄与する:

| 効果 | 機構 |
|------|------|
| Likelihood boost | trigger 1 件以上で `+1`、5 で cap。実装は `risk_scorer._compute_likelihood`。 |
| Intelligence-level escalation | trigger 1 件以上 + composite < 12 で `tactical → operational`。実装は `risk_scorer._recommend_level`。 |

**根拠:** NIST SP 800-37 Rev 2 は event-driven trigger 間で重み差を
付けない — 同質な再評価プロンプト集合として扱う。BEACON もこれを継承。

旧 0.x 系の非対称サブセット
（`{ot_connectivity, m_and_a, ipo_or_listing}`）は出典なき内部
ヒューリスティックであったため、0.10.0 で削除。

---

## 更新手順

1. **年次（Q1）に**最新の ENISA Threat Landscape / Verizon DBIR / IBM
   Cost of a Data Breach / CrowdStrike GTR / Mandiant M-Trends /
   Cloudflare Threat Report / IOCTA / APWG を再読する。trigger の
   primary citation が成立しなくなった、または独立 ≥2 報告に新しい
   経験的支持を持つ trigger が出現した場合は、citation 付きで改訂を
   提案する。
2. **BusinessContext スキーマ変更時には**、10 trigger すべてが依然として
   構造的検出パスを持つかを確認する。参照フィールドが削除されると、
   trigger は再配線または廃止のいずれかが必要。
3. **trigger の変更はすべて本書と `docs/triggers.md` の両方を同一
   commit で更新**し、`tests/test_element_extractor.py` の該当ケースも
   併せて更新すること。
4. **`HIGH_RISK_GEOPOLITICAL_ZONES` の改訂**は、追加・削除する国ごとに
   ref/ コーパスの具体的根拠（CrowdStrike GTR / Cloudflare 国家主体章 /
   IOCTA 地域エコシステムなど）を citation すること。集合は経験的根拠で
   定まる constant であり、規範的判断ではない。

---

## 関連

- `src/beacon/analysis/element_extractor.py:_detect_triggers` — 検出ロジック
- `src/beacon/analysis/risk_scorer.py:_compute_likelihood` /
  `_recommend_level` — 重み付け
- `schema/trigger_keywords.json` — AI / 規制 trigger のキーワード集合
- `BEACON/high-level-design.md` §5.3 — risk scoring の narrative
