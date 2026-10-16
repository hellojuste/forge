# Fair real-user-vs-automation distinction
owner: governance/rules.d/protect.json R-protect-own-targets (commons since reconcile-01; study owner: station quarantine) · status: CURRENT · date: 2026-10-16 · supersedes: work/protection/ on station quarantine · audit: python3 tools/protect/self_check.py --selftest

## The finding that shapes everything
The held tools make browser-side "is this a bot?" signals unreliable: engine-level spoofing of navigator, WebGL,
audio, screen and WebRTC (notes/camofox-fingerprint-surfaces.md), `navigator.webdriver` forced false and generated
fingerprints (notes/maxun-robot-signals.md), persistent per-account identities (notes/invisible_dots-automation-signatures.md).
So: **the question to ask is not "is this a bot?" but "is this request doing harm, and what does it cost to let it
through?"** That question also never punishes a disabled user, because it is about effect, not about the browser.

## Never use as a block signal (they hit legitimate people, and the held tools pass them anyway)
| signal | who it hurts | does it stop the held tools? |
|---|---|---|
| no mouse movement / keyboard-only navigation | keyboard users, switch-access, screen-reader users | no — camofox humanizes the pointer |
| very fast or very regular form fill | password managers, autofill, voice dictation | partly — but autofill looks the same |
| `navigator.webdriver`, missing plugins, headless UA | nobody legit, but | no — all three hide these |
| JavaScript disabled / blocked fingerprint scripts | privacy browsers, Tor, NoScript users | no |
| VPN / datacenter / foreign IP | privacy-conscious users, travellers | no — residential proxies (camofox lib/proxy.js) |
| accessibility tree queried / ARIA-driven interaction | screen readers | no |
| visual-only CAPTCHA | blind users | weakly; the agent learns playbooks |

## Use instead (server-side, outcome-based, layered)
1. **Value-at-risk tiers.** Read-only public pages: allow everyone, rate-limit generously. Sign-up, login, password
   reset, contact form, checkout: limit and verify. Anything moving money or exposing personal data: require an
   authenticated, verified account and step-up confirmation.
2. **Velocity per durable key, not per IP.** Per account, per verified email domain, per payment instrument, per
   phone number, per destination of a message. IPs rotate (camofox), device fingerprints multiply
   (invisible_dots one-identity-per-account); these keys are expensive to multiply.
3. **Consistency checks that are about the request, not the person.** A User-Agent claiming Firefox arriving with
   Chromium client hints (`Sec-CH-UA`) is an inconsistent CLIENT (Maxun's static UA list,
   notes/maxun-robot-signals.md). Use it to raise a score, never as a sole block: some privacy extensions edit UAs.
4. **Disposable-email screening at sign-up** (invisible_dots' throwaway-mail loop). Prefer "verify later before
   anything valuable" over "refuse": a refused legit user is a lost user.
5. **Uniform-timing heuristic, score only.** Every keystroke exactly 30 ms apart (camofox default delay) is not
   human; but dictation and paste are also not "human typing". Score, never block.
6. **Challenges are an escalation, with an accessible path.** If you must challenge: offer a non-visual alternative
   (email/SMS one-time link, audio, or a human-reviewed queue). Prefer privacy-preserving proof-of-work or
   attestation tokens over puzzles; never a puzzle as the only gate.
7. **Fail soft.** A high score → slow down (delay, queue, review) before refusing. A refusal page states what
   happened and gives a contact route. Log the reason code, not the person's content.

## Accessibility acceptance test (run on every bot control before shipping)
- Complete sign-up, login and the main form using only a keyboard; with a screen reader (NVDA/VoiceOver);
  with a password manager autofilling; with JavaScript disabled where the page claims to work without it; through a
  VPN. Each must succeed or reach a human path. A control that fails any of these does not ship.
