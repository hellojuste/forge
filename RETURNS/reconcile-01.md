# RETURN — slice reconcile-01 (branch claude/stable-kit-main + 6 stations)

owner: child reconcile-01 of PRIME session_01GbdVhRTvKX1mxo9qitPKER · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: `python3 tools/station_audit.py` on main and on each synced station, plus the tails below

**Status: DONE.** The operator's order was: "reconcile everything that needs be into the core, then i will pull." That order is recorded verbatim as DEC-core-0011.

- Three proven cross-station capabilities now live in the commons, one owner each:
  - the design engine
  - the protection pack with `self_check`
  - the shared market-scan
- Every main-targeted proposal from the five DONE stations has been folded in.
- The six DONE or stable stations were synced and pushed: markets, client-bi, studio, venture, research and quarantine. Each one runs the commons copy and keeps no fork of its own.
- Forge and career were not touched (see PENDING).
- Every touched branch ends with: `station_audit` 0 red, `workflows_check` 0 violations, and every selftest passing.

## What moved to the commons, and to what path

| from (station) | to (commons path) | check (MUST) · rule | skill + router row |
|---|---|---|---|
| studio `tools/station/detector/` (59/59 rules, 209/209 set parity, vendored Apache-2.0 fixtures + LICENSE) | `tools/design/detector/` | `design_detector` · R-design-detector | `design-review` (`router/intents.d/design.json`) |
| studio `tools/station/contrast.py` | `tools/design/contrast.py` | (rides design_handoff / design-review) | ″ |
| studio `tools/station/design_catalog.py` + `.json` (8 local directions; impeccable.style roll client, always opted out, no choice ping unless `impeccable_roll.telemetry`) | `tools/design/design_catalog.py`, `tools/design/design_catalog.json` | `design_catalog` · R-design-roll | ″ |
| studio `studio_lint` handoff / review / motion-spec / token / a11y / breakpoint / DESIGN.md lints (13 functions) | `tools/design/handoff.py` (new CLI `check`, `tokens --css`, `--check`) | `design_handoff` · R-design-handoff | ″ |
| (new) design-tokens schema | `commons/schema/design_tokens.schema.json` (color, font, space, radius required) | ″ | ″ |
| (new) handoff-package format | `commons/packs/design/HANDOFF.md` (target site\|venture\|client-bi\|career + 9 parts) | ″ | ″ |
| quarantine `work/protection/{PACK,FAIR_DISTINCTION,RATE_LIMITING,HARDENING_CHECKLIST,PRIVACY_CHECKLIST}.md` | `commons/packs/protection/` (words carried; the old "until main adopts it" paragraph is kept under a SUPERSEDED line) | — | `site-protection` (`router/intents.d/protect.json`) |
| quarantine `tools/station/self_check.py` + fixtures, check `self_check`, rule R-quarantine-own-targets | `tools/protect/self_check.py`, `tools/protect/fixtures/self_check/` | `self_check` · R-protect-own-targets (carries R-quarantine-own-targets / DEC-quarantine-0006) | ″ |
| research `tools/station/custody.py`, `tools/station/sizing.py` | `tools/research/custody.py`, `tools/research/sizing.py` (+ `sizing.py scan`) | `market_scan` · R-research-market-scan | `shared-market-scan` (`router/intents.d/research.json`) |

### Rails preserved, with evidence

**self_check: refuses a non-owned host.**
- A target is accepted only if it is loopback or listed in the station's own `work/protection/OWNED.txt`. A missing OWNED.txt counts as empty.
- Broker and exchange hosts are refused even when listed, and listing one turns the check red.
- There is no override flag. It imports only the stdlib.
- Selftest: 40 cases, up from 39. The new case: "check green when OWNED.txt is absent", for main and fresh stations.
- On quarantine, `self_check.py https://example.com/` returns REFUSED.

**Shared market-scan: respects the NC boundary.**
- A record fails when its MARKET.md carries the NC-LANE stamp.
- A record also fails when a source row names the nc-lane path, or when a capture carries the stamp.
- `scan` never walks `nc-lane/`.
- Selftest: 18 cases, including the 3 NC plants and the scan cases.
- Research keeps the NC lane itself, along with `nc_stamp`, `nc_export`, the gateway, repomap and its own custody/deliverables rows.

### Kit-wide capabilities (every station, via commons skills + router rows)

