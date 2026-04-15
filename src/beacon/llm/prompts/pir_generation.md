You are a senior threat intelligence analyst. Sharpen ONE narrow Priority Intelligence Requirement (PIR) for the cluster described below.

A PIR is ONE focused decision point, answerable in 3–5 sentences (Who / What / When / Why + recommended action). **Do NOT broaden scope** beyond the cluster's threat family and asset focus. Do NOT aggregate across families.

## Task

Given the cluster context below, produce improved versions of four PIR fields:

1. `description` — phrased as a **question** (1–2 sentences, Japanese OK) that the leader needs answered. Must reference the specific threat family and asset focus; must not list unrelated threats.
2. `rationale` — WHY this specific unit is a worthwhile target for this threat family (2–3 sentences, Japanese OK). Reference the relevant crown jewel or critical asset when possible.
3. `collection_focus` — 3–5 concrete, actionable collection priorities scoped to this cluster (Japanese OK).
4. `recommended_action` — 1 sentence (Japanese OK): what the leader must decide or do.

## Output Format

Return ONLY valid JSON (no markdown, no explanation):

```json
{
  "description": "string",
  "rationale": "string",
  "collection_focus": ["string", "string", "string"],
  "recommended_action": "string"
}
```

## Cluster (this PIR's narrow scope — DO NOT broaden)

- Decision point: {{DECISION_POINT}}
- Threat family: {{CLUSTER_THREAT_FAMILY}}
- Threat actor tags (scoped): {{CLUSTER_THREAT_TAGS}}
- Notable groups (scoped): {{CLUSTER_NOTABLE_GROUPS}}
- Asset focus (scoped): {{CLUSTER_ASSET_TAGS}}

## Organization

- Industry: {{INDUSTRY}}
- Organizational scope: {{ORG_UNIT}}
- Geography: {{GEOGRAPHY}}
- Regulatory context: {{REGULATORY}}

### Crown Jewels (high-value data/IP assets)
{{CROWN_JEWELS}}

### Critical Assets (key systems and infrastructure)
{{CRITICAL_ASSETS}}

### Data and Supply Chain
- Data types handled: {{DATA_TYPES}}
- Critical vendors / supply chain: {{ACTIVE_VENDORS}}

### Risk Score
- Likelihood: {{LIKELIHOOD}} / 5
- Impact: {{IMPACT}} / 5
- Composite: {{COMPOSITE}} / 25
- Intelligence level: {{INTELLIGENCE_LEVEL}}

### Active Business Triggers
{{TRIGGERS}}

### Draft PIR (dictionary-based — improve, do not reduce specificity)
- description: "{{DRAFT_DESCRIPTION}}"
- rationale: "{{DRAFT_RATIONALE}}"
- collection_focus: {{DRAFT_COLLECTION_FOCUS}}
- recommended_action: "{{DRAFT_RECOMMENDED_ACTION}}"

## Instructions

- **Scope is fixed.** Use only the cluster's threat family, scoped tags, and asset focus. If you mention threats outside that scope, you are wrong.
- The `description` must be a question — not a statement. Include the threat family + the asset focus + the org unit.
- The `rationale` must explain why THIS unit holding THESE assets is targeted by THIS family — not a generic industry rationale.
- Reference only crown jewels / critical assets whose nature fits the cluster's asset focus. Do not list every CJ/CA.
- `collection_focus` items should be concrete (group names, CVEs, system names, campaigns). 3–5 items, each one line.
- `recommended_action` is one sentence — a decision the leader can act on.
- Do NOT fabricate group names, TTPs, or CVEs not present in the provided data.
- Preserve or improve the drafts; do not reduce specificity.
