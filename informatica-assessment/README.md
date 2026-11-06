# informatica-assessment

Survey an Informatica PowerCenter estate with the [phData Toolkit](https://toolkit.phdata.io/docs)
CLI and turn it into a migration plan: dependency-ordered waves, scored groups, an inventory, and
an explicit list of what should not be migrated at all.

Everything here is the **free path** — no LLM, no agent license — and the legacy database is
never connected to unless the user has access and wants a scan. Converting the mappings is the
separate [informatica-etl-conversion](../informatica-etl-conversion/) plugin, which does need
both.

```
a directory of exported PowerCenter XML  →  copied in as informatica-xml/
   │   /informatica-assessment:collect — analyzer recon (export completeness),
   │   collect etl, optional legacy source-database scan
   ▼
toolkit ds lineage <legacy-ds>
   │   /informatica-assessment:lineage — parse-failure triage, spot checks
   ▼
toolkit migration plan <legacy-ds>
   │   /informatica-assessment:plan — waves, groups, held-out objects, tuning loop
   ▼
migration-plan/<ds>/plan.txt + inventory.csv        (the plan of record)
   │
   ▼   /informatica-etl-conversion:wave, one plan group at a time
```

The legacy datasource is never dialed unless asked: a stub connection whose JDBC scheme only
sets the SQL dialect is enough for the whole assessment.

## Skills

| Skill | Purpose |
|---|---|
| `/informatica-assessment:collect` | Copy in the corpus, size it, pick a route; analyzer reconnaissance; `collect etl`; optional legacy source-DB scan |
| `/informatica-assessment:lineage` | Extract lineage, triage SQL parse failures, spot-check dataflows |
| `/informatica-assessment:plan` | Cut and tune the wave plan with `migration plan` |

`:collect` sizes the corpus and, when it's small (around 20 mappings or fewer), asks which route
to take: the full assessment, or skipping straight to conversion. The assessment exists to make
a large migration tractable; on a small one it can be more ceremony than it's worth.

What a usable corpus looks like and what each plan-tuning knob does live in
[references/](references/).

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

Run them with whichever Python 3 is on PATH — `python3` on macOS and Linux, `python` or `py` on
Windows. **Standard library only: no jq, no grep, no packages**, so the skills behave the same on
every platform.

They exist because both patterns are subtle and fail silently when retyped. The mapping regex
must require whitespace after `<MAPPING` (or `<MAPPINGVARIABLE` matches), tolerate `NAME ="x"`
spacing, and anchor on the element rather than a bare `NAME=` (or every workflow scheduling the
mapping matches). The plan snapshot must survive absent `processes`/`tables` keys, wave numbering
that may or may not start at 0, and groups holding SQL scripts or no processes at all.
`infa_plan.py` reads the snapshot JSON off disk because `toolkit migration show` cannot deserialize a
plan containing Informatica processes.

informatica-etl-conversion ships the same two scripts, so either plugin stands alone.

## Prerequisites

- **toolkit-core** (installed automatically as a dependency): the toolkit binary, a project, and
  a datasource entry for the legacy database. Skills preflight with `toolkit_check.py`.
- **Legacy source dialect** must be one of oracle, mssql, teradata, snowflake, databricks — the
  dialects the collect store parses. Anything else can't be collected today.
- **Database access is optional.** A stub connection assesses a legacy database entirely
  offline; `ds lineage --offline` is then required, since a stub URL must never be dialed.
- **No LLM, no agent license.** Nothing here calls `toolkit agent *`.

## Scope

Informatica PowerCenter, starting from an export someone hands you: workflow XML for
orchestration context, mappings for the conversion that follows. Producing the export
(Repository Manager, `pmrep objectexport`) is the Informatica team's job, not a step here.

SSIS `.dtsx` packages are also assessable with `collect etl --type=SSIS`, and are
deliberately **not** wrapped here — use the CLI directly, or a future sibling plugin. The naming
is specific on purpose: a generic ETL-assessment plugin invites wandering off the documented
path.

Orchestration is not part of the plan. `analyzer-out/dependency.txt` from the collect step is
the workflow → session → mapping record, and rebuilding schedules from it is a manual exercise.
