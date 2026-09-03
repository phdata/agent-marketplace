---
name: lineage
description: Extract table lineage from the collected Informatica corpus with ds lineage, then spot-check dataflows with --lookup and --table. Use after ds collect etl, when lineage looks incomplete, or when the user asks what feeds or reads a table in the legacy estate.
---

# Lineage: collected mappings → dataflow graph

Turns the imported corpus into the table-level graph that `ds migration-plan` decomposes into
waves. Free path — no LLM, no agent license.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
"$TOOLKIT_CHECK" || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit-check` in the installed toolkit-core plugin directory.

The corpus must already be imported (`/informatica-etl-conversion:collect`). If extraction
reports no patterns and no tables, that's the symptom of an empty store — go back to collect.

## Step 1 — extract

```bash
toolkit ds lineage legacy_dw --offline
```

`--offline` when the datasource is a no-access stub — **required** there, because a stub URL
must never be dialed. With real access to the legacy database, drop `--offline` so tables can
be verified and classified against the live catalog.

Middle ground: stay offline but enrich from a scan snapshot taken earlier
(`/informatica-etl-conversion:collect` Step 5) by passing the snapshot selector as the
positional argument:

```bash
toolkit ds lineage legacy_dw:scan:latest --offline
```

Read the summary out loud to the user: patterns processed/succeeded/failed, parse success rate,
lineage edges created, tables enriched, and unqualified ETL names resolved.

A few failed patterns are normal and not worth chasing: Informatica's dataflow edges come from
the XML structure, not from the embedded SQL, so a failed parse costs fidelity on that
mapping's SQL overrides rather than dropping it from the graph — and `etl-extract` translates
those overrides separately at wave time anyway. A *low* success rate is the signal worth
acting on, and it usually means the datasource type is the wrong dialect for this estate: fix
it, re-run collect with `--replace-all`, and extract again. To see the actual failures,
`toolkit ds lineage legacy_dw --export-errors <dir>` writes them out with a clustered summary
(it's a separate mode that reads stored results — it doesn't re-extract).

## Step 2 — spot-check with the user

Pick two or three tables the user knows well:

```bash
toolkit ds lineage legacy_dw --lookup DW.DIM_CUSTOMER    # upstream + downstream ASCII trees
toolkit ds lineage legacy_dw --table DW.DIM_CUSTOMER     # metadata, column usage, readers, writers
```

`--lookup` accepts `%` wildcards. If the trees match the user's mental model of the estate, the
corpus is trustworthy enough to plan from; if whole branches are missing, the export is
incomplete — back to `/informatica-etl-conversion:collect`.

These lookups stay useful for the whole migration, long after the plan is cut — come back here
whenever someone asks what feeds or reads a table.

Then hand off to `/informatica-etl-conversion:plan`.
