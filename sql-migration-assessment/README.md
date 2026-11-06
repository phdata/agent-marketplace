# sql-migration-assessment

Assess a SQL database estate before migrating it, with the
[phData Toolkit](https://toolkit.phdata.io/docs) CLI: collect the SQL that defines the workload,
extract table-level lineage from it, and decompose the estate into dependency-ordered, scored
migration waves.

Everything here is the **free path** — no LLM, no agent license — and much of it runs with no
database access at all.

```
            ┌─ collect remote   object DDL          Snowflake, Oracle, SQL Server, MySQL, Hive …
the SQL ────┼─ collect script   files incl. BTEQ    any dialect — never connects
            └─ collect history  live query history  Snowflake, Databricks only
   │   /sql-migration-assessment:collect
   ▼
toolkit ds lineage <ds>            (+ --pull on Databricks, --export-errors to triage)
   │   /sql-migration-assessment:lineage
   ▼
toolkit migration plan <ds>
   │   /sql-migration-assessment:plan — waves, groups, held-out objects, tuning loop
   ▼
migration-plan/<ds>/plan.txt + inventory.csv        (the plan of record)
```

## The collection route is the whole decision

It differs per platform more than anything else, and getting it wrong is the usual reason an
assessment stalls. This table is a snapshot from **2026-11-06**; the live answer is in the
project's own `docs/toolkit/data-source.adoc`, which `toolkit init` writes, and
[references/platform-support.md](references/platform-support.md) carries the two `grep`s that
read it out. Check there before telling anyone a route is impossible — the toolkit gains
platforms, and a stale "not supported" is the one error here that fails silently.

| Platform | `collect remote` | `collect script` | `collect history` |
|---|---|---|---|
| Snowflake | TABLE, VIEW, PROCEDURE, FUNCTION | yes | **yes** |
| Databricks | — | yes | **yes** (plus `ds lineage --pull`) |
| Oracle | all four types | yes | no |
| SQL Server | VIEW, PROCEDURE, FUNCTION — **no TABLE** | yes | no |
| **Teradata** | **not supported** | **yes, including BTEQ** | no |
| MySQL | all four types | yes | no |
| Hive / SQLite | TABLE, VIEW | yes | no |

So Teradata is a script-file estate with no DDL collection; SQL Server cannot have its table DDL
collected (use `ds scan` for that metadata); and only Snowflake and Databricks can see the ad-hoc
and BI-tool SQL that no stored object contains.

`collect script` never connects to the data source, so a stub datasource whose JDBC scheme only
sets the dialect is enough — which is what makes a Teradata or SQL Server assessment possible
with no access to the database at all.

## Skills

| Skill | Purpose |
|---|---|
| `/sql-migration-assessment:collect` | Get the SQL in, by the route the platform supports |
| `/sql-migration-assessment:lineage` | Extract lineage, judge the parse rate, triage failures, spot-check dataflows |
| `/sql-migration-assessment:plan` | Cut and tune the wave plan, and say what is actually convertible |

The per-platform matrix, BTEQ specifics, collection restrictions and `collect history`
privileges are in [references/platform-support.md](references/platform-support.md); the plan's
knobs and dispositions are in [references/plan-tuning.md](references/plan-tuning.md).

## What a plan can and cannot hand on

A plan holds four kinds of process, and only two have a converter. `plan.py kinds <ds>` prints
the breakdown, which is usually the most useful number in the whole assessment:

| Kind | Converter |
|---|---|
| `SCRIPT_FILE` — procedure, BTEQ script, job | [procedure-etl-conversion](../procedure-etl-conversion/), **SQL Server and Oracle only** |
| `INFORMATICA_MAPPING` | [informatica-etl-conversion](../informatica-etl-conversion/) |
| `SSIS_PACKAGE` | none — assessable only |
| `QUERY_PATTERN` | none — assessable only |

A complete plan can still be mostly work that nothing automates, and saying so is part of the
assessment. A Teradata BTEQ estate is the clearest case: fully assessable, not convertible by any
current plugin, though `toolkit sql translate` will translate the SQL itself.

## Bundled scripts

[scripts/](scripts/) is invoked by path from the plugin directory — plugin scripts are not on
PATH, and `CLAUDE_PLUGIN_ROOT` is not set for the Bash tool. Run with whichever Python 3 is on
PATH; standard library only, so it behaves the same on Windows, macOS and Linux.

| Command | Purpose |
|---|---|
| `plan.py kinds <ds>` | Estate-wide process counts by kind, and which converter handles each |
| `plan.py groups <ds>` | TSV: wave, group, per-kind counts, tables |
| `plan.py processes <ds> <wave> <group> [--kind K]` | Process ids in one group, optionally of one kind |
| `plan.py summary \| snapshot <ds>` | The plan's summary block; the newest snapshot's path |
| `plan.py wave-id <wave> <group>` | Directory-safe name for a group |

It reads the snapshot JSON off disk because `toolkit migration show` cannot deserialize a plan
containing Informatica or SSIS processes (`Unrecognized field "componentCount"`) — a plan of
SQL-only processes round-trips fine, but reading the file works either way and starts no JVM.

## Prerequisites

- **toolkit-core** (installed automatically): the toolkit binary and a project. Skills preflight
  with `toolkit_check.py`.
- **A datasource entry** for the source. A real connection for `collect remote` and
  `collect history`; a **stub** whose URL is never dialed is enough for `collect script`, as long
  as its type sets the right dialect — that is what the SQL is parsed as.
- **No LLM, no agent license.** Nothing here calls `toolkit agent *`.

## Relationship to the other assessment plugin

[informatica-assessment](../informatica-assessment/) covers the same lineage-and-plan path for a
PowerCenter XML corpus, which arrives as exported files rather than from a database and is
imported with `collect etl --type=INFORMATICA`. Install that one for Informatica, this one for
databases and SQL scripts; they can coexist, and both read the same `migration plan` output.
