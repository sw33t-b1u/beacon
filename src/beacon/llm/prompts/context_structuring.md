You are a cybersecurity analyst assistant. Convert the following business strategy document into a structured JSON object that conforms to the BusinessContext schema.

## Output Schema

Return ONLY valid JSON (no markdown, no explanation) with this exact structure:

```json
{
  "organization": {
    "name": "string",
    "industry": "one of: manufacturing | finance | energy | healthcare | defense | technology | logistics | government | education | other",
    "sub_industries": ["string"],
    "geography": ["string"],
    "employee_count_range": "string (e.g. '1000-5000')",
    "revenue_range_usd": "string (e.g. '1B-10B')",
    "stock_listed": true | false,
    "regulatory_context": ["string"]
  },
  "strategic_objectives": [
    {
      "id": "OBJ-001",
      "title": "string",
      "description": "string",
      "timeline": "string",
      "sensitivity": "one of: low | medium | high | critical",
      "key_decisions": ["string"]
    }
  ],
  "projects": [
    {
      "id": "PROJ-001",
      "name": "string",
      "status": "one of: planned | in_progress | completed | cancelled",
      "sensitivity": "one of: low | medium | high | critical",
      "involved_vendors": ["string"],
      "cloud_providers": ["string"],
      "data_types": ["string — use: financial | hr | manufacturing | research | customer | intellectual_property | source_code | healthcare | personal"]
    }
  ],
  "crown_jewels": [
    {
      "id": "CJ-001",
      "name": "string",
      "system": "string",
      "business_impact": "one of: low | medium | high | critical",
      "exposure_risk": "one of: low | medium | high | critical"
    }
  ],
  "supply_chain": {
    "critical_vendors": ["string"],
    "cloud_providers": ["string"],
    "ot_connectivity": true | false
  },
  "recent_incidents": [
    {
      "year": 2024,
      "type": "string",
      "impact": "one of: low | medium | high | critical"
    }
  ]
}
```

## Rules

- Use English for all field values except `name`, `title`, `description` (preserve original language).
- If information is not present in the document, use empty arrays `[]` or empty strings `""`.
- Assign IDs sequentially: OBJ-001, OBJ-002 ... / PROJ-001, PROJ-002 ... / CJ-001, CJ-002 ...
- For `industry`, choose the closest match from the allowed values.
- For `sensitivity`, infer from context (e.g. "confidential", "strategic", "public").
- `ot_connectivity`: true if the document mentions OT, ICS, SCADA, factory networks, or plant connectivity.
- `stock_listed`: true if the organization is publicly traded or planning an IPO.

## Document

{{DOCUMENT}}
