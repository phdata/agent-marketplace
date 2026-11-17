---
name: plan
description: Run toolkit migration plan to decompose extracted lineage into ordered, scored migration waves, then walk the waves, groups, held-out objects and what is actually convertible with the user, tuning until the cut is right. Use when the user wants a migration plan, wave sequencing, an inventory, a migration estimate, or asks to re-cut an existing plan.
---

# Plan: lineage → ordered migration waves

`migration plan` clusters the lineage graph into groups, orders them into waves by dependency,
and scores each for complexity, priority and risk. Its output is the plan of record for the rest
of the migration — this plugin keeps no separate state. Free path: no LLM, no agent license.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
python3 "$TOOLKIT_CHECK" --level project || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit_check.py` in the installed toolkit-core plugin directory.

Lineage must exist (`/sql-migration-assessment:lineage`). A plan cut from a thin graph looks just
as confident as one cut from a complete graph, so do not get here with an unresolved parse-rate
problem.

## Step 1 — cut a plan

```bash
toolkit migration plan <ds>
```

For a small estate (under ~50 tables) the defaults — tuned for hundreds of tables — collapse
everything into one group. Start from the small-estate preset instead:

```bash
toolkit migration plan <ds> \
    --hub-min-component-size 10 --hub-min-readers 4 --max-group-size 8
```

Writes `migration-plan/<ds>/plan.txt`, `migration-plan/<ds>/inventory.csv`, and a JSON snapshot
under `tools/migration/snapshots/migration-plan/`. `-o` moves that output directory.

To plan one mart rather than the estate, `--target <table>` scopes the whole plan to that table
and everything it is transitively built from — repeatable, and it takes an `@file` for a long
list. That is usually a better first conversation than tuning group sizes on a whole-estate cut.

## Step 2 — read the artifacts, not the console

The command's own output truncates long lists. Read the written files, and use the bundled script
rather than reaching into the JSON by hand:

```bash
python3 <plugin>/scripts/plan.py kinds   <ds>   # what the estate actually contains
python3 <plugin>/scripts/plan.py summary <ds>   # wave/group/table counts
python3 <plugin>/scripts/plan.py groups  <ds>   # TSV: wave, group, counts by kind, tables
```

Invoke it by path from this plugin's `scripts/` directory (two levels up from this skill's
directory); Python 3 standard library only. It handles the three snapshot shapes that bite when
queried by hand — absent `processes`/`tables` keys, wave numbers that do not start at 0, and the
four different process kinds — and it reads the JSON off disk because
`toolkit migration show` cannot deserialize a plan containing Informatica or SSIS processes.

**Lead with `kinds`.** It is the question the user actually has, and the answer that decides what
the migration costs:

```
SCRIPT_FILE            412   procedure-etl-conversion (SQL Server / Oracle procedures)
INFORMATICA_MAPPING      0   informatica-etl-conversion
SSIS_PACKAGE            37   no converter - assessable only
QUERY_PATTERN          188   no converter - assessable only
```

Then walk the user through, in this order:

1. **Summary** — wave, group and table counts, and unparsed patterns.
2. **The wave table** — which groups land in which wave, with complexity, priority and risk
   bands. Wave order is a dependency order: a group migrates after everything it reads from.
3. **Contract edges** (`feeds X: A -> B` lines in `plan.txt`) — cross-group dataflows. Each is a
   cutover constraint: sequence it, or dual-run the two sides.
4. **Co-migrate groups** — groups in a dependency cycle that must cut over together.
5. **Held-out objects** — audit sinks, interfaces, placeholders, plumbing, dead and set-aside
   tables. Each disposition means a different decision, and the glossary is in
   `references/plan-tuning.md`. Interfaces especially: files, queues and services with no
   warehouse equivalent, which someone has to rebuild as a stage, an unload or a connector.
6. **What has no converter.** Be explicit. A complete plan can still be mostly work that nothing
   automates — `SSIS_PACKAGE` and `QUERY_PATTERN` processes have no conversion path today, and
   `SCRIPT_FILE` only converts for SQL Server and Oracle. A Teradata BTEQ estate is fully
   assessable and not convertible by any current plugin, though `toolkit sql translate` will
   translate the SQL itself.

On a large plan, read `plan.txt` in pieces — the summary table first, then the groups under
discussion — rather than pulling the whole file into context.

## Step 3 — tune and re-cut

Re-run with adjusted knobs until the user agrees the cut matches how their teams actually own the
work. The full knob table and when to reach for each is in `references/plan-tuning.md`; the ones
that come up most:

- `--target <table>` — plan one mart and its upstream, instead of the estate.
- `--max-group-size N` — split groups too big for one team to migrate at once. It caps *tables*,
  not processes, so a group can still come out process-heavy; check `plan.py groups` after.
- `--seed <table>` — treat a table as an additional final output, to break a group on a boundary
  the user cares about.
- `--exclude <table>` — leave a table out entirely (already migrated, or truly retired).
- `--hub-min-readers` / `--hub-min-component-size` / `--hub-max-tables` — control what gets
  pulled into the shared foundation group.

Each re-run overwrites `plan.txt` and `inventory.csv` and adds a snapshot. **Warn the user before
re-cutting once conversion has started**: group names and wave numbers can change, which strands
existing per-group work directories, and a conversion plugin's `status` skill detects that drift
by comparing modification times.

## Step 4 — hand off

Say plainly what the plan is for and who takes it next:

- `SCRIPT_FILE` processes on SQL Server or Oracle → `/procedure-etl-conversion:convert`, one
  group at a time, lowest wave first (its foundation group, if there is one, feeds everything
  else).
- `INFORMATICA_MAPPING` processes → `/informatica-etl-conversion:wave`. Note that plugin assesses
  its own corpus from PowerCenter XML rather than from this plan's collection.
- Everything else → the plan, the inventory and a human.

`inventory.csv` is the artifact to hand to stakeholders: one row per object, with its wave, group,
kind, scores and stats. It is the thing that answers "how big is this migration".

Command reference: the `migration plan` sections of `docs/toolkit/data-source.adoc`, written into
the project by `toolkit init` — worth reading before tuning, since it documents what each knob
does to the clustering.
