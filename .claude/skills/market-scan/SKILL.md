---
name: market-scan
description: Size a market or scan competitors from public sources with every figure sourced, denominated and re-checked by the shared sizing + custody tools (venture, career, research).
---
# market-scan — sized claims with custody, any station (commons; owner governance/rules.d/research.json R-research-market-scan)

Research owns the method depth (and the NC lane); this skill is the shared floor so venture decisions and career
targeting use numbers that can be re-derived.

## Steps
1. **Record** — `python3 tools/research/sizing.py init --dir work/markets/<slug> --market "<m>" --geography <G> --as-of YYYY-MM`
   writes MARKET.md, sources.json, claims.json, sizing.json and a DRAFT marker (fails until filled).
2. **Sources** — capture each public source (the research station's gateway, or by hand) and register it:
   `python3 tools/research/custody.py add-source --dir <d> --locator <url> --file <capture> --used`.
   Respect robots.txt and terms; one fetch per need, no polling.
3. **Figures** — in sizing.json give each figure unit, geography, as_of, approach (top-down AND bottom-up),
   arithmetic, grounds quoting the source's own number, and a denominator {n, population}. A figure you cannot
   source is `UNSOURCED`: shown, never summed. Methods: market-sizing / competitor-analysis / market-segments where
   the station routes them.
4. **Check** — `python3 tools/research/sizing.py check --dir <d>` (re-hashes captures, re-finds every quote, flags
   uncited lines), then remove DRAFT. The audit row `market_scan` checks every work/**/sizing.json.

## NC boundary (hard)
Nothing from the CC BY-NC lane feeds a market-scan: a source naming the nc-lane path or carrying the NC-LANE stamp,
or a stamped MARKET.md, fails the check. NC work stays in station research.
