# Privacy / data-protection checklist — private venture
owner: governance/rules.d/protect.json R-protect-own-targets (commons since reconcile-01; study owner: station quarantine) · status: CURRENT · date: 2026-10-16 · supersedes: work/protection/ on station quarantine · audit: python3 tools/protect/self_check.py --selftest

Scope: a private venture's site or form that collects personal data (names, emails, phone, messages, payment via a
processor). The repo is private to protect data; this list keeps the shipped site to the same standard. Written to
fit GDPR/UK-GDPR-style principles; it is a checklist, not legal advice — a jurisdiction-specific review is the
operator's call.

## Collect
- [ ] Every field has a stated purpose; drop fields without one (minimisation).
- [ ] Lawful basis named per purpose (contract, consent, legitimate interest); consent is opt-in and separate.
- [ ] No third-party trackers before consent; analytics configured cookieless or consented.
- [ ] Payment data goes straight to the processor (hosted fields/checkout); the site never sees card numbers.
- [ ] Anti-abuse signals (FAIR_DISTINCTION.md) use the minimum: hashed keys, reason codes, no fingerprint store.

## Store
- [ ] Encryption in transit (HTTPS only, HSTS) and at rest (managed DB encryption; backups too).
- [ ] Secrets in the platform's secret store, never in the repo; `.env` holds names only (kit rule).
- [ ] Least-privilege access: who/what can read personal data, written down; DB roles per service.
- [ ] Row-level security or per-tenant scoping where one database serves several clients (client-bi).

## Keep and delete
- [ ] Retention per data type (e.g. abuse logs 30 days, full IPs 30 days then truncated, inactive accounts N months).
- [ ] Deletion actually deletes (including derived copies and exports); backups age out on schedule.
- [ ] Data-subject requests (access, correction, deletion, export) have an owner and a ≤ 30-day path.

## Disclose
- [ ] Privacy notice: who you are, what you collect, why, how long, who processes it (list processors), rights, contact.
- [ ] Processor agreements (DPA) with each processor; note any transfer outside the region.
- [ ] Cookie notice matches what is actually set (self_check lists Set-Cookie names it saw).

## Prevent and respond
- [ ] Rate limits on login, reset, sign-up, export (RATE_LIMITING.md) — scraping is a data-protection risk.
- [ ] Error pages and APIs never echo personal data or stack traces; `Server`/`X-Powered-By` stripped.
- [ ] Breach plan: who decides, notify within 72 h where required, a contact list kept offline.
- [ ] Review this list at each release that adds a field, processor or integration.
