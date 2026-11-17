---
name: status
description: Report stored-procedure conversion progress from the artifacts on disk — procedures read, specs emitted, contracts approved, open review items, pipelines built — and name the next command to run. Use when the user asks how far along a procedure migration is, what is left, or what to do next.
---

# Status: where the procedure conversion stands

Read-only. Nothing is tracked in a state file: progress is derived from the plan snapshot, when
there is one, and the artifacts each stage leaves behind, so it stays true even when the work
happened in another session.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
python3 "$TOOLKIT_CHECK" --level project || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit_check.py` in the installed toolkit-core plugin directory.

Then establish which shape this conversion has:

- **A plan under `migration-plan/<ds>/`** — report against it, group by group (Step 1).
- **No plan, but a `procedure-out/` directory** — a direct conversion. Skip Step 1 and report
  from the artifacts alone, with the procedure count as the denominator:
  `ls procedures/*.sql | wc -l`.
- **Neither** — nothing has been converted. Point at `/procedure-etl-conversion:convert`, and
  note that it needs a directory of `.sql` procedure scripts first (`toolkit collect remote
  <legacy-ds> --types PROCEDURE -o procedures/` with database access, or scripts from a DBA).

## Step 1 — the plan side

```bash
python3 <plugin>/scripts/proc_plan.py groups  <legacy-ds>   # TSV: wave, group, procedures, tables
python3 <plugin>/scripts/proc_plan.py summary <legacy-ds>
```

Invoke it by path from this plugin's `scripts/` directory; Python 3 standard library only, so it
behaves the same on Windows, macOS and Linux.

Two kinds of group are easy to misreport:

- **Groups with zero procedures** are either table-only, or hold work of a different kind —
  Informatica mappings, SSIS packages or bare query patterns, which this plugin does not
  convert. `proc_plan.py` counts only `SCRIPT_FILE` processes, so a group showing 0 may still be
  real migration work. Say which it is rather than calling it untouched.
- **Procedures that yield no loads** (orchestrators that only `EXEC` other procedures) will
  never produce a spec. Count them as read, not as pending.

## Step 2 — the artifact side

```bash
ls procedures/*.sql 2>/dev/null | wc -l
ls procedure-out/etl-specs/*.discovery.yaml 2>/dev/null | wc -l
python3 <plugin>/scripts/review_queue.py status --dir procedure-out/discovery-out
ls procedure-out/pipeline-out/*/build-report.txt 2>/dev/null | wc -l
```

`review_queue.py status` prints one row per contract — approved yes/no, open items, how many are
commented, and how many the last resolve sweep refused — plus the approved count. For the
distinct open questions rather than the per-contract view, `review_queue.py list`.

## Step 3 — report

One table, ordered by wave then group when there is a plan, otherwise one row per procedure:

| Wave | Group | Procedures | Specs | Contracts approved | Open items | Built | Next action |

Then, below it, only what applies:

- **Procedures that failed to parse** — from `procedure-out/etl-extract.log`, which is the only
  record of them.
- **Flagged loops** — extracted loops that could not be reduced to a set-based statement.
  Those marked for human review are decisions someone still owes, not bugs.
- **Judge failures** — builds that finished with failing verdicts, from `build-report.txt`, and
  any `EXECUTION: SKIPPED` on a dbt or pyspark build, which means nothing was actually run.
- **NOT APPLIED review items** — comments the resolver refused, which need a different answer
  rather than the same one again.
- **Unsequenced cutover** — in a direct conversion nothing analyzed the order between
  procedures, so deployment order is still manual. Worth repeating once pipelines are built.
- **Orchestration** — the `EXEC` graph between procedures is never captured by extraction, and
  has to be rebuilt as scheduling on the target side.

Finish with a single recommended next command. With a plan, pick the group by **wave order, not
by how much progress it has**: waves are a dependency order, so an untouched group in wave 1
comes before a half-finished one in wave 2. That is usually
`/procedure-etl-conversion:convert`; when everything is built it is the deployment follow-ups in
`/toolkit-pipeline:build`.
