# informatica-etl-conversion

Convert a set of Informatica PowerCenter mappings into Snowflake or Databricks pipelines with
the [phData Toolkit](https://toolkit.phdata.io/docs) CLI — a large migration wave by wave, a
small one in a single pass.

`:collect` sizes the corpus and asks which route to take when it's small (around 20 mappings
or fewer): the full assessment below, or a direct conversion that skips straight to `:wave`.

## Phase A — assess (free path: no LLM, no agent license)

```
a directory of exported PowerCenter XML  →  copied in as informatica-xml/
   │   /informatica-etl-conversion:collect — analyzer recon, ds collect etl,
   │   optional legacy source-database scan
   ▼
toolkit ds lineage <legacy-ds>
   │   /informatica-etl-conversion:lineage — parse-failure triage, spot checks
   ▼
toolkit ds migration-plan <legacy-ds>
   │   /informatica-etl-conversion:plan — waves, groups, held-out objects, tuning loop
   ▼
migration-plan/<ds>/plan.txt + inventory.csv        (the plan of record)
```

The legacy datasource is never connected to unless the user has access and wants a scan — a
stub connection whose JDBC scheme only sets the SQL dialect is enough for the assessment.

## Phase B — convert, one plan group at a time

```
plan group ──► staged XML subset ──► toolkit agent etl-extract      (dry-run cost gate)
   ▼
one dataspec per (mapping, target) ──► toolkit agent discovery <target-ds> per spec
   ▼
grouped review queue: aggregate humanReviewItems across the group's contracts,
decide by category, write comments, --resolve sweep, repeat until approved
   ▼
toolkit agent pipeline-build per approved contract
   ▼
waves/w<N>-<group>/wave-report.md            /informatica-etl-conversion:status
```

## Skills

| Skill | Purpose |
|---|---|
| `/informatica-etl-conversion:collect` | Copy in the corpus, size it, pick a route; analyzer reconnaissance; `ds collect etl`; optional legacy source-DB scan |
| `/informatica-etl-conversion:lineage` | Extract lineage, triage SQL parse failures, spot-check dataflows |
| `/informatica-etl-conversion:plan` | Cut and tune the wave plan with `ds migration-plan` |
| `/informatica-etl-conversion:wave` | Convert one plan group end to end — or the whole corpus in direct mode — with the grouped review queue |
| `/informatica-etl-conversion:status` | Progress across the whole conversion, and what to run next |

What a usable corpus looks like, the plan-tuning knobs, and the wave runbook live in
[references/](references/).

## Bundled scripts

[scripts/](scripts/) holds the parsing the skills would otherwise retype. Invoked by path from
the plugin directory — plugin scripts are not on PATH, and `CLAUDE_PLUGIN_ROOT` is not set for
the Bash tool.

| Command | Purpose |
|---|---|
| `infa-corpus count \| list [corpus-dir]` | Mappings in the export corpus (default `./informatica-xml`) |
| `infa-corpus find <mapping> [corpus-dir]` | Which XML file(s) contain a mapping |
| `infa-plan groups <ds>` | TSV of wave, group, Informatica mappings, tables |
| `infa-plan processes <ds> <wave> <group>` | Mapping names in one plan group |
| `infa-plan wave-id <wave> <group>` | Directory-safe name for a group's wave directory |
| `infa-plan snapshot <ds>` | Path to the newest migration-plan snapshot |

They exist because both patterns are subtle and fail silently when retyped: the mapping regex
must keep the space after `<MAPPING` (or `<MAPPINGVARIABLE` matches), tolerate `NAME ="x"`
spacing, and anchor on the element rather than a bare `NAME=` (or every workflow scheduling the
mapping matches). The plan snapshot must survive absent `processes`/`tables` keys and wave
numbering that may or may not start at 0. `infa-plan` reads the snapshot JSON directly because
`toolkit ds show` cannot deserialize a plan containing Informatica processes.

## Prerequisites

- **toolkit-core** and **toolkit-pipeline** (installed automatically as dependencies): the
  toolkit binary, a project, and configured datasources. Skills preflight with `toolkit-check`.
- **Legacy source dialect** must be one of oracle, mssql, teradata, snowflake, databricks — the
  dialects the collect store parses. Database access is optional; a stub connection assesses an
  legacy database offline.
- **Target platform**: Snowflake or Databricks, with the mappings' source data already landed
  there — that's what discovery validates against.
- **dbt or PySpark tooling**, if the wave emits either: `pipeline-build` executes the generated
  code, so `dbt` (with a matching `profiles.yml`) or `databricks-connect` must be on the PATH of
  the shell running `toolkit` — an activated virtualenv, not just an installed package. Without
  it the build silently skips execution and the judge loop never runs. `sql` tooling needs
  nothing extra.
- **LLM access + license** for Phase B only. `toolkit agent *` commands call an LLM (Bedrock
  fallback via phData auth, or configure a provider with `/toolkit-core:llm`) and are
  license-gated. All of Phase A and `status` run without either.

## Scope

Informatica PowerCenter is the whole scope, starting from an export someone hands you:
workflow XML for orchestration context, mappings for conversion. Producing the export
(Repository Manager, `pmrep objectexport`) is the Informatica team's job, not a step here.

Two adjacent paths the toolkit CLI supports are deliberately **not** wrapped here — SSIS
`.dtsx` packages (assessable via `ds collect etl --type=SSIS`) and SQL Server
stored procedures (`agent etl-extract --etl-platform=procedure`); use the CLI directly, or a
future sibling plugin.

Within a converted wave, orchestration is not generated: `agent etl-extract` works at mapping
level and doesn't capture workflow or session names. `analyzer-out/dependency.txt` from the
collect step is the record for rebuilding schedules by hand.
