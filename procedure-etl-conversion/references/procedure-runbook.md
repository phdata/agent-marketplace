# Stored-procedure conversion runbook

Mechanics behind `/procedure-etl-conversion:convert`.

## What the toolkit supports, exactly

Both of these are closed sets enforced in the extractor, not preferences:

| | Supported | Not supported |
|---|---|---|
| Source dialect | `mssql` (T-SQL), `oracle` (PL/SQL) | everything else `--source-dialect` accepts for other platforms — teradata, hana, postgres, netezza, redshift, bigquery, … (Teradata is a special case: see below) |
| Target platform | `SNOWFLAKE` | `DATABRICKS`, which the Informatica path *does* support |

The refusals read:

```
Procedure extraction reads stored procedures; the source dialect must be mssql or oracle (got teradata).
Procedure extraction currently supports only the Snowflake target platform (got databricks).
```

So "we also have Teradata procedures" or "we're landing on Databricks" is a conversation to have
before starting, not a flag to find. There is no partial path: the extractor parses the
procedure body with a dialect-specific grammar, and the two it has are T-SQL and PL/SQL.

## How deterministic it actually is

`ProcLineageWalker` walks each parsed procedure body, follows its `IF`s and loops to find the
statements that load tables, resolves each load's column lineage, and hands the SQL to
`sql-translation-next`. No LLM anywhere in that. Each spec carries the resulting transformation
as the authoritative one, which is why discovery consumes the spec's target requirement verbatim
instead of LLM-parsing free text the way it does for Informatica.

The single exception is the **loop classifier**: one LLM call per loop that could not be
extracted as a single SQL statement, asking how it should be rewritten set-based and attaching a
hint to the spec. `--no-classify-loops` turns it off and makes extraction completely LLM-free
and offline.

| Stage | LLM | License |
|---|---|---|
| `collect remote --types PROCEDURE` | no | no |
| `etl-extract --etl-platform=procedure --no-classify-loops` | **no** | yes (`agent *` is gated) |
| `etl-extract` with loop classification | one call per unextractable loop | yes |
| `agent discovery` | yes — source proposal, joins, assertions (spec parsing is skipped) | yes |
| `agent pipeline-build` | yes | yes |

## Directory layout

```
procedures/                          the .sql scripts, from collect remote or a DBA
procedure-out/
  etl-extract-dryrun.log             tee'd cost preview  (the only record of it)
  etl-extract.log                    tee'd extraction    (the only record of unparsed files)
  etl-specs/                         <schema>.<procedure>__<target>.discovery.yaml
  etl-specs/*.needs-review.txt       one per target the extractor handed to a human
  discovery-out/<spec-stem>/         data-contract.json + discovery-report.txt
  pipeline-out/<spec-stem>/          build-report.txt, transforms/, tests/, mockdata/
  conversion-report.md               human deliverable; nothing parses it
```

In planned mode, stage each group's scripts into their own directory and give the group its own
output root, e.g. `waves/w<N>-<group>/`, so a re-cut plan cannot strand finished work.
`proc_plan.py wave-id <wave> '<group>'` produces the directory-safe name.

## Procedures to specs is not one-to-one

- **One spec per `(procedure, target)`.** A procedure that loads four tables yields four specs.
- **Branches consolidate.** A procedure whose `IF` arms load the same target more than once gets
  one spec per consolidated arm, so the file name may carry an arm suffix. List the directory;
  never assume the names.
- **Orchestrators yield nothing.** A procedure whose body is a sequence of `EXEC`/`CALL`
  statements has no loads of its own. Extraction follows loads *within* a body, never across a
  call into another procedure. That is expected — and it is also the orchestration that nobody
  converts, so it belongs in the report as manual work.
- **Unparseable files are warned about on the console only.** Hence the `tee`. The run's closing
  summary line counts them alongside translation failures, targets skipped for an unsupported
  statement shape, procedural-loop specs, and targets handed to human review — and that line is
  the only place several of those numbers appear.
- **`*.needs-review.txt`** is written beside the specs for each target the extractor would not
  guess at. It is a deliberate hand-off, not an error; read it before deciding the procedure
  converted cleanly.

## Procedure parameters

A load whose predicate depends on a procedure parameter keeps it as a parameter, with whatever
value was supplied as its default.

```bash
--parameter 'SCHEMA_NAME=STAGING'      # repeatable; wins over --parameter-file
--parameter-file params.txt            # a PowerCenter- or IICS-shaped parameter file
```

A value that names a schema or table is substituted into the spec; a runtime value stays a
parameter with that value as its default. Worth settling before extraction, because a parameter
that should have been a schema name produces specs pointing at the wrong place.

## Target filtering

Extraction skips, by default, targets that are by-products rather than business output:

| Shape | Examples | Flag to keep them |
|---|---|---|
| Staging | `STG_*`, `STAGING_*`, `S_*` | `--include-staging` |
| Audit | `BATCH_*`, `*_AUDIT`, `*_LOAD_DETAIL`, `*_ERROR_LOG`, `*_PROCESS_HISTORY`, `*ETL_PARAMETERS`, `*ETL_RUN_ID`, anything containing `audit` | `--include-audit` |
| Flat files | file exports rather than tables | `--include-flat-files` |

