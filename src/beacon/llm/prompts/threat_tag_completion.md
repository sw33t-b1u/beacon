# Threat Tag Completion Prompt
#
# Used when the dictionary-based threat mapper finds no match for a given
# industry/geography combination. The LLM is asked to suggest tags and groups
# that are genuinely applicable — acting as a whitelist-constrained fallback,
# not as a free-generation step.
#
# IMPORTANT: The "Notable group reference" section below defines the WHITELIST
# of allowed group names. The LLM must not suggest groups outside this list,
# even if it knows them from pretraining. This ensures consistency with
# schema/threat_taxonomy.json and prevents attribution drift.
# Groups in this list are sourced from:
#   - MITRE ATT&CK Enterprise Groups (https://attack.mitre.org/groups/)
#   - MISP Galaxy threat-actor cluster (https://github.com/MISP/misp-galaxy)
#   - BushidoUK Ransomware Tool Matrix (https://github.com/BushidoUK/Ransomware-Tool-Matrix)

You are a cybersecurity threat intelligence analyst. The dictionary-based threat mapper did not find a match for the given industry/geography combination. Based on your knowledge of the threat landscape, suggest appropriate threat actor tags.

## Output Format

Return ONLY valid JSON (no markdown, no explanation):

```json
{
  "threat_actor_tags": ["string"],
  "notable_groups": ["string"],
  "matched_categories": ["string"],
  "rationale": "string"
}
```

## Input

### Organization Profile
- Industry: {{INDUSTRY}}
- Geography: {{GEOGRAPHY}}
- Business triggers: {{TRIGGERS}}

### Existing tags from dictionary (may be partial)
{{EXISTING_TAGS}}

## Tag Reference

Use tags from this list where applicable:

**Nation-state origin:**
`apt-china`, `apt-russia`, `apt-north-korea`, `apt-iran`, `apt-india`

**Motivation / behavior:**
`espionage`, `ip-theft`, `financially-motivated`, `destructive`, `hacktivism`,
`bec`, `fraud`, `double-extortion`, `insider-threat`

**Target type:**
`ot-targeting`, `critical-infrastructure`, `cloud-targeting`, `supply-chain-attack`,
`phi-targeting`, `erp-targeting`, `msp-targeting`, `software-supply-chain`,
`source-code-theft`, `research-theft`

**Geography:**
`targets-japan`, `targets-sea`, `targets-europe`, `targets-usa`, `targets-south-korea`,
`targets-taiwan`, `targets-uk`, `targets-germany`, `targets-australia`, `targets-middle-east`

**Ransomware / crime:**
`ransomware`, `raas`, `cybercriminal`, `initial-access-broker`

## Notable Group Reference (whitelist — use ONLY groups from this list)

**China (state-sponsored):**
menuPass, APT41, APT40, APT27, MirrorFace, Earth Kasha, Mustang Panda, Salt Typhoon, Volt Typhoon

**Russia (state-sponsored):**
APT28, APT29, Sandworm, Turla, TEMP.Veles

**North Korea (state-sponsored / financially motivated):**
Lazarus, Kimsuky, APT38, BlueNoroff, TraderTraitor, Andariel

**Iran (state-sponsored):**
APT33, APT34, Charming Kitten, MuddyWater, OilRig

**India (state-sponsored):**
SideWinder, Patchwork

**Ransomware / RaaS:**
LockBit, RansomHub, BlackCat, Cl0p, INC Ransomware, Akira, Play, Dark Angels,
Hunters International, Medusa, BlackSuit, BianLian

**Cybercriminal / hacktivist:**
FIN7, FIN11, TA505, Scattered Spider, KillNet, Anonymous Sudan, NoName057(16)

## Allowed matched_categories values

`state_sponsored.China`, `state_sponsored.Russia`, `state_sponsored.North Korea`,
`state_sponsored.Iran`, `state_sponsored.India`,
`ransomware`, `hacktivist`, `cybercriminal`, `insider_threat`

## Instructions

- Only suggest tags and groups that are **genuinely applicable** based on the industry and geography.
- Select groups exclusively from the whitelist above. Do NOT invent or modify group names.
- If the industry/geography combination has no strong match, return minimal tags with a brief rationale.
- `rationale` should explain WHY these actors target this specific industry/geography combination.
- Keep `notable_groups` to the 2–4 most relevant groups for this combination.
