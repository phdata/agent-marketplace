---
name: status
description: Report Informatica conversion progress by crossing the migration plan with the artifacts under waves/ — mappings staged, specs emitted, contracts approved, open review items, pipelines built — and name the next command to run. Use when the user asks how far along the conversion is, what's left in a wave, or what to do next.
---

# Status: where the conversion stands

Read-only. Nothing is tracked in a state file — progress is derived from the plan snapshot and
the artifacts each wave leaves behind, so it stays true even when work happened in another
session.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
"$TOOLKIT_CHECK" --level project || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit-check` in the installed toolkit-core plugin directory.

Check for a plan under `migration-plan/<ds>/`:

- **Plan present** — report against it, as below.
- **No plan but `waves/all/` exists** — this is a direct conversion (few mappings, no plan by
  choice). Skip Step 1 and report from the artifacts alone, with the corpus mapping count as
  the denominator: `<plugin>/scripts/infa-corpus count`.
- **Neither** — assessment hasn't gotten anywhere yet; point at
  `/informatica-etl-conversion:collect`, or `:plan` if the corpus is already imported.

## Step 1 — the plan side

```bash
<plugin>/scripts/infa-plan groups <ds>       # TSV: wave, group, mappings, tables
```

Groups with zero Informatica mappings are table-only — real migration work, but not work this
plugin's wave skill performs. Say so rather than reporting them as untouched.

## Step 2 — the artifact side

```bash
ls -d waves/*/ 2>/dev/null
ls waves/<id>/etl-specs/*.discovery.yaml 2>/dev/null | wc -l
ls waves/<id>/etl-specs/_out-of-scope/*.discovery.yaml 2>/dev/null | wc -l
for c in waves/<id>/discovery-out/*/data-contract.json; do
  jq -r --arg c "$c" '[$c, (.approvedByHuman|tostring),
                       ((.sourceToTarget.humanReviewItems // []) | length)] | @tsv' "$c"
done
ls waves/<id>/pipeline-out/*/build-report.txt 2>/dev/null | wc -l
```

Wave directory names are `w<wave>-<group-sanitized>`, so they map back to plan groups by
construction — except `waves/all/`, which is a direct conversion of the whole corpus.

## Step 3 — report

One table, ordered by wave then group:

| Wave | Group | Mappings | Specs | Contracts approved | Open items | Built | Next action |

Then, below it, only what applies:

- **Judge failures** — builds that finished with failing verdicts, from `build-report.txt`.
- **Plan drift** — if `migration-plan/<ds>/plan.txt` is newer than any `waves/` directory, the
  plan was re-cut after execution started; those wave directories may refer to groups that no
  longer exist under those names. Say which ones.
- **Unsequenced cutover** — in a direct conversion, nothing analyzed the dependency order
  between the converted mappings, so deployment order is still someone's manual problem. Worth
  repeating once the pipelines are built.
- **Out-of-scope specs** — extracted for mappings belonging to other groups, waiting for their
  own group's turn.

Finish with a single recommended next command. Pick the group by **wave order, not by how much
progress it has** — waves are a dependency order, so an untouched group in wave 1 comes before a
half-finished one in wave 2. Within a wave, prefer the foundation group if there is one, then
whichever group has work in flight. That's usually `/informatica-etl-conversion:wave` for that
group; when everything is built, it's the deployment follow-ups in `/toolkit-pipeline:build`.
