---
name: lineage
description: Extract table-level lineage from collected SQL with ds lineage, triage the queries that failed to parse with --export-errors, and spot-check dataflows with --lookup and --table. Use after collecting a database's SQL, when lineage looks incomplete or the parse rate is low, or when asked what feeds or reads a table.
---

# Lineage: collected SQL → dataflow graph

Turns whatever `collect` imported into the table-level graph that `migration plan` decomposes
into waves. Free path — no LLM, no agent license.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
python3 "$TOOLKIT_CHECK" --level project || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit_check.py` in the installed toolkit-core plugin directory.

Something must have been collected first (`/sql-migration-assessment:collect`). No patterns and
no tables is the symptom of an empty store, not of unparseable SQL — go back rather than tuning.

## Step 1 — extract

```bash
toolkit ds lineage <ds> --offline
```

`--offline` when the datasource is a no-access stub — **required** there, because a stub URL must
never be dialed. With real access, drop it so tables can be verified and classified against the
live catalog. Middle ground: stay offline but enrich from an earlier scan snapshot by passing the
selector as the positional argument, `toolkit ds lineage <ds>:scan:latest --offline`.

**On Databricks, add `--pull`.** It reads lineage directly from Unity Catalog system tables and
captures notebooks, jobs and pipelines that never issue warehouse SQL — work that parsing
collected history cannot see at all. It is the one place where the graph can be more complete
than the SQL.

Read the summary to the user: patterns processed, succeeded and failed, parse success rate,
lineage edges created, tables enriched, and unqualified names resolved.

## Step 2 — judge the parse rate before anything else

This is the number that decides whether the plan is worth cutting, and what it means depends on
where the SQL came from:

- **A few failures are normal** and not worth chasing. Structural edges often survive a failed
  parse, and a single unparsed statement costs fidelity on one load rather than dropping it from
  the graph.
- **A low rate usually means the wrong dialect**, not bad SQL. The datasource's configured type
  decides how the collected SQL is parsed; a Teradata estate parsed as ANSI, or PL/SQL parsed as
  T-SQL, fails in ways that read like broken queries. Fix the datasource type, re-collect with
  `--replace-all` if the store is stale, and extract again.
- **A dialect the toolkit does not parse for lineage** surfaces as errors rather than edges,
  however valid the SQL is. `references/platform-support.md` has the supported set; it is a
  smaller list than the set of dialects `collect remote` will happily store.

To see the actual failures:

```bash
toolkit ds lineage <ds> --export-errors ./lineage-errors
```

`--export-errors` is a **mode, not an add-on flag**: it reads the results of the last extraction,
never re-extracts, and never connects. The directory holds an `errors.csv` index — one row per
failed query with its message, source file, schema context and execution count — plus a
`<pattern-hash>.sql` reproducer for each, ready to parse as-is. The most common failure messages
are also printed at the end of the run, and clustered, which is the fastest read on whether this
is one systematic problem or a long tail. That directory is also exactly what phData asks for to
get parsing issues fixed.

**For a BTEQ estate**, read the collection warnings alongside this: `.IMPORT` / `.EXPORT` /
`.RUN` were never stored, and `.IF ... THEN <sql>` was skipped with its command, so some of
what is "missing" from the graph was dropped before lineage ever ran and will not appear in
`errors.csv` at all.

## Step 3 — spot-check with the user

Pick two or three tables the user knows well:

```bash
toolkit ds lineage <ds> --lookup DW.DIM_CUSTOMER    # upstream + downstream ASCII trees
toolkit ds lineage <ds> --table DW.DIM_CUSTOMER     # metadata, column usage, readers, writers
```

`--lookup` accepts `%` wildcards. If the trees match the user's mental model, the graph is
trustworthy enough to plan from; if whole branches are missing, the collection was incomplete —
back to `/sql-migration-assessment:collect`, not forward to the plan.

These lookups stay useful long after the plan is cut: come back here whenever someone asks what
feeds or reads a table.

Command reference: the `ds lineage` sections of `docs/toolkit/data-source.adoc`, written into the
project by `toolkit init`.

Then hand off to `/sql-migration-assessment:plan`.
