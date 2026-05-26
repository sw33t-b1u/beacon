# 外部引用・ライセンスインベントリ

本ドキュメントは BEACON が使用するすべての外部データソース、そのライセンス条件、
および BEACON での具体的な使用方法を列挙する。Initiative F の決定記録（2026-05-23）に
より、メンテナンスが義務付けられている。

---

## MITRE ATT&CK Enterprise

| 属性 | 詳細 |
|---|---|
| バージョン | 19.1（2026-05-23 バンドル取得）|
| ライセンス | MITRE ATT&CK 利用規約 |
| 正規 URL | https://attack.mitre.org/ |
| バンドル URL | https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json |

**BEACON での使用方法:**
`scripts/derive_source_groups.py` は導出時に STIX 2.1 バンドルを読み込み、
`intrusion-set` の外部参照を抽出して `schema/source_attack_groups.derived.json` を生成する
— `source_name` 文字列を ATT&CK グループ ID に対応付ける決定論的マッピング。
この導出済み JSON が BEACON リポジトリにコミットされる唯一の ATT&CK 由来成果物。
53 MB のバンドル自体はコピーされない。

`schema/content_ja.json` の `sources[].evidence_attack_groups` フィールドは、
`schema/source_aliases.json` 経由で導出済み JSON から生成される;
これらには ATT&CK テキストではなく ATT&CK グループ ID が参照として含まれる。

**必要な帰属表記（MITRE ATT&CK 利用規約）:**
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

| 属性 | 詳細 |
|---|---|
| バージョン | 最新版（GitHub 配布）|
| ライセンス | Intel 471 CU-GIR Framework ライセンス（独自）|
| 正規 URL | https://github.com/intel471/CU-GIR |
| STIX JSON | 上記リポジトリ内の `STIX/Current/intel471_cu-gir.json` |

**ライセンス概要（Intel 471 CU-GIR Framework ライセンス）:**
本ライセンスは Framework の複製、二次著作物の作成、公開表示、配布に対して
ロイヤリティフリー、永続的、世界的なライセンスを付与する。ただし以下が条件:
- (a) すべての所有権表示および著作権表示を保持すること。
- (b) Framework を競合する CTI 製品またはサービスの開発に使用しないこと（BEACON はオープンソースの PIR 定義ツールであり、CTI フィードベンダーではなく、Intel 471 の TITAN プラットフォームや地下監視サービスと競合しない）。

**BEACON での使用方法:**
GIR の 10 進数識別子（例: `6.1.3.1`）およびカテゴリ名は、分類参照として
`schema/content_ja.json` の `intelligence_requirements[].gir_id` エントリで使用される。
BEACON 内の説明および EEI テキストは BEACON 著者が独自に作成したものであり、
CU-GIR のテキストを複製していない。

**必要な帰属表記:**
> CU-GIR Framework by Intel 471, Inc.
> Licensed under the Intel 471 CU-GIR Framework License.
> Source: https://github.com/intel471/CU-GIR

---

## Verizon Data Breach Investigations Report（DBIR）

| 属性 | 詳細 |
|---|---|
| 使用版 | 2025 年版 |
| ライセンス | Creative Commons Attribution-NonCommercial-ShareAlike 4.0（CC BY-NC-SA 4.0）|
| 正規 URL | https://www.verizon.com/business/resources/reports/dbir/ |

**BEACON での使用方法:**
`schema/content_ja.json` の `trigger_actions` フィールドにおける統計引用
（例: 「サードパーティ侵害事例 (Verizon DBIR 2025: 30%)」）。原文テキストは複製しない;
帰属明記の上で統計のみを引用する。

**必要な帰属表記:** 「Verizon 2025 Data Breach Investigations Report.」

---

## IBM Cost of a Data Breach Report

| 属性 | 詳細 |
|---|---|
| 使用版 | 2025 年版 |
| ライセンス | IBM 独自（引用目的の非独占的使用）|
| 正規 URL | https://www.ibm.com/reports/data-breach |

**BEACON での使用方法:**
`schema/content_ja.json` の `trigger_actions` における統計引用
（`ai_adoption_exposure`: 「IBM CoDB 2025」）。原文テキストは複製しない。

**必要な帰属表記:** 「IBM Cost of a Data Breach Report 2025.」

---

## NIST 特別刊行物（Special Publications）

| 属性 | 詳細 |
|---|---|
| 発行者 | 米国国立標準技術研究所（商務省）|
| ライセンス | 米国政府著作物 — 17 USC §105 によりパブリックドメイン |
| 引用ポリシー | 原文引用は自由に可; SP 番号による帰属表記が標準的な形式 |

**BEACON での各 SP の使用方法:**

