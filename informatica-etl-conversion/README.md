# informatica-etl-conversion

Convert a set of Informatica PowerCenter mappings into Snowflake or Databricks pipelines with
the [phData Toolkit](https://toolkit.phdata.io/docs) CLI — one migration-plan group at a time
for a large estate, or the whole corpus in a single pass for a small one.

Assessing the estate first — lineage, dependency-ordered waves, an inventory — is the separate
[informatica-assessment](../informatica-assessment/) plugin. This plugin reads its
`migration-plan/<ds>/` output off disk if it's there and needs nothing else from it: **direct
mode is a complete path on its own.**

```
plan group (optional) ──► staged XML subset ──► toolkit agent etl-extract   (dry-run cost gate)
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

Planned mode converts one plan group per run; a wave is its groups in sequence. Groups within a
wave are independent by construction, which also makes one group the right size for a single
review queue. Direct mode converts everything in `informatica-xml/` in one run into
`waves/all/`, and leaves deployment sequencing as someone's manual problem — the thing the
assessment would have answered.

## Skills

| Skill | Purpose |
|---|---|
| `/informatica-etl-conversion:wave` | Convert one plan group end to end — or the whole corpus in direct mode — with the grouped review queue |
| `/informatica-etl-conversion:status` | Progress across the whole conversion, and what to run next |

The wave runbook — directory layout, mapping-to-file matching, multi-mapping files, the review
queue's tags, resume and redo — is in [references/](references/).

## Bundled scripts

[scripts/](scripts/) holds the parsing the skills would otherwise retype. Invoked by path from
the plugin directory — plugin scripts are not on PATH, and `CLAUDE_PLUGIN_ROOT` is not set for
the Bash tool.

| Command | Purpose |
|---|---|
| `infa_corpus.py count \| list [corpus-dir]` | Mappings in the export corpus (default `./informatica-xml`) |
| `infa_corpus.py find <mapping> [corpus-dir]` | Which XML file(s) contain a mapping |
| `infa_plan.py groups <ds>` | TSV of wave, group, Informatica mappings, tables |
| `infa_plan.py processes <ds> <wave> <group>` | Mapping names in one plan group |
| `infa_plan.py wave-id <wave> <group>` | Directory-safe name for a group's wave directory |
| `infa_plan.py snapshot <ds>` | Path to the newest migration-plan snapshot |
| `infa_plan.py summary <ds>` | The plan's summary block (wave/group/table counts) |
| `review_queue.py list \| show \| comment \| status --dir <wave>/discovery-out` | The wave's human-review items collapsed into distinct questions, and one decision written across a whole group |

Run them with whichever Python 3 is on PATH — `python3` on macOS and Linux, `python` or `py` on
Windows. **Standard library only: no jq, no grep, no packages**, so the skills behave the same on
every platform. `review_queue.py` is shared with toolkit-pipeline, whose `discover` skill runs
the same review loop for a plain dataspec run.

The `infa_*` scripts exist because both patterns are subtle and fail silently when retyped. The
mapping regex must require whitespace after `<MAPPING` (or `<MAPPINGVARIABLE` matches), tolerate
`NAME ="x"` spacing, and anchor on the element rather than a bare `NAME=` (or every workflow
scheduling the mapping matches). The plan snapshot must survive absent `processes`/`tables` keys,
wave numbering that may or may not start at 0, and groups holding SQL scripts or no processes at
all. `infa_plan.py` reads the snapshot JSON off disk because `toolkit migration show` cannot deserialize
a plan containing Informatica processes.

informatica-assessment ships the same two scripts, so either plugin stands alone.

## Prerequisites

- **toolkit-core** and **toolkit-pipeline** (installed automatically as dependencies): the
  toolkit binary, a project, and configured datasources. Skills preflight with `toolkit_check.py`.
- **The corpus** in `informatica-xml/`, structure as exported. `:wave` copies it in if the
  assessment plugin hasn't already.
- **Target platform**: Snowflake or Databricks, with the mappings' source data already landed
  there — that's what discovery validates against. The target datasource is a *different* one
  from the legacy datasource used for assessment, and wants a scoped `filters` block.
- **dbt or PySpark tooling**, if the wave emits either: `pipeline-build` executes the generated
  code, so `dbt` (with a matching `profiles.yml`) or `databricks-connect` must be on the PATH of
  the shell running `toolkit` — an activated virtualenv, not just an installed package. Without
  it the build silently skips execution and the judge loop never runs. `sql` tooling needs
  nothing extra.
- **LLM access + license.** `toolkit agent *` commands call an LLM (Bedrock fallback via phData
  auth, or configure a provider with `/toolkit-core:llm`) and are license-gated. `status` runs
  without either, as does all of informatica-assessment.

## Scope

Informatica PowerCenter mappings are the whole scope. Two adjacent paths the toolkit CLI
supports are deliberately **not** wrapped here — SSIS `.dtsx` packages and SQL Server stored
procedures (`agent etl-extract --etl-platform=procedure`); use the CLI directly, or a future
sibling plugin. The naming is specific on purpose: a generic ETL-conversion plugin invites
wandering off the documented path.

Within a converted wave, orchestration is not generated: `agent etl-extract` works at mapping
level and doesn't capture workflow or session names. `analyzer-out/dependency.txt` from
`/informatica-assessment:collect` is the record for rebuilding schedules by hand.
