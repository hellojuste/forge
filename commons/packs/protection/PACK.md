# protection — the defensive pack (commons; studied and owned for evidence by station quarantine)
owner: governance/rules.d/protect.json R-protect-own-targets (commons since reconcile-01; study owner: station quarantine) · status: CURRENT · date: 2026-10-16 · supersedes: work/protection/ on station quarantine · audit: python3 tools/protect/self_check.py --selftest

Operator, verbatim (design/QUEUE.md Q4): "i genuinely just dont want anyone - especially myself - to be exposed to
unsafe behavior ... id have to be really irresponsible to do a venture and not live up to my own standards."

What this is: what the operator needs to PROTECT a site or form they ship (venture, client-bi, studio) against the
three automation tools held in quarantine — written from the study notes, containing no evasion code and no step that
drives any held tool. Evidence for every "this tool defeats X" claim is a cited study note under notes/ on station quarantine.

| file | answers | use it when |
|---|---|---|
| `FAIR_DISTINCTION.md` | how to tell automation from people without punishing screen readers, keyboard users, password managers, privacy browsers | designing any bot/abuse control |
| `RATE_LIMITING.md` | limits and abuse-handling patterns that hold when IPs rotate and fingerprints look human | shipping any endpoint, form or login |
| `HARDENING_CHECKLIST.md` | which of your OWN defenses camofox / Maxun / invisible_dots defeat, and what to do instead | before launch; after any defense change |
| `PRIVACY_CHECKLIST.md` | data-protection checklist for a private venture (minimise, retain, protect, disclose) | any site that collects personal data |
| `tools/protect/self_check.py` | static exposure report for a site YOU OWN (headers, robots, rate-limit and bot-handling signals) | before launch, on staging or your own local build |

## Rails (binding; rule R-protect-own-targets, carried from R-quarantine-own-targets, enforced in code: see tools/protect/self_check.py)
1. **Evasion tooling never leaves quarantine.** This pack holds no code from the held trees and no instructions to
   run them. Nothing here imports, installs or launches camofox, Maxun or invisible_dots.
2. **Own targets only.** `self_check.py` checks a site the operator owns: localhost, a local directory, or a host the
   operator lists in the station's own work/protection/OWNED.txt (one per station, since the operator's hosts differ
   per venture; absent = empty). Anything else is refused by default (`--selftest` proves it).
3. **No broker/exchange accounts.** Anything that touches a broker, exchange or trading account is out of scope:
   `self_check.py` refuses such hosts even when listed as owned, and this pack gives no advice for them.
4. **Self-check is passive.** One GET of the page, one of `/robots.txt`, one HEAD probe, and a short bounded burst of
   at most 5 GETs to see whether a rate limit answers — no spoofed identity, no fingerprint evasion, no form
   submission.
5. **Fair first.** No control in this pack may block a user for using assistive technology, a privacy browser, a VPN,
   or JavaScript disabled, without a human path through (see FAIR_DISTINCTION.md).

## For venture, client-bi, studio (and every station)
This pack and `tools/protect/self_check.py` are commons: every station has them. Skill `site-protection` routes here.
Launch step for venture, client-bi and studio: run `python3 tools/protect/self_check.py <staging URL or local build>`
on your OWN staging host or local build only, and fix every FAIL before launch.
SUPERSEDED 2026-10-16 (reconcile-01: main adopted the pack as commons/packs/protection and the tool as tools/protect/):
"Until main adopts it, read this pack on claude/stable-kit-quarantine (read only — nothing is copied out of
quarantine, per STATION.md#Boundary). The proposal for main is in RETURNS/defensive.md." (backticks dropped so the quote is not a live path claim)