Per-name overrides: `--include-target <regex>` keeps one the heuristics would skip,
`--exclude-target <regex>` drops one they would keep, and **exclude wins**. Both match the whole
name, case-insensitively, and both are repeatable.

## Review queue tags

A review item is `{"description": "...", "comment": ""}`, plus a `resolverNote` once a sweep has
refused to apply its comment. The kind is a bracket tag at the front of the description.

```bash
python3 <plugin>/scripts/review_queue.py list    --dir procedure-out/discovery-out
python3 <plugin>/scripts/review_queue.py show    <group>
python3 <plugin>/scripts/review_queue.py comment <group> "decision" --dir procedure-out/discovery-out
python3 <plugin>/scripts/review_queue.py status  --dir procedure-out/discovery-out
```

| Tag | What discovery is asking |
|---|---|
| `[LOW CONFIDENCE]` | It found a source column but isn't sure it's the right one |
| `[UNMAPPED]` | It found no source for a target column |
| `[MULTIPLE CANDIDATES]` | Several plausible sources; confirm the one it picked is authoritative |
| `[COMPLEX TRANSFORM]` | Business logic it won't guess at — verify the expression |
| `[JOIN FAILED]` | A join path it couldn't validate against real data; match rates are in the description |
| `[ASSERTION FAILED]` | Its proposed mapping contradicts the spec's example records |
| `[LOAD STRATEGY]` | An incremental load with no change-detection method chosen |
| `[SPEC AMBIGUITY]` | An ambiguity carried from the spec — about the procedure's intent, not the warehouse |
| `[PROCEDURAL LOOP]` | **Procedure-specific.** The source ran this load row by row; the translated loop is reference only, and the pipeline must be built set-based from the mappings and the rewrite hint |
| `[LOOP REWRITE HINT]` | **Procedure-specific.** The loop classifier's verdict on a loop that *does* fit a set-based model: `<CATEGORY> (<confidence> confidence): <rewrite form> — <rationale>`, sometimes with a `Fallback:`. Only present when `--classify-loops` was on. It is an answer, not a question — read it, confirm the rewrite form is right for the data, and say so rather than re-deriving it |

A `[PROCEDURAL LOOP]` item is the one tag that is not a question about the warehouse. It is the
honest output of a cursor loop that could not be reduced to a statement, and the answer is
either the rewrite hint the classifier attached or a human deciding how the set-based version
should behave. Never resolve it by pasting the loop back in.

## Resume and redo

| Situation | What happens |
|---|---|
| `procedure-out/` exists | Resume: skip extraction if `etl-specs/` has specs, discovery per spec if its `data-contract.json` exists, build per contract if its `build-report.txt` exists |
| User wants a clean redo | They delete the directory themselves — the skill never deletes |
| Procedures re-collected mid-migration | Re-run extraction; specs are overwritten per `(procedure, target)`, and a target that no longer exists leaves a stale spec behind, so prefer a fresh output directory |
| Contract already approved | The `--resolve` sweep passes it through unchanged; safe to include in every sweep |

## Teradata BTEQ — assessable, not convertible

Worth stating plainly, because it is the obvious next question. Teradata **is** supported by the
toolkit, just not by this conversion path:

| | Teradata BTEQ |
|---|---|
| `collect script` import | **yes** — the docs say "Supported for imported script files, including BTEQ scripts" |
| `ds lineage` → `migration plan` | **yes** — BTEQ scripts land as `SCRIPT_FILE` processes, the same kind as stored procedures, so `proc_plan.py` lists them |
| `sql translate` (Teradata → Snowflake SQL) | **yes** — a supported source dialect |
| `etl-extract --etl-platform=procedure` | **no** — refused outright; the extractor's grammars are T-SQL and PL/SQL |

So a Teradata estate can be collected, lineage-extracted, planned, scored and had its SQL
translated — what it cannot get is the deterministic procedure-to-dataspec extraction and the
discovery/pipeline-build chain that follows. Point users at `/toolkit-pipeline:spec` plus
`sql translate` for that work, and do not reach for `--source-dialect=teradata` here.

Two fidelity caveats on BTEQ lineage, from the script collector, since they decide how much a
plan built from BTEQ is worth:

- `.IMPORT` / `.EXPORT` / `.RUN` reference external files. They are **surfaced as warnings** and
  never stored, so file-based data movement is invisible to the graph — read those warnings.
- `.IF ... THEN <sql>` embedded SQL is conditional and is **skipped with the command**, so
  conditional loads yield no edges. `.LOGON` / `.LOGDATA` are skipped without echoing their text,
  which is the right call for credentials but means the connection context is absent too.

## What this plugin deliberately does not do

- **Assessment.** `collect remote` → `ds lineage` → `migration plan` works for procedures today,
  but no plugin wraps it yet; run those three commands directly. This plugin reads the resulting
  plan off disk if it is there.
- **Teradata BTEQ**, per the section above — assessable and translatable, not convertible here.
- **SSIS packages.** `collect remote --types SSIS` sweeps them from MSDB/SSISDB on SQL Server and
  `etl-extract` has no SSIS platform — SSIS is assessable, not convertible, today.
- **Informatica**, which has its own pair of plugins, including an `informatica-iics` platform
  that `informatica-etl-conversion` does not yet wrap.
