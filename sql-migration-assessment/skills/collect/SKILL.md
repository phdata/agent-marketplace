---
name: collect
description: Collect the SQL that defines a database's workload into the toolkit's store — object DDL with collect remote, script files including Teradata BTEQ with collect script, or live warehouse query history with collect history — choosing the route the platform actually supports. Use when starting a migration assessment of SQL Server, Oracle, Teradata, Snowflake, Databricks or another JDBC source, or when asked how to get a legacy database's SQL into the toolkit.
---

# Collect: a database's SQL → the toolkit's store

First step of an assessment. Free path — no LLM, no agent license — and the only step whose shape
depends on which platform the estate runs on.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
python3 "$TOOLKIT_CHECK" --level project || exit
python3 "$TOOLKIT_CHECK" --list-datasources
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit_check.py` in the installed toolkit-core plugin directory.

`--level project` and not the default: `collect script` never connects to the data source, so a
script-file assessment needs no working datasource at all. The other two routes do, and get
their own check below.

## Step 1 — pick the collection route

**This is the decision the rest of the assessment hangs on.** `references/platform-support.md`
(two levels up from this skill's directory) has the full matrix and, more importantly, the two
one-line `grep`s that read it out of the project's own `docs/toolkit/data-source.adoc` — which
`toolkit init` writes and which is the actual source of truth. Run those **from the toolkit
project**, the directory holding `toolkit.conf`: that path is relative to the project, not to
this plugin, and a bare `No such file or directory` means the wrong directory or a
`--docs=false` init, both of which that reference tells you how to fix. Use those whenever the platform
is not one of the three below, or whenever a user says a route should work that the table says
does not: the toolkit gains platforms, and a stale "not supported" is the one error here that
fails silently rather than loudly.

The common cases, as of 2026-11-06:

| Platform | Route |
|---|---|
| **Teradata** | `collect script` only — no DDL collection exists. BTEQ scripts included. |
| **SQL Server** | `collect remote` for VIEW, PROCEDURE, FUNCTION — **no TABLE** — or `collect script` |
| **Oracle** | `collect remote` for all four types, or `collect script`. PL/SQL package bodies are parsed |
| **Snowflake / Databricks** | `collect history` for live query history, the only route that sees ad-hoc and BI SQL |

Ask what the user has before choosing: a Teradata shop usually has a directory of BTEQ scripts in
version control, while a SQL Server shop usually has database access and no script export. Say
which route you are taking and why.

## Step 2a — object DDL (`collect remote`)

Needs a working connection: `python3 "$TOOLKIT_CHECK" --level connect --datasource <ds>`.

```bash
toolkit collect remote <ds> --types PROCEDURE,VIEW,FUNCTION -o collected-sql/
```

- **`-o` matters even though it is optional.** It writes the SQL out as files as well as storing
  the DDL, which gives you a reviewable artifact and a free fallback: if lineage gets no edges
  from the stored DDL, `collect script collected-sql/` imports the very same SQL by the route the
  support matrix does guarantee.
- **Omit `--types` to take every supported type**, but name them when you know what you want —
  and remember SQL Server has no TABLE support, so table and column metadata comes from
  `toolkit ds scan <ds>` instead, which is a different snapshot that feeds the plan's sizing.
- **Filters barely apply here.** There are none at all for procedures and functions; database and
  schema filters are honoured for those only on SQL Server and Snowflake, and Oracle takes either
  a database or a schema filter but not both. Datasource filters in `toolkit.conf` are ignored
  when collecting SQL. Do not promise the user a scoped collection the tool will not deliver.
- `--group-by SCHEMA` organizes the written files by schema; the default groups by object type.

Report what it prints: objects collected per type, and anything it skipped.

## Step 2b — script files (`collect script`)

The route for Teradata, and for any estate whose SQL arrives as files.

```bash
toolkit collect script <ds> -i sql-scripts/
```

- **Never connects to the data source**, so it works with a stub datasource whose JDBC scheme
  only sets the dialect for parsing — the same trick the Informatica assessment uses. That is
  what makes a Teradata assessment possible with no Teradata access at all.
- The datasource's configured type decides which dialect the scripts are parsed as. Getting it
  wrong is the usual cause of a near-zero parse rate, and it reads like broken SQL rather than a
  wrong setting.
- **BTEQ** is handled, with its dot-commands isolated and deliberately dropped. Two of those
  drops change what the lineage is worth: `.IMPORT` / `.EXPORT` / `.RUN` are surfaced as
  **warnings** and never stored, so file-based movement is invisible; and `.IF ... THEN <sql>` is
  skipped with its command, so conditional loads yield no edges. Surface both to the user — the
  warnings are the only record.

## Step 2c — live query history (`collect history`)

Snowflake and Databricks only, and the only route that sees SQL no stored object contains.

```bash
toolkit collect history <ds> --lookback 90
```

Needs privileges that are usually not granted by default:

- **Snowflake**: `IMPORTED PRIVILEGES` on the `SNOWFLAKE` database, which only `ACCOUNTADMIN`
  has out of the box — `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <role>;`
- A stage-export attempt happens first for throughput and falls back to JDBC streaming on its
  own, so a stage failure in the log is a performance note, not an error.

On Databricks, mention `ds lineage --pull` at the next step too: it reads lineage straight from
Unity Catalog and captures notebooks, jobs and pipelines that never issue warehouse SQL, which
no amount of history collection will show.

## Step 3 — confirm what landed

```bash
toolkit collect list
```

Report the counts and, where the route wrote files, the directory. If the numbers are far below
what the user expected, resolve that now — the plan can only ever be as complete as what was
collected, and a thin collection produces a confident-looking plan of the wrong estate.

Command reference: the `collect` sections of `docs/toolkit/data-source.adoc`, written into the
project by `toolkit init`.

Then hand off to `/sql-migration-assessment:lineage`.
