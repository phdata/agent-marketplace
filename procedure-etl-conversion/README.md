# procedure-etl-conversion

Convert SQL Server (T-SQL) and Oracle (PL/SQL) stored-procedure ETL into Snowflake pipelines with
the [phData Toolkit](https://toolkit.phdata.io/docs) CLI.

Unlike the Informatica path, **extraction here is deterministic**: `agent etl-extract
--etl-platform=procedure` parses each procedure body, walks its `IF`s and loops to find the
statements that load tables, resolves each load's column lineage, and dialect-translates the SQL
with `sql-translation-next` — no LLM. Each emitted spec carries the authoritative transformation,
so discovery consumes it verbatim rather than re-interpreting prose. Extraction can be run
entirely LLM-free.

```
procedures/*.sql                       from 'collect remote --types PROCEDURE', or a DBA
   │   /procedure-etl-conversion:convert
   ▼
toolkit agent etl-extract --etl-platform=procedure   (dry-run first; deterministic)
   │   one <schema>.<procedure>__<target>.discovery.yaml per load
   ▼
toolkit agent discovery <snowflake-ds> per spec
   │   spec parsing is skipped — the spec's target requirement is authoritative
   ▼
grouped review queue → --resolve sweep → approvedByHuman
   ▼
toolkit agent pipeline-build per approved contract
   ▼
procedure-out/conversion-report.md     /procedure-etl-conversion:status
```

## Scope — read this first

Both limits are enforced by the toolkit, not preferences:

| | Supported | Not supported |
|---|---|---|
| Source dialect | **mssql** (T-SQL), **oracle** (PL/SQL) | anything else — Teradata, HANA, Postgres, Netezza, Redshift, BigQuery … |
| Target platform | **Snowflake** | **Databricks**, which the Informatica path does support |

A run with any other dialect or target is refused outright, so establish both before starting.

## Skills

| Skill | Purpose |
|---|---|
| `/procedure-etl-conversion:convert` | Procedures → generated pipelines end to end: dry run, extract, discovery, grouped review queue, build, report |
| `/procedure-etl-conversion:status` | Progress across the conversion, and what to run next |

The dialect and target limits, how deterministic each stage really is, procedure parameters,
target filtering, the review-queue tags and the resume rules are in
[references/procedure-runbook.md](references/procedure-runbook.md).

## Getting the procedures

With access to the legacy database, collect the DDL — this also stores it so `ds lineage` can
read it with no script-import step, which is what makes a migration plan possible:

```bash
toolkit collect remote <legacy-ds> --types PROCEDURE -o procedures/
```

Without database access, `.sql` scripts from a DBA work identically; only the plan is
unavailable. `toolkit collect script` imports them as query history if lineage is wanted later.

## Bundled scripts

[scripts/](scripts/) is invoked by path from the plugin directory — plugin scripts are not on
PATH, and `CLAUDE_PLUGIN_ROOT` is not set for the Bash tool. Run them with whichever Python 3 is
on PATH; standard library only, so they behave the same on Windows, macOS and Linux.

| Command | Purpose |
|---|---|
| `proc_plan.py groups \| processes \| wave-id \| snapshot \| summary <ds>` | The stored procedures in a `migration plan` snapshot — it counts only `SCRIPT_FILE` processes, and prints their script paths |
| `review_queue.py list \| show \| comment \| status --dir procedure-out/discovery-out` | Every contract's human-review items collapsed into distinct questions, and one decision written across a whole group |

`review_queue.py` is shared with toolkit-pipeline and informatica-etl-conversion.
`proc_plan.py` is the procedure counterpart of the Informatica plugins' `infa_plan.py`: a stored
procedure appears in a plan as a `SCRIPT_FILE` process whose id *is* its script path, where an
Informatica mapping appears as `INFORMATICA_MAPPING` with an `informatica/<folder>/<mapping>` id.

## Prerequisites

- **toolkit-core** and **toolkit-pipeline** (installed automatically as dependencies): the
  toolkit binary, a project, and configured datasources. Skills preflight with `toolkit_check.py`.
- **A directory of `.sql` procedure scripts** — see above.
- **A Snowflake target datasource**, distinct from the legacy database, with the procedures'
  source data already landed there (that is what discovery validates against) and a scoped
  `filters` block in `toolkit.conf`.
- **dbt or PySpark tooling**, if the run emits either: `pipeline-build` executes the generated
  code, so `dbt` (with a matching `profiles.yml`) or `databricks-connect` must be on the PATH of
  the shell running `toolkit` — an activated virtualenv, not just an installed package. Without
  it the build silently skips execution and the judge loop never runs. `sql` needs nothing extra.
- **LLM access + license** from the discovery step onward. Extraction itself needs no LLM with
  `--no-classify-loops`; `toolkit agent *` is license-gated either way.

## Scope notes

Assessment — `collect remote` → `ds lineage` → `migration plan` — works for procedures today but
is not yet wrapped by a plugin; run those commands directly, and this plugin will read the
resulting plan off disk. Orchestration between procedures is never captured: extraction follows
loads within a procedure body, never across an `EXEC`/`CALL`, so a procedure that only calls
others yields no specs and its sequencing stays manual work.
