# Rate limiting and abuse handling
owner: governance/rules.d/protect.json R-protect-own-targets (commons since reconcile-01; study owner: station quarantine) · status: CURRENT · date: 2026-10-16 · supersedes: work/protection/ on station quarantine · audit: python3 tools/protect/self_check.py --selftest

## Why per-IP alone fails here
camofox rotates residential sessions with country/state/city targeting (notes/camofox-fingerprint-surfaces.md);
Maxun runs 5 concurrent workers by default (notes/maxun-robot-signals.md). A per-IP limit sees many ordinary home
addresses each under the line. Keep per-IP limits (they stop the naive and cost nothing) but layer durable keys.

## Pattern table (every limit names its key, window and response)
| surface | key(s) | starting limit (tune from logs) | response when exceeded |
|---|---|---|---|
| public pages | IP; /24 or /48 prefix | 120 req / 1 min per IP; 1,200 / 1 min per prefix | `429` + `Retry-After` |
| search / listing APIs | IP + session; API key | 30 req / 1 min per session | `429` + `Retry-After`; cap page size and page depth |
| sign-up | IP prefix; email domain; device cookie | 5 / 1 h per prefix; 20 / 1 h per email domain (disposable domains: verify-first) | queue for verification, not a hard refusal |
| login | account; IP | 5 failures / 15 min per account → step-up; 50 failures / 15 min per IP | step-up (email link), lockout only after step-up fails; never reveal whether the account exists |
| password reset | account; IP | 3 / 1 h per account | same response whether or not the account exists |
| contact / message forms | IP; destination; content hash | 3 / 10 min per IP; identical content 1 / 1 day | accept-and-drop duplicates silently |
| exports / bulk data | account | 10 / 1 day; row cap per export | `429`; alert the operator above 3× baseline |

Algorithm: token bucket or sliding window (Redis `INCR`+`EXPIRE`, or the platform's built-in limiter). Return
`429 Too Many Requests` with `Retry-After`, and expose `RateLimit-Limit` / `RateLimit-Remaining` / `RateLimit-Reset`
(IETF RateLimit headers) on APIs so honest clients back off. `self_check.py` looks for these.

## Abuse handling
- **Cap the shape, not only the rate.** Max page size, max pagination depth, no unbounded `?limit=`. Maxun's
  `scrapeList` paginates until done — a depth cap ends it fairly for everyone.
- **Don't publish what you don't want harvested.** Maxun crawls `/sitemap.xml` and follows links; keep private,
  per-user and draft URLs out of sitemaps and behind auth. robots.txt with `Crawl-delay` is honoured by Maxun when
  present (polite crawlers obey) but it is never access control.
- **Authenticate data, not pages.** Anything you would mind seeing in someone else's spreadsheet belongs behind
  login + per-account limits. Obfuscating markup only hurts accessibility; Maxun keys off selectors but re-records.
- **Honeypot fields, accessibly.** A hidden field must be `aria-hidden="true"` and `tabindex="-1"` with an
  off-screen label saying "leave empty", so screen readers and keyboards never reach it. Score, never block on it alone.
- **Log for abuse review, minimally.** Reason code, key hashed (HMAC with a server secret), timestamp, route. No
  request bodies, no full IPs beyond 30 days (PRIVACY_CHECKLIST.md).
- **Kill switch.** One config flag per surface to tighten limits ×10 during an incident without a deploy.