| SP | 使用箇所 | 目的 |
|---|---|---|
| SP 800-30r1 | `src/beacon/analysis/actor_triage.py`（docstring）| アドバーサリーの能力・意図評価テーブル D-3 / D-4 |
| SP 800-37r2 | `src/beacon/analysis/risk_scorer.py`（コメント）; `docs/data-model.ja.md` | 戦術→運用レベルへのプロモーションのためのイベント駆動トリガーフレームワーク |
| SP 800-53 | `docs/context_template.ja.md` | AC-2 / AC-3 / IA-2 / IA-4 アクセス制御フレームワーク |
| SP 800-82r3 | `src/beacon/analysis/element_extractor.py`（コメント）| IT/OT 収束トリガーのための ICS/OT セキュリティガイダンス参照 |
| SP 800-161r1 | `src/beacon/analysis/element_extractor.py`（コメント）| サプライチェーンリスク管理の参考文献 |
| SP 800-207 | `docs/context_template.ja.md` | ゼロトラストアーキテクチャの参考文献 |

**必要な帰属表記:** 標準的な NIST 引用形式（例: 「NIST SP 800-61r3 §2.1、2025 年 4 月」）。著作権表示は不要。

---

## MITRE Cyber Prep / サイバー脅威レベル評価

| 属性 | 詳細 |
|---|---|
| 著者 | Sergio Bodeau, Jenn Fabius-Greene, Rich Graubart |
| 発行者 | The MITRE Corporation |
| タイトル | *"How Do You Assess Your Organization's Cyber Threat Level?"* |
| ライセンス | © The MITRE Corporation. All rights reserved（学術的フェアユースのみ — 帰属明記の上で短い引用）|

**BEACON での使用方法:**
`src/beacon/analysis/actor_triage.py` の `Likelihood = Intent × Capability × Opportunity`
計算式の方法論的基盤。Cyber Prep は脅威を *capability（能力）、intent（意図）、targeting（標的化）* の観点から定義しており、BEACON の `Opportunity` 要因は Cyber Prep の `Targeting` にマッピングされる。3 要素の定義の短い原文引用が actor_triage.py の docstring に学術引用として含まれている（フェアユース; 論文テキストの大量複製は行わない）。

この引用は Initiative G の `ir_observed_capability` 要因の根拠でもある:
Cyber Prep は Capability を「knowledge（知識）」を含むと定義しており、
過去の攻撃の IR 観測がこの知識シグナルを直接提供する。

**必要な帰属表記:** 「Bodeau, Fabius-Greene, Graubart. 'How Do You Assess Your Organization's Cyber Threat Level?' The MITRE Corporation.」インライン学術引用で可; 論文テキストを大量に複製してはならない。

---

## SANS Internet Storm Center / Reading Room

| 属性 | 詳細 |
|---|---|
| 発行者 | SANS Institute |
| ライセンス | SANS フェアユースガイドラインに従い引用可 |

**BEACON での使用方法:**
`src/beacon/analysis/actor_triage.py` の docstring で引用されている
SANS I-O-C（Intent / Opportunity / Capability）アクタートリアージの 3 要素の出典。
帰属明記の上で短い原文引用。

---

## その他の年次脅威レポート

以下のレポートは BEACON における統計引用の参照として使用されている。
2026-05-23 ポリシーに従い、これらの独自レポートの原文テキストは
コミット済みの BEACON 成果物に複製しない;
明示的な帰属表記（`source_name (year): statistic`）を付けた短い統計引用のみを使用し、
原文の長い引用よりもパラフレーズを優先する。

| レポート | 発行者 | ライセンスの概要 |
|---|---|---|
| CrowdStrike Global Threat Report 2025 | CrowdStrike | 独自（引用可）|
| Mandiant M-Trends 2026 | Google / Mandiant | 独自（引用可）|
| ENISA Threat Landscape 2025 | ENISA | CC BY 4.0 |
| ENISA Public Administration Threat Landscape 2024 | ENISA | CC BY 4.0 |
| ENISA Finance Threat Landscape 2024 | ENISA | CC BY 4.0 |
| Dragos OT Cybersecurity Report 2026 | Dragos | 独自（引用可）|
| Cloudflare 2026 Threat Report | Cloudflare | 独自（引用可）|
| APWG eCrime Trends Q4 2025 | APWG | 独自 |
| IOCTA 2026 | Europol | 独自（通常は帰属明記で公開）|
| TrendMicro 2026 Predictions | Trend Micro | 独自（引用可）|
| CYBER ASP Cyber Threat Assessment 2025/26 | CYBER ASP | レポートを参照 |
| AI Safety Report 2026 | International AI Safety Initiative | おそらく帰属明記でオープン |

---

## メンテナンス

新しい外部参照が Committed BEACON 成果物に追加される際は、マージ前に
本ドキュメントに行を追加すること。ライセンスが配布出力への帰属テキストの
掲載を要求する場合は、`src/beacon/generator/report_builder.py` の
フッター生成部分に追加すること。
