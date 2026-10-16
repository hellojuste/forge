export const meta = {
  name: '_template',
  description: 'Skeleton for a station workflow: GATHER real command output, do the work, re-run the certain test and return its exit code as the verdict',
  whenToUse: 'copy to .claude/workflows/<name>.js when a station verb needs a workflow (CA-17); never run as is',
  phases: [
    { title: 'Gather', detail: 'a small agent runs the GATHER commands verbatim and returns stdout tail + exit code per command' },
    { title: 'Work', detail: 'the worker does the one deliverable, reading only what Gather returned plus the files it names' },
    { title: 'Verify', detail: 'a reader who did not do the work re-runs CERTAIN_TEST; its exit code is the verdict' },
  ],
}

// --- how to use this skeleton (commons; copy, never edit in place) ------------
// 1. Copy to .claude/workflows/<verb>.js (station-only) and set meta.name to the file stem.
// 2. Replace GATHER with the commands whose REAL output the work needs (never prose about them).
// 3. Replace TASK with the one deliverable (one file or one return shape) and its FORBIDDEN list.
// 4. Set CERTAIN_TEST to a command that names a tool, can fail on a wrong result, and mutates nothing
//    (tools/upstream/workflows_check.py certain_tests enforces this).
// 5. Models come from args.models ({small, medium, large}) so the station roster (station.json gov.model_roster)
//    decides them; with no roster the harness default runs.
// Every agent prompt starts with STATION_WORKFLOW=<name> so hooks can tell a workflow agent from an inline run.
const WORKFLOW = '_template'
const CERTAIN_TEST = 'python3 tools/station_audit.py -k workflows_parse -k certain_tests'
const GATHER = [
  'python3 tools/station_audit.py --state',
  'git status --short',
  'git log --oneline -8',
]
const TASK = 'the one deliverable this workflow exists for (replace me in the copy)'
const FORBIDDEN = 'editing any lane (repertoire/, upstream/, study/, nc-lane/) outside _PATCHES/; any commons file; force-push or history rewrite; inventing a secret value'

const MODELS = (args && args.models) || {}
function opts(phaseName, tier, effort) {
  const o = { phase: phaseName, effort: effort }
  if (MODELS[tier]) { o.model = MODELS[tier] }
  return o
}

function buildPlan() {
  return {
    workflow: WORKFLOW,
    shape: 'gather -> work -> verify',
    gather: GATHER,
    certainTest: CERTAIN_TEST,
    stages: meta.phases.map(function (p) { return p.title }),
  }
}

// --dry: the plan, no agent spawned
if (args && args.dry === true) {
  log(WORKFLOW + ' --dry: ' + meta.phases.length + ' stages planned, none spawned')
  return buildPlan()
}

const out = {}

phase('Gather')
out.gather = await agent(
  'STATION_WORKFLOW=' + WORKFLOW + '. Gather stage. Run each command below VERBATIM from the station root, one at a time. ' +
    'Return JSON only: [{"cmd": <command>, "exit": <exit code>, "tail": <last 40 lines of stdout+stderr>}]. ' +
    'Do not summarise, interpret or fix anything. Commands: ' + JSON.stringify(GATHER),
  opts('Gather', 'small', 'low'))

phase('Work')
out.work = await agent(
  'STATION_WORKFLOW=' + WORKFLOW + '. Work stage. Deliverable: ' + TASK + '. FORBIDDEN: ' + FORBIDDEN + '. ' +
    'Ground every claim in the gathered output below or in a file you read and cite as path + quoted text (no line numbers). ' +
    'What you cannot establish goes in gaps[], each ending with the test that would settle it. Gathered: ' + JSON.stringify(out.gather),
  opts('Work', 'medium', 'medium'))

phase('Verify')
out.verify = await agent(
  'STATION_WORKFLOW=' + WORKFLOW + '. Verify stage. You did NOT do the work. Run exactly: ' + CERTAIN_TEST +
    ' from the station root. Return JSON only: {"cmd": <command>, "exit": <exit code>, "tail": <last 30 lines>}. ' +
    'Do not edit anything. The work claimed: ' + JSON.stringify(out.work),
  opts('Verify', 'small', 'low'))

const exitCode = out.verify && typeof out.verify === 'object' && 'exit' in out.verify ? out.verify.exit : null
return { workflow: WORKFLOW, plan: buildPlan(), result: out, certainTest: CERTAIN_TEST, exit: exitCode,
  verdict: exitCode === 0 ? 'certain test exit 0' : 'certain test exit ' + String(exitCode) }
