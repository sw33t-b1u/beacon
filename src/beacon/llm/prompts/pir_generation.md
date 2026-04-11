You are a senior threat intelligence analyst. Improve the Priority Intelligence Requirement (PIR) text fields based on the provided business context and threat analysis results.

## Task

Given the structured analysis results below, generate improved versions of three PIR fields:
1. `description` — a concise, actionable PIR statement (1–2 sentences, Japanese OK)
2. `rationale` — explains WHY this PIR is important for this specific organization (2–3 sentences, Japanese OK)
3. `collection_focus` — a list of 3–5 specific intelligence collection priorities (Japanese OK)

## Output Format

Return ONLY valid JSON (no markdown, no explanation):

```json
{
  "description": "string",
  "rationale": "string",
  "collection_focus": ["string", "string", "string"]
}
```

## Analysis Results

### Organization
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

### Matched Threat Actors
- Categories: {{MATCHED_CATEGORIES}}
- Notable groups: {{NOTABLE_GROUPS}}
- Threat tags: {{THREAT_TAGS}}

### Risk Score
- Likelihood: {{LIKELIHOOD}} / 5
- Impact: {{IMPACT}} / 5
- Composite: {{COMPOSITE}} / 25
- Intelligence level: {{INTELLIGENCE_LEVEL}}

### Active Business Triggers
{{TRIGGERS}}

### Draft PIR (dictionary-based, to be improved)
- description: "{{DRAFT_DESCRIPTION}}"
- rationale: "{{DRAFT_RATIONALE}}"
- collection_focus: {{DRAFT_COLLECTION_FOCUS}}

## Instructions

- **Scope**: The PIR is for the organizational unit specified in "Organizational scope". If it is a department or team (not "entire company"), all fields must reflect that unit's context — do NOT broaden scope to the whole company.
- Make the description specific to this unit's context (mention industry + organizational scope + geography + key asset type or system).
- The rationale should explain the threat actor motivation and why this specific unit is a target (e.g., the data it holds, critical systems it operates, supply chain role, decisions it makes).
- If Critical Assets include supply-chain-connected systems (supply_chain field non-empty), reference the supply chain risk in the rationale.
- Collection focus items should be concrete and actionable (specific group names, CVEs, campaigns, system names from Critical Assets, data types).
- Do NOT fabricate group names or TTPs not present in the analysis results.
- Preserve or improve the draft — do not reduce specificity.
