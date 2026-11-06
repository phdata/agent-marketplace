# What each platform supports

The whole shape of an assessment is decided by how the SQL can be got out of the source, and
that differs per platform more than anything else here. Settle this first; everything downstream
is the same regardless.

## Read the current matrix, don't trust this one

**The toolkit's own docs are the source of truth, and they ship into every project.** The tables
below are a snapshot taken on **2026-11-06**, kept here so the common cases need no lookup — but
the toolkit adds platforms and capabilities, and a stale "not supported" here would tell a user
something is impossible when it has since shipped. That is the one failure mode worth guarding
against, because it is silent.

So when the platform in front of you is anything other than SQL Server, Oracle or Teradata, or
when a user says a route should work that the table says does not, check the project's own copy
first.

**Run these from the toolkit project** — the directory holding `toolkit.conf`, which
`toolkit_check.py --level project` prints as its `ok project:` line. The path is relative to that
project, *not* to this plugin and not to wherever the shell happens to be; running it in the
wrong directory is the one way this fails, and it fails with a bare
`No such file or directory`:

```bash
cd "<the toolkit project>"

# which object types `collect remote` can collect, per platform
grep -A50 '^===== Supported Object Types' docs/toolkit/data-source.adoc | grep -E '^\|'

# which platforms `ds lineage` parses, and from which collection route
grep -A24 'Lineage Support' docs/toolkit/data-source.adoc | grep -E '^\| '
```

Two things that make the file absent even inside a real project, both recoverable:

- **`toolkit init` was run with `--docs=false`.** Re-run plain `toolkit init` in that project: it
  reports "already initialized" and still extracts `docs/toolkit/`, preserving any file that was
  modified. Verified — that is how the docs arrive after the fact.
- **You are not in a toolkit project at all** (a plugin checkout, a home directory). There is
  nothing to read; find the project, or fall back to the published docs at
  https://toolkit.phdata.io/docs, which carry the same tables.

(`Supported Platforms` appears twice in that file — the first belongs to `ds row-diff`. Anchor on
`Lineage Support` instead, which is unique.)

Facts in this file that come from the **code** rather than the docs are marked as such; those
fail loudly and self-correct, so they are safe to rely on. Everything in the two tables below is
doc-sourced, and can drift.

## Collection routes

*Snapshot 2026-11-06 — verify with the grep above before telling a user something is impossible.*

| Platform | `collect remote` (object DDL) | `collect script` (files) | `collect history` (live) |
|---|---|---|---|
| Snowflake | TABLE, VIEW, PROCEDURE, FUNCTION | yes | **yes** |
| Databricks | — | yes | **yes** (plus `ds lineage --pull`) |
| Oracle | TABLE, VIEW, PROCEDURE, FUNCTION | yes | no |
| SQL Server | VIEW, PROCEDURE, FUNCTION — **no TABLE** | yes | no |
| Teradata | **not supported** | **yes, including BTEQ** | no |
| MySQL | TABLE, VIEW, PROCEDURE, FUNCTION | yes | no |
| Hive | TABLE, VIEW | yes | no |
| SQLite | TABLE, VIEW | yes | no |

So in practice:

- **Teradata** is a script-file estate. There is no DDL collection; the SQL has to arrive as
  files — BTEQ scripts included — and `collect script` imports them. This is the single most
  common surprise.
- **SQL Server** cannot have its table DDL collected. Collect views, procedures and functions
  for the workload, and use `ds scan` for table and column metadata, which is a different
  snapshot and feeds the plan's sizing rather than its lineage.
- **Snowflake and Databricks** are the only platforms with live query history, which is the one
  route that sees ad-hoc and BI-tool SQL rather than just stored objects.
- **Databricks** additionally has `ds lineage --pull`, reading lineage straight from Unity
  Catalog system tables — it captures notebooks, jobs and pipelines that never issue warehouse
  SQL, which nothing else here can see.

## Lineage support

