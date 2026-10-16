<!-- kit-authored · pack: grade · owner: commons/packs/grade/RUBRIC.md · evidence-graded scoring for any candidate, vendor, posting, tool or proposal -->
# Evidence-graded rubric (grade pack)

A score is only as good as the evidence under it. This rubric is for comparing things a human must decide between:
job postings, candidates' own CVs against a posting, tools in a trial, vendors, ideas. The pattern (score every
criterion, cite the evidence for each, refuse to score what has none) is common to hiring and screening tools; the
wording and the rules here are the kit's own.

## 1 · Define before you score
Write the criteria, their weights and their anchors BEFORE reading the candidates. Weights sum to 100. Each criterion
has anchors for 0, 2 and 4 written as observable facts, not adjectives.

| criterion | weight | 0 | 2 | 4 |
|---|---|---|---|---|
| <criterion> | <w> | <what the evidence shows at 0> | <at 2> | <at 4> |

## 2 · Every score row cites evidence, or scores 0
```
<criterion> · score <0-4> · evidence: <source path or URL + quoted text, or the command and its output>
```
- **No evidence -> 0.** Not "probably 2", not "assumed". The absence is itself the finding, and it is written as
  `evidence: none found (searched: <where>)`.
- **Evidence is quoted, not paraphrased**, with a locator a reader can open. A claim the candidate makes about itself
  is evidence OF THE CLAIM, scored as such; an independent source outranks it.
- **One fact, one criterion.** The same fact may not raise two criteria (double counting).
- **Disqualifiers are separate** from the score: a must-have that is absent stops the evaluation regardless of total.

## 3 · Total with its denominator
`total = sum(weight x score) / (4 x 100)`, reported as `<x>% (<k> of <m> criteria evidenced)`. A total where fewer than
half the criteria are evidenced is reported as **insufficient evidence**, not as a low score.

## 4 · Calibration and bias checks
- Score blind where possible (names, photos, ages removed when grading people).
- Two graders, or one grader twice a day apart on a sample; disagreement > 1 point on a criterion means its anchors are
  unclear: fix the anchors, re-score everything.
- Record the decision and the rubric version together, so a later reader can see what the score meant then.

## 5 · Output
```
GRADE <subject> · rubric <name> v<n> · <date> · grader <name/model>
<criterion rows as in section 2>
disqualifiers: none | <which, with evidence>
total: <x>% (<k>/<m> evidenced) · verdict: <advance | hold | decline | insufficient evidence>
```
The human makes the decision; the rubric makes the evidence visible.
