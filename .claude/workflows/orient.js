export const meta = {
  name: 'orient',
  description: 'Orient on this branch from real output: audit state line, STATION.md head, router top rows, last 8 commits -> one orientation summary with the next move',
  whenToUse: 'start of a session on a station or on main, after a compaction, or when unsure which station a task belongs to',
  phases: [
    { title: 'Gather', detail: 'run the four read-only commands and return their raw output and exit codes' },
    { title: 'Orient', detail: 'one summary: where am I, what is red, what the router would do first, the next move' },
    { title: 'Verify', detail: 're-run the audit state line; its exit code is the verdict' },
  ],
}

// --- workflow identity --------------------------------------------------------
// Read-only. Gathers the station's own state instead of guessing it (LEAN LL-19/LL-27: the first move is a
// gather, and an inherited claim is re-derived). On main (no station.json) STATION.md is absent: the summary
// then says "main: the kit" and points at KIT.md and the decision tree (README.md).
const WORKFLOW = 'orient'
const CERTAIN_TEST = 'python3 tools/station_audit.py --state'
const GATHER = [
  'python3 tools/station_audit.py --state',
  'head -n 40 STATION.md 2>/dev/null || head -n 40 KIT.md',
  'python3 -c "import json,glob;rows=json.load(open(\'router/intents.json\')).get(\'intents\',[]);[rows.extend(json.load(open(f)).get(\'intents\',[])) for f in sorted(glob.glob(\'router/intents.d/*.json\'))];[print(r.get(\'name\'),\'->\',json.dumps((r.get(\'router\') or {}).get(\'first_move\'))) for r in rows[:12]]"',
  'git log --oneline -8',
]

const MODELS = (args && args.models) || {}
function opts(phaseName, tier, effort) {
  const o = { phase: phaseName, effort: effort }
  if (MODELS[tier]) { o.model = MODELS[tier] }
  return o
}

function buildPlan() {
  return { workflow: WORKFLOW, shape: 'gather -> orient -> verify', readOnly: true, gather: GATHER, certainTest: CERTAIN_TEST }
}

if (args && args.dry === true) {
  log('orient --dry: 3 stages planned (gather -> orient -> verify), none spawned')
  return buildPlan()
}

const out = {}
const question = (args && args.question) || 'what should this session do first?'

phase('Gather')
out.gather = await agent(
  'STATION_WORKFLOW=orient. Gather stage. From the repository root run each command below VERBATIM, one at a time, read-only. ' +
    'Return JSON only: [{"cmd": <command>, "exit": <exit code>, "tail": <last 40 lines of stdout+stderr>}]. ' +
    'Do not summarise or fix anything. Commands: ' + JSON.stringify(GATHER),
  opts('Gather', 'small', 'low'))

phase('Orient')
out.summary = await agent(
  'STATION_WORKFLOW=orient. Orient stage. Using ONLY the gathered output below, write one orientation summary of at most 12 lines: ' +
    '(1) branch and station (or "main: the kit"), (2) the audit state line verbatim and which MUST checks are red, ' +
    '(3) the station purpose from STATION.md in one line, (4) the router rows most relevant to the question, ' +
    '(5) the last commit, (6) ONE recommended next move naming a workflow or skill that exists in the gathered rows. ' +
    'Any number you state is quoted from the gathered output; anything not in it is "unknown". Question: ' + question +
    '. Gathered: ' + JSON.stringify(out.gather),
  opts('Orient', 'medium', 'low'))

phase('Verify')
out.verify = await agent(
  'STATION_WORKFLOW=orient. Verify stage. Run exactly: ' + CERTAIN_TEST + ' from the repository root. ' +
    'Return JSON only: {"cmd": <command>, "exit": <exit code>, "tail": <its output>}. Do not edit anything.',
  opts('Verify', 'small', 'low'))

const exitCode = out.verify && typeof out.verify === 'object' && 'exit' in out.verify ? out.verify.exit : null
return { workflow: WORKFLOW, summary: out.summary, gather: out.gather, certainTest: CERTAIN_TEST, exit: exitCode }