`collect remote` **stores DDL for every supported dialect**, but `ds lineage` parses a subset.
Patterns in a dialect it cannot parse surface as lineage errors rather than edges — which is why
a low parse rate is the signal to check, not a thing to chase statement by statement.

*Snapshot 2026-11-06 — same caveat.*

| Platform | Lineage |
|---|---|
| Snowflake | Full: extraction, table lookup, lineage lookup |
| Databricks | Full, plus `--pull` from Unity Catalog |
| SQL Server | From imported script files |
| Teradata | From imported script files, including BTEQ |
| Oracle | From imported script files **and** object DDL stored by `collect remote`. SQL and PL/SQL both parsed — procedures, functions, package bodies, anonymous blocks, triggers — so DML nested in package routines and control flow yields edges, and package routines are named `SCHEMA.PACKAGE.ROUTINE` |

If a platform's stored DDL yields no edges, the fallback costs nothing: `collect remote -o <dir>`
has already written the same SQL out as files, so `collect script` can import them by the route
the table above does guarantee.

## BTEQ specifics

Teradata BTEQ scripts are parsed, with the dot-commands isolated and handled deliberately. This
behaviour is **in the collector's code**, not a support table, so it does not drift the way the
matrices above can. Two of those decisions change what the lineage is worth, so state them when
assessing a BTEQ estate:

- `.IMPORT` / `.EXPORT` / `.RUN` reference external files. They are **surfaced as warnings and
  never stored**, so file-based data movement is invisible to the graph. Read those warnings —
  they are the only record that something was dropped.
- `.IF ... THEN <sql>` embedded SQL is conditional and is **skipped with the command**, so
  conditional loads yield no edges at all.
- `.LOGON` / `.LOGDATA` are skipped without ever echoing their text — right for credentials, but
  it means connection context is absent too. Everything else is skipped silently, like `GO`.

## Collection restrictions worth knowing before filtering

- **Procedures and functions cannot be filtered at all.** There are no filters for those object
  types; collection takes every procedure and function it can see.
- **Database and schema filters** apply to table and view collection on every supported
  platform, but for procedures and functions only **SQL Server and Snowflake** honour them, and
  **Oracle** honours either a database or a schema filter — not both.
- **Datasource table/view filters in `toolkit.conf` are not applied** when collecting SQL. CLI
  parameters take precedence over `toolkit.conf`.

## `collect history` privileges

Only Snowflake and Databricks have it, and it reads system tables that need granting:

- **Snowflake**: the connecting role needs `IMPORTED PRIVILEGES` on the `SNOWFLAKE` database —
  by default only `ACCOUNTADMIN` has it.
  `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <role>;`
- **Snowflake (stage export)**: the toolkit first tries a high-throughput export via the user
  stage (`@~/toolkit_history_export/`), needing temporary-table creation and stage write. If that
  fails it falls back to JDBC streaming automatically, with no extra requirement — so a stage
  failure is a performance note, not an error.

`collect script` never connects to the data source, so none of these privileges apply to it.

## What the plan can and cannot convert afterwards

A plan holds four kinds of process. `plan.py kinds <ds>` prints the breakdown, and which of them
has a converter today:

The kinds are **a code enum** (`ProcessKind`), so this list is stable; which plugin converts
which is a fact about this marketplace, not about the toolkit.

| Kind | What it is | Converter |
|---|---|---|
| `SCRIPT_FILE` | An imported script file — stored procedure, BTEQ script, job | `procedure-etl-conversion`, **SQL Server and Oracle only** |
| `INFORMATICA_MAPPING` | A mapping from an ETL import | `informatica-etl-conversion` |
| `SSIS_PACKAGE` | An SSIS package from an ETL import or catalog DDL sweep | none — assessable only |
| `QUERY_PATTERN` | A query pattern with no file provenance, usually from history | none — assessable only |

This matters at the end of an assessment: a plan can be complete and still contain a lot of work
nothing automates. Say which is which rather than implying the whole estate converts. A Teradata
BTEQ estate is the clearest case — fully assessable, and not convertible by any current plugin,
though `toolkit sql translate` will translate the SQL itself.