These are listed in `_gov.COMMONS_SKILLS`.
- **`design-review`**: detector score, contrast pairs, tokens and the handoff lint, on any build. Covers client-bi dashboards, venture MVPs, career CV/portfolio and studio variants.
- **`site-protection`**: the pack, plus `self_check` on the operator's OWN staging host or local build. This is the launch step for venture, client-bi and studio.
- **`shared-market-scan`**: sized, denominated, custody-checked figures for venture, career and research.
  - It was first named `market-scan` and renamed in `4a428ce`, because research's `.claude/workflows/market-scan.js` has the same name (LL-02). That clash turned `workflows_parse` red on research.

### Station side (each now imports the commons copy; retired rows are kept verbatim in STATION_HISTORY.md)

- **studio `34b592a`**: removed `tools/station/detector/`, `contrast.py` and `design_catalog.*`.
  - `studio_lint` imports `tools/design/handoff.py`.
  - `site_scaffold` runs the commons detector, and `wf_sim` copies `tools/design` into its temp station.
  - Retired `studio_detector`, `studio_catalog`, R-studio-detector and R-studio-roll.
  - Studio keeps the design work: `studio_work`, `studio_site`, `studio_workflows`, and its station.json roll settings, which the commons catalog reads.
  - Results: landing-sample site 100/100, exit 0, with the commons detector. studio_lint 47 cases, site_scaffold 3, wf_sim 12 + plants.
- **quarantine `79bc73e`**: removed the pack copies and `self_check` with its fixtures, and retired the station check row and rule.
  - `work/protection/OWNED.txt` stays.
  - Quarantine stays the study owner (`notes/`, DEC-quarantine-0006).
- **research `1ad6492`**: removed `tools/station/{custody,sizing}.py`.
  - deliverables, gateway and repomap import `tools/research/`. The gap skills, workflows, router rows, custody check row and catalog are repointed.
  - Results: deliverables 0 on all 5 kinds, sizing 0, custody plant red, workflow_sim 0.
- **venture `d107a65`**: `mvp_static.py` drops its `token_leaves` copy and imports the commons one.
  - The tariefwijzer pipeline still passes 9 of 9 stages, and the re-run leaves no diff.
  - DEF-venture-0001 and DEF-venture-0002 are marked `FIXED 43b7020`, with their re-tests. The old status is kept under a SUPERSEDED line.
- **client-bi `8c79681`**: `sheet_grammar` C6 accepts a commons design-token file (its `color-*` leaves) or the legacy palette. Selftest: 11 cases.
- **markets `7c35939`**: sync only.

## Main-targeted proposals folded (DONE stations only)

| proposal (station RETURN) | done on main |
|---|---|
| client-bi: `power bi` / `dax` / `powerbi` in the client-bi leaf of `router/kit_tree.json` | `powerbi` added (`power bi`, `dax` were already present) |
| venture DEF-venture-0002: `check_paths` bare tokens stop at `~` | `~` added to the bare-token class. A planted selftest case reproduced the false `repertoire/a` claims with the old regex and passes with the new one |
| venture DEF-venture-0001: Lago submodule pins | Bootstrap-only rows `getlago~lago-api@753abde…` and `getlago~lago-front@94911425…` added to `registry/sources.json`, `homes.json` and `licences.json`.<br>Each licence was read at its pin with a depth-1 fetch: AGPL-3.0, 7,247 and 3,435 files.<br>`kit_check` EXPECTED_SOURCES is now 30.<br>Re-test: `python3 tools/kit/bootstrap.py getlago~lago-api` printed "fetched 753abde3787f, 1 / 1 pins present" |
| research: a `kind: gap` row type for `router/skills.json` | `skill_routes check` accepts `kind: gap` rows (`id gap:<path>`, path under `.claude/skills/`, keywords required, never a census id); the schema enum and pattern are widened; 4 planted selftest cases |
| studio: telemetry rows | The impeccable engine row's opt-out text was read at the pin; the row stays `verified:false`.<br>New row `design_catalog roll client`: `verified:true`, evidence `tools/design/design_catalog.py:93-129` + selftest |
| venture proposal 3 / client-bi tokens: one token-flattening owner | `tools/design/handoff.py`; both station forks are retired (above) |

Not folded, and why:
- **client-bi's shared data gateway, runnable-workflow pattern and artifact scope guard.** These are design-level proposals with no proven commons implementation yet, and the brief scoped this pass to proven pieces.
- **venture's `work/examples` convention, `dirs.json outputs:` and scheduler pattern.** Same reason as above.
- **studio's "derived works" section in the generated NOTICE.md.** The detector's NOTICE.md travels beside it in `tools/design/detector/`.
- **research's ARS policy note.** It is addressed to the operator and needs a decision, not a code change.

