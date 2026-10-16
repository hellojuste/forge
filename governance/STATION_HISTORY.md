# STATION_HISTORY — verbatim destination for superseded forge hot-path text

## 2026-10-16 · moved to the commons by reconcile-01 wave 2 (DEC-core-0012) · understand.py and its router row

SUPERSEDED 2026-10-16: tools/station/understand.py -> tools/kit/understand.py (rule R-kit-understand, check understand,
router row understand in router/intents.d/understand.json, memory + mcp_optin defaults in commons/defaults.json, SessionStart
MEMORY line from tools/brain.py). setup_tool.py and its tool table stay here: forge installs ProjectAtlas and openwiki for
every station. station.json memory.targets ["kit"] and mcp_optin.enabled [] stay forge's own settings.

Retired station router row (verbatim):
```json
{
 "name": "understand",
 "description": "decipher and remember any target (path, owner~repo pin, or the kit): ProjectAtlas index + grounded openwiki wiki in one memory outside the station",
 "contributed_by": "station",
 "router": {
  "keywords": [
   "understand this repo",
   "understand this codebase",
   "index this repo",
   "code map",
   "atlas index",
   "memory for",
   "decipher",
   "understand.py"
  ],
  "phrases": [],
  "path_patterns": [
   "tools/station/understand.py"
  ],
  "file_types": [],
  "patterns": [],
  "first_move": {
   "args": "<path|owner~repo|kit> [--atlas] [--wiki] [--refresh]",
   "inline_gather": "python3 tools/station/understand.py --list"
  },
  "claims": [
   "understand this repo",
   "understand this codebase",
   "index this repo",
   "code map",
   "atlas index",
   "memory for",
   "decipher",
   "understand.py"
  ]
 }
}
```
