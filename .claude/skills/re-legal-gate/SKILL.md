---
name: re-legal-gate
description: Before any REA run, record the target's owner, licence, your right to analyse it and the jurisdiction note from REA's DISCLAIMER.md; refuse third-party proprietary targets without a stated right.
---
# re-legal-gate — reverse engineering only with a recorded right (station forge; gap skill, invocable only)

REA's own DISCLAIMER.md (`repertoire/morluto~rea/DISCLAIMER.md`, read as data) puts authorization and compliance
on the user and lists uses it does not support (DRM/licence-check circumvention, cheats, access-control bypass,
copying proprietary code). This skill writes that decision down before the first REA command.

## Do
1. Identify the target exactly: path or package, version, sha256 of the artifact.
2. Record in `work/re/legal_gate.json` (`{"rows": [...]}`) a row:
   `{"id": "RE-GATE-nnnn", "target": "<artifact + sha256>", "owner": "self|operator|<third party>",
   "licence": "<licence or proprietary|unknown>", "right": "own|authorized|open-source-licence|interoperability-statute|public-domain|",
   "right_evidence": "<authorization letter, licence clause, statute + article>", "jurisdiction_note": "<where you are;
   DISCLAIMER.md says RE may be restricted by jurisdiction or licence>", "purpose": "<security research|interop|
   debugging own software|...>", "decision": "proceed|refuse", "date": "<UTC>"}`.
3. **Refuse** when the owner is a third party, the licence is proprietary/unknown and no right is stated, or when
   the purpose is one DISCLAIMER.md lists as unsupported. A refusal is a row too (`decision: refuse`).
4. Only then run REA (from a run-tree, `python3 tools/kit/runtree.py`; act_gate asks before `rea analyze-*`).
   The findings report `work/re/<slug>.md` starts with `gate: RE-GATE-nnnn` and separates observation,
   derivation, inference and unknown, each with its evidence path.

## Test (what fails)
`python3 tools/station/forge_check.py check` (`forge_gates`): a `work/re/*.md` report without a `gate:` line, a
gate id absent from legal_gate.json or not `proceed`, or a `proceed` row on a third-party proprietary target with
no stated right. Planted in the selftest.

## Never
Never reverse-engineer a client's, customer's or employer's software on this station (boundary); never reproduce
protected code or assets in a deliverable.