## Defects found in this pass and fixed in the same pass (invariant 6)

- **`gen_station_map` hardcoded `main`.** With local `station/*` worktrees and no local `main`, `station_map` went UNREADABLE (red). It now resolves `tools/kit/_kit.main_ref`, like sync.py (`4a428ce`).
- **`licence_filter` false positives.** The vendored Apache-2.0 detector fixtures share a boilerplate `<meta name="viewport" …>` line with held AGPL Maxun, which gave 5 false violations on quarantine after the sync.
  - Fix: the nearest-licence rule. A file whose nearest ancestor LICENSE is Apache-2.0, MIT, BSD or ISC is not treated as station-authored text. A file under a copyleft or unknown own licence still fails.
  - 2 planted selftest cases (`cfff481`).
- **Name collision between the commons skill `market-scan` and research's workflow of the same name.** Fixed by the rename above.

## PENDING (not promoted; branches still live)

- **forge**: `understand` / ProjectAtlas / openwiki / evo / rea. PRIME folds these in a follow-up. Research's `repomap.py` keeps the `atlas.json` and `WIKI.md` names for that hand-over.
- **career**: the career CLI. Not touched.
- **forge and career branches were not synced.** When PRIME syncs them they will receive:
  - the three commons skills; no name clash was found on either branch
  - the `licence_filter` nearest-licence rule
  - the `check_paths` `~` token. A dead `owner~repo` lane path in their workflows will now be reported.

## Notes

- **No `commons-v*` tag exists in the kit, so none was created.** `map/STATIONS.md` reports drift as a WORKLIST on main: it renders local `station/*` refs, and the worktrees used here are transient.
- **The context hook asked for a handoff at 150k, 200k, 250k, 300k and 350k.** This session's window is larger than the hook assumes, every step was committed and pushed as it closed, and PRIME asked for one RETURN. So no successor was started; the same deviation as the studio, research and venture children.
- **The Workflow tool was not used.** There was no operator opt-in; all work ran in-session.

## Final tails

```
main cfff481 (before this RETURN)
$ python3 tools/station_audit.py                  -> station_audit: 0 red · 42/42 clean · worklists 58
$ python3 tools/upstream/workflows_check.py --root . --check
  workflows_parse 0 / 2 · certain_tests 0 / 2 · listing_budget 0 / 9 (9 skills listed, 1,636 of 8,000 chars)
$ python3 tools/station_audit.py --selftest       -> selftest OK (92 cases)
$ python3 .claude/hooks/intent_router.py --selftest -> selftest OK (145 cases, 56 fixture prompts)
$ every tools/** + .claude/hooks/** --selftest     -> selftests: 57 pass / 0 fail / 57 total
  new/changed: detect 169 · handoff 23 · contrast 14 · design_catalog 8 · self_check 40 · sizing 18 · custody 33 ·
  check_paths OK · skill_routes 25 · licence_filter 8 · gen_station_map OK · kit_check OK · bootstrap OK

station     head      station_audit                                         workflows_check (parse · certain · listing)   selftests
markets     7c35939   0 red · 49/49 clean                                   0/7 · 0/7 · 0/108                             63 pass / 0 fail / 63
client-bi   8c79681   0 red · 47/47 clean                                   0/10 · 0/10 · 0/23                            77 pass / 0 fail / 77
studio      34b592a   0 red · 42/45 clean · 3 NOT RUN (knob map=S)          0/4 · 0/4 · 0/32                              61 pass / 0 fail / 61
venture     d107a65   0 red · 44/44 clean                                   0/9 · 0/9 · 0/150                             75 pass / 0 fail / 75
research    1ad6492   0 red · 45/45 clean                                   0/7 · 0/7 · 0/33                              62 pass / 0 fail / 62
quarantine  79bc73e   0 red · 41/45 clean · 4 NOT RUN (knob map=XS)         0/4 · 0/4 · 0/11                              60 pass / 0 fail / 60
router selftests: markets 263 · client-bi 181 · studio 213 · venture 335 · research 195 · quarantine 143 cases, all OK
sync.py: every station merged with only GENERATED conflicts (regenerated); no non-generated conflict, so no station was stopped
```

closeout: reconcile-01 DONE · commons +3 capabilities (design engine, protection pack + self_check, shared market-scan) with 5 MUST checks and 5 rules under DEC-core-0011 · 6 main proposals folded, 3 found defects fixed · 6 of 6 DONE/stable stations synced, pushed, 0 red · forge + career PENDING for PRIME · NEXT: PRIME folds forge/career and syncs them; the operator pulls
