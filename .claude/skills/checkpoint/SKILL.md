---
name: checkpoint
description: Record a checkpoint the moment work becomes durable (an accepted slice or a commit): hash, paths, numbers with their commands, owed items with triggers, and the next slice's contract.
---
# checkpoint — the durable record of an accepted slice (commons; owner governance/rules.json R-checkpoint)

Write one after every accepted slice and every commit, and before a compaction or `/clear`. A compaction reopens on
the plan and the newest checkpoint's NEXT block, never on the diff.

## Live context
!`git log --oneline -3`
!`python3 tools/station_audit.py --state`

## Shape (append to `work/CHECKPOINTS.md`, newest last; one block per checkpoint)
```
## CP <YYYY-MM-DD HH:MM UTC> · <branch> · <short subject>
commit: <full or short hash that resolves>          plan item: <plan file + item id>
paths: <every path the slice touched>
numbers:
  - <value> — `<the command that prints it>`        (a number without its command is not recorded)
owed:
  - <item> — trigger: <event | date | command>       (no trigger = not owed, abandoned)
NEXT:
  deliverable: <one file or one return shape>
  files: <paths the next slice may write>
  tier: <model at effort, from /tier>
  done-test: <a command that can fail>
  refusal: <what to return instead of guessing>
```

## Rules
- The hash must resolve (`git cat-file -e <hash>`); cite text anchors, never line numbers.
- Numbers are re-derived by their command at write time; a checkpoint never copies a number from an older one.
- If the slice was rejected, say so in one line and keep the NEXT block pointing at the redo.
