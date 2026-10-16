---
name: site-protection
description: Before launching a site or form the operator owns: apply the protection pack and run the passive self-check on their OWN staging host or local build only.
---
# site-protection — protect what you ship, fairly (commons; owner governance/rules.d/protect.json R-protect-own-targets)

For venture, client-bi, studio and any station that ships a site. The pack is written from quarantine's study notes;
nothing here runs, installs or imitates a held tool.

## Steps
1. **Read the pack** — `commons/packs/protection/PACK.md` (index + rails), then the file for the job:
   FAIR_DISTINCTION.md (bot controls that never punish screen readers, keyboard users, VPNs or no-JS users),
   RATE_LIMITING.md (durable keys, 429 + Retry-After), HARDENING_CHECKLIST.md (H1-H16), PRIVACY_CHECKLIST.md.
2. **Own targets only** — a URL is checked only if its host is loopback or listed by the OPERATOR in this station's
   work/protection/OWNED.txt (one host per line; absent = empty). Never add a host the operator has not said is theirs.
   Broker, exchange and trading hosts are refused even when listed. There is no override.
3. **Run** — `python3 tools/protect/self_check.py <local build dir | http://localhost:PORT | owned staging URL>`.
   Passive: one GET of page, robots.txt, sitemap.xml and a burst of at most 5 GETs; honest User-Agent; no forms.
   Exit 0 no FAIL · 1 FAIL rows · 3 REFUSED (not yours) · 2 unreachable.
4. **Fix every FAIL** before launch; WARN rows go to the launch checklist with a reason.

## Report shape
`site-protection: <target> · self_check <fails> FAIL / <warns> WARN of <rows> rows · pack rows applied: <ids>`
A REFUSED result is reported as refused, never worked around.
