<!-- kit-authored · pack: research · owner: commons/packs/research/NEGATIVE_RESULTS.md · a station keeps its rows in work/NEGATIVE_RESULTS.md -->
# Negative results (research pack): leads that went nowhere, and claims that did not hold

An investigation is mostly dead ends. Writing them down is what stops the next pass re-walking them. Record a dead
lead or a refuted claim in the SAME commit that establishes it; a new investigation reads this file before its first
search.

## Row grammar
```
## N-<station>-<nnnn> · <YYYY-MM-DD> · <the lead or claim, one line>
question: <the investigation question it served>
what was checked: <sources consulted, each with URL or archive id and the date accessed>
result: refuted | unsupported (no primary source found) | inconclusive (sources conflict)
evidence: <the primary source that contradicts it, quoted with its locator; or the search log showing absence>
custody: <who/what fetched it, stored where (path + sha256 of the capture)>
retest: <a concrete condition: a record release date, a new archive, a person who could confirm — never "later">
```

## Rules
- "Unsupported" and "refuted" are different results. Absence of evidence is recorded with the search that found
  nothing (queries, sources, dates) so a reader can judge how hard it was looked for.
- A claim that circulated widely and turned out false is especially worth a row: it will be met again.
- Rows are append-only; a later confirmation adds a new row that cites this one.
- A row never contains personal data beyond what the public source itself published.
