# Hardening checklist — which of YOUR defenses the held tools defeat
owner: governance/rules.d/protect.json R-protect-own-targets (commons since reconcile-01; study owner: station quarantine) · status: CURRENT · date: 2026-10-16 · supersedes: work/protection/ on station quarantine · audit: python3 tools/protect/self_check.py --selftest

Read across: if you rely on the defense in column 1, column 2 says which held tool walks past it (evidence: the
cited note), column 3 says what to do. `self_check.py` covers the rows marked SC (static check on your own site).

| # | your defense | defeated by | harden with | SC |
|---|---|---|---|---|
| H1 | `navigator.webdriver` / headless-UA check | all three (camofox engine; Maxun init script; invisible_dots engine) | drop it as a gate; server-side velocity (RATE_LIMITING.md) | — |
| H2 | JS fingerprint consistency (WebGL, canvas, audio, screen) | camofox (engine-level, WebGL via virtual display), invisible_dots (engine) | treat as one weak score input; never a gate | — |
| H3 | per-IP rate limit only | camofox residential rotation | add per-account / per-email-domain / per-instrument keys | SC (429 + Retry-After seen?) |
| H4 | IP-geo vs timezone/locale mismatch | camofox (locale from proxy geo-IP) | weak score only | — |
| H5 | "one account per device" | invisible_dots (one identity per account by design) | velocity per payment instrument / phone / verified domain | — |
| H6 | email verification as proof of human | invisible_dots throwaway-mail loop | disposable-domain screening; value gated behind later verification | — |
| H7 | robots.txt as protection | Maxun (opt-in, soft-fails open when unreachable) | robots.txt for courtesy + Crawl-delay; auth for anything private | SC (robots present, Crawl-delay, no private paths listed) |
| H8 | private URLs "hidden" in sitemap | Maxun sitemap crawl | never list private/per-user URLs; auth them | SC (sitemap leak of sensitive paths) |
| H9 | markup obfuscation / rotating class names | Maxun re-records selectors | don't (hurts accessibility); protect data with auth + limits | — |
| H10 | static CAPTCHA / fixed puzzle | invisible_dots learns site playbooks | escalation-only challenges with accessible alternative | — |
| H11 | vendor bot-manager header present = protected | camofox detects vendors by header and counts challenges | verify the vendor actually challenges abusive rates on YOUR routes | SC (vendor header noted, not credited) |
| H12 | UA allow/deny lists | Maxun random UA list; camofox real Firefox UA | UA/client-hint consistency as a score; never block on UA alone | — |
| H13 | missing security headers | n/a (baseline) | HSTS, CSP, X-Content-Type-Options, frame-ancestors/X-Frame-Options, Referrer-Policy, Permissions-Policy | SC |
| H14 | session cookie without flags | n/a (baseline; persistent identities reuse cookies) | `Secure; HttpOnly; SameSite=Lax/Strict`; short idle expiry; rotate on login | SC |
| H15 | server/version banners | n/a (recon aid) | strip `Server` version, `X-Powered-By` | SC |
| H16 | forms with no CSRF token | automation replays requests | CSRF token or SameSite + origin check | SC (form without token-like hidden field) |

## Before launch
- [ ] Run `python3 tools/protect/self_check.py <your own staging URL or local build>` and fix every FAIL.
- [ ] Every row H1–H12 you rely on has its "harden with" in place, or is written down as accepted risk.
- [ ] FAIR_DISTINCTION.md accessibility acceptance test passes.
- [ ] PRIVACY_CHECKLIST.md complete.
