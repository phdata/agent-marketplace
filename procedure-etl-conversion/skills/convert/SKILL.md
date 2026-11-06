---
name: convert
description: Convert SQL Server (T-SQL) or Oracle (PL/SQL) stored-procedure ETL into Snowflake pipelines end to end — agent etl-extract --etl-platform=procedure parses each procedure and emits one dataspec per target table, agent discovery resolves them against the warehouse, a grouped review queue drives the contracts to approved, then agent pipeline-build generates the code. Use when the user wants to migrate, convert or rewrite stored procedures, T-SQL or PL/SQL ETL, or a legacy procedure-based warehouse load, for one migration-plan group or a whole set at once.
---

# Convert: stored procedures → generated pipelines

`agent etl-extract --etl-platform=procedure` is **deterministic**. It parses each procedure
body, walks its `IF`s and loops to find the statements that actually load tables, resolves each
load's column lineage, and translates the SQL with `sql-translation-next` — no LLM. Each emitted
spec carries the authoritative transformation, so discovery consumes it verbatim instead of
re-interpreting prose.

That makes this a different proposition from the Informatica path: extraction can be run
**entirely LLM-free** (`--no-classify-loops`), and what it produces is a translation rather than
a guess. The LLM and the agent license are still needed from Step 5 onward, because discovery
and pipeline-build need them.

Runs in one of two modes:

- **Planned** — one **migration-plan group** per run, when a plan exists. Stored procedures
  appear in a plan as `SCRIPT_FILE` processes whose id is the script's path.
- **Direct** — no plan; every procedure in the input directory is converted in one run. The
  normal starting point, since no plugin currently produces the plan for procedures (see
  "Where the procedures come from" below).

```bash
ls -d migration-plan/*/ 2>/dev/null
```

A plan present means planned mode, but **ask rather than assume** — a user may have one and
deliberately not be following it.

## Step 0 — the two hard constraints

Settle these before anything else. Both are enforced by the toolkit and both fail the run:

- **Source dialect must be `mssql` or `oracle`.** Nothing else. The extractor's supported set is
  exactly those two, and anything else is refused with "Procedure extraction reads stored
  procedures; the source dialect must be mssql or oracle". Never guess which one: parsing PL/SQL
  as T-SQL, or the reverse, fails in ways that read like a broken procedure rather than a wrong
  flag. Ask, or read it off the datasource.
- **Target platform must be Snowflake.** "Procedure extraction currently supports only the
  Snowflake target platform." Databricks works for Informatica but **not** for procedures — if
  the user wants Databricks, stop here and say so rather than starting a run that cannot finish.

If either is wrong, say which one and stop. Everything below assumes both hold.

**Teradata comes up here constantly, so know the answer:** BTEQ scripts *are* supported by the
toolkit — `collect script` imports them, `ds lineage` and `migration plan` read them, and
`sql translate` converts their SQL — but **not by this path**. There is no deterministic
procedure extraction for Teradata, because the extractor's grammars are T-SQL and PL/SQL. Say
what *is* possible rather than just refusing; `references/procedure-runbook.md` has the
breakdown and the two BTEQ lineage caveats worth repeating.

## Step 1 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
python3 "$TOOLKIT_CHECK" || exit
python3 "$TOOLKIT_CHECK" --list-datasources
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit_check.py` in the installed toolkit-core plugin directory.

- **Target datasource**: the Snowflake account the pipelines are built against. This is a
  *different* datasource from the legacy SQL Server or Oracle database the procedures came from.
  Confirm which it is with the user rather than inferring it from the datasource list, then
  probe it: `python3 "$TOOLKIT_CHECK" --level connect --datasource <target-ds>`.
- **Target datasource filters**: discovery scans and profiles the warehouse live on *every*
  spec, so an unscoped datasource makes each run slow and lets unrelated tables compete as
  candidates. Confirm a `filters` block naming the landing database and schema
  (`grep -A 4 'filters' toolkit.conf`); `/toolkit-core:connect` writes it.
- **Tooling environment**, if the answer to tooling is dbt or pyspark: `pipeline-build` executes
  the generated code and resolves the tool on the PATH of the shell running `toolkit`, so the
  virtualenv must be **activated in that shell**. `which dbt` / `which databricks-connect`.
  Missing, the build still "succeeds" with execution marked `SKIPPED` and the judge loop never
  engages. `sql` tooling needs nothing extra.
- **LLM access and license** are needed for Step 5 and Step 7, not for extraction. With no
  `llmClient` block the toolkit falls back to Amazon Bedrock via the phData auth flow;
  others configure a provider with `/toolkit-core:llm`. `toolkit agent *` is license-gated.
- **Resume**: if the output directory already exists, resume by skipping stages whose artifacts
  are present. Never delete one; a clean redo is the user's own `rm`.

## Step 2 — where the procedures come from

Extraction takes a path to a `.sql` file or a directory of them. There are two ways to get
there, and the choice has consequences worth stating:

**With access to the legacy database** — collect the DDL, which also stores it for lineage:

```bash
toolkit collect remote <legacy-ds> --types PROCEDURE -o procedures/
```

This writes one `.sql` file per object and imports the DDL into the collect store, where
`ds lineage` can read it directly with no script-import step. That is what makes a migration
plan possible later. Add `--types TABLE,VIEW,PROCEDURE` when the plan should see the tables too.

**Without database access** — a DBA hands over `.sql` scripts. Extraction works on them exactly
the same way; only the plan is unavailable, because nothing collected them. `toolkit collect
script` can import them as query history if lineage is wanted later.

Either way, confirm what arrived before spending a run:

```bash
ls procedures/*.sql | wc -l
```

Procedures that call other procedures matter here: the extractor follows loads *within* a
procedure body, not across a `CALL`/`EXEC` into another one. A procedure that is only an
orchestrator — a sequence of `EXEC` calls — yields no loads of its own, which is expected and
not a failure. Surface those to the user as the orchestration that still needs rebuilding, the
same way a workflow does.

**Planned mode** additionally needs the group's procedures:

```bash
python3 <plugin>/scripts/proc_plan.py groups    <legacy-ds>
python3 <plugin>/scripts/proc_plan.py processes <legacy-ds> <wave> '<group>'
```

Bundled in this plugin's `scripts/` directory (two levels up from this skill's directory);
invoke it by path, since plugin scripts aren't on PATH. Python 3 standard library only. It
prints each procedure's script **path**, because a `SCRIPT_FILE` process id *is* that path —
match them to the files on disk by basename if the directory has moved since the plan was cut.
Stage the group's files into their own directory and run extraction over that.

## Step 3 — dry run

```bash
toolkit agent etl-extract procedures/ \
    --etl-platform=procedure \
    --source-dialect=<mssql|oracle> \
    --target-platform=SNOWFLAKE \
    --dry-run 2>&1 | tee procedure-out/etl-extract-dryrun.log
```

The dry run parses everything, reports the unique-expression count and the projected LLM call
count, and writes nothing. For procedures that projected count is **only the loop classifier**:
one call per loop that could not be extracted as a single SQL statement. With
`--no-classify-loops` it is zero.

Show the user the counts, then settle two things:

1. **The filtered targets.** Extraction skips staging-shaped (`STG_`, `STAGING_`, `S_`),
   audit-shaped (`BATCH_*`, `*_AUDIT`, `*_LOAD_DETAIL`, `*_ERROR_LOG`, `*_PROCESS_HISTORY`,
   ETL run-control tables, anything containing `audit`) and flat-file targets by default,
   because they are by-products of the ETL rather than its business output. Confirm that is
   right for this set, or re-run with `--include-staging`, `--include-audit`,
   `--include-flat-files`, or the per-name `--include-target <regex>` /
   `--exclude-target <regex>` (exclude wins).
2. **Loop classification.** `--classify-loops` is the default and is the *only* LLM use in
   extraction. Keep it when the procedures contain cursor loops — the hint it attaches is what
   tells `pipeline-build` how to rewrite the loop set-based. Pass `--no-classify-loops` for a
   fully deterministic, zero-cost, offline extraction, accepting that unextractable loops arrive
   without a rewrite hint.

## Step 4 — extract the specs

```bash
toolkit agent etl-extract procedures/ \
    --etl-platform=procedure \
    --source-dialect=<mssql|oracle> \
    --target-platform=SNOWFLAKE \
    [--tool=SQL|DBT|PYSPARK] [--dbt-profile <name>] \
    [--no-classify-loops] \
    --output procedure-out/etl-specs 2>&1 | tee procedure-out/etl-extract.log
```

`--tool=DBT` requires `--dbt-profile`. The `tee` is load-bearing: files that could not be parsed
are warned about on the console and recorded nowhere else — read the log and surface every
skipped procedure by name.

Extraction finishes with a single summary line that is the whole report on what happened —
read it out, because several of its counts appear nowhere else:

```
Extracted 1 procedure(s) from 1 file(s) → 1 spec task(s); 0 parse failure(s), 0 translation
failure(s), 0 target(s) skipped (unsupported statement shape), 0 procedural-loop spec(s),
0 target(s) handed to human review (*.needs-review.txt).
```

Any non-zero count there is a thing to surface: a **parse failure** is a procedure the grammar
could not read, a **translation failure** is SQL it read but could not translate, a target
**skipped (unsupported statement shape)** is a load whose statement the walker could not reduce,
and a target **handed to human review** gets a `*.needs-review.txt` file written beside the
specs. Read those files — they are the extractor saying plainly that something needs a person.

Then review the specs with the user before spending discovery. One spec per `(procedure,
target)` pair, named `<schema>.<procedure>__<target>.discovery.yaml` (e.g.
`dbo.usp_load_customer__dim_customer.discovery.yaml`); **list the directory rather than assuming
the names**, since a procedure whose branches load the same target more than once gets one spec
per consolidated arm.

```bash
ls procedure-out/etl-specs/*.discovery.yaml
ls procedure-out/etl-specs/*.needs-review.txt 2>/dev/null
```

What to look at, and what is specific to procedures:

- **The loads found per procedure.** A procedure that writes four tables yields four specs. If a
  procedure you expected to see produced none, that is the thing to investigate: it is usually
  an orchestrator, or its writes are inside a construct the walker could not reduce to a
  statement.
- **Procedure parameters.** A load whose predicate depends on a parameter keeps it as a
  parameter with the supplied value as its default. `--parameter NAME=VALUE` (repeatable, wins
  over everything) and `--parameter-file <file>` set them. A parameter naming a schema or table
  is substituted into the spec; a runtime value stays a parameter.
- **Loops.** Each is either extracted as a set-based statement, or flagged. A flagged loop that
  the classifier could rewrite carries a hint; one it could not is marked for human review.
  Neither is a failure — both are the honest answer, and both surface again in Step 6.
- **The translated SQL.** Deterministic does not mean infallible: the translation is
  `sql-translation-next`'s, and the spec keeps enough context to judge it — each column
  derivation carries its `kind`, a `confidence`, the generated `sql`, and the `original`
  expression next to it, which is what to compare. Spot-check the gnarliest procedure rather
  than all of them.
- **Column types are not in the spec.** A procedure declares no types for its target columns, so
  the emitted DDL lists bare column names and says so: "Column types are not declared in the
  procedure; resolve them against the source catalog." Discovery resolves them against the
  warehouse in Step 5 — which is another reason a spec whose sources have not landed yet comes
  back looking worse than it is.

## Step 5 — discovery

One output subdirectory per spec — discovery always writes `<output-dir>/data-contract.json`,
so a shared directory clobbers:

```bash
for f in procedure-out/etl-specs/*.discovery.yaml; do
  name=$(basename "$f" .discovery.yaml)
  [ -f "procedure-out/discovery-out/$name/data-contract.json" ] && continue   # resume
  toolkit agent discovery <target-ds> "$f" --output "procedure-out/discovery-out/$name"
done
```

Because a procedure spec carries a structured target requirement, discovery **skips the LLM
spec-parsing step** and consumes it verbatim; the source-proposal, join-validation and
assertion agents still run and still cost LLM calls. Each run scans and profiles the warehouse
live, bounded by the `filters` confirmed in Step 1.

A spec whose source tables have not been landed in Snowflake yet does not fail loudly — it comes
back with failed assertions and low-confidence mappings that read like problems with the
procedure. If a contract looks inexplicably bad, check whether its sources arrived before
spending review time on it.

## Step 6 — the grouped review queue

The queue is mostly repeats: the same idiom appears across many procedures, so one decision
resolves many items.

```bash
python3 <plugin>/scripts/review_queue.py list --dir procedure-out/discovery-out
python3 <plugin>/scripts/review_queue.py show <group>
python3 <plugin>/scripts/review_queue.py comment <group> "<the user's decision>" \
    --dir procedure-out/discovery-out
```

It collapses every contract's `humanReviewItems` into distinct questions, biggest first, and
`comment` writes one decision into every member item across every affected contract. Always
`show` a group before deciding, to confirm it really is one question. The tags, and the two that
only procedures produce, are tabulated in `references/procedure-runbook.md`.

Then sweep:

```bash
for f in procedure-out/etl-specs/*.discovery.yaml; do
  name=$(basename "$f" .discovery.yaml)
  contract="procedure-out/discovery-out/$name/data-contract.json"
  [ -f "$contract" ] || continue
  toolkit agent discovery <target-ds> "$f" --resolve "$contract"
done
```

The positional datasource and spec are required by the CLI but ignored on the resolve path. Each
commented item is all-or-nothing: one whose amendments contradict an earlier item's change is
left open with a `resolverNote`, which `review_queue.py list` flags as `NOT APPLIED`. Items that
ask for the same change are all applied, which is why broadcasting one decision is safe.
Re-queue and repeat until every contract reports `approvedByHuman: true`
(`review_queue.py status --dir procedure-out/discovery-out`).

## Step 7 — build

```bash
for d in procedure-out/discovery-out/*/; do
  name=$(basename "$d")
  contract="$d/data-contract.json"
  [ -f "procedure-out/pipeline-out/$name/build-report.txt" ] && continue      # already built
  python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("approvedByHuman") else 1)' \
      "$contract" || continue                                                 # unapproved
  toolkit agent pipeline-build <target-ds> \
      --contract "$contract" --output "procedure-out/pipeline-out/$name"
done
```

The approval guard is the loop's, not a matter of remembering: anything it skips goes back
through Step 6. `--force-unresolved` overrides it only with the user's explicit OK and produces
code embedding unreviewed guesses. Read every `build-report.txt` — judge failures and exhausted
retries belong in the report, not glossed over. For dbt and pyspark, check the `EXECUTION`
section too: `SKIPPED` means the tool was not on PATH and nothing ran.

For the generated output's layout, the `--max-retries` / `--llm-effort` knobs, and the optional
apply / seed / test follow-ups, use `/toolkit-pipeline:build` — the mechanics are identical.
For tuning and running the emitted `mockdata/datagen-spec.yaml`, use `/toolkit-datagen:generate`.

## Step 8 — report

Write `procedure-out/conversion-report.md`: procedures read and procedures that yielded no
loads, specs emitted per procedure, targets skipped as staging/audit/flat-file, procedures that
failed to parse, loops extracted set-based versus flagged, contracts approved, pipelines built,
and judge failures. Finish with what is still someone's manual problem — the orchestration
between procedures, which extraction never sees, and in direct mode the deployment order, which
nothing analyzed.

## Guardrails

- **Never hand-translate a procedure when extraction fails.** Fix the input, the dialect or the
  flags, or report the failure and ask. A hand-written translation throws away the determinism
  that is the entire reason to use this path.
- **Never silently fall back to Databricks or another dialect.** Both constraints in Step 0 are
  refusals from the toolkit, not preferences.
- **A loop marked for human review is a decision, not a defect.** Row-by-row logic that cannot
  be expressed set-based is exactly what a human should see; present it rather than inventing a
  rewrite.

Command reference for `etl-extract`, `discovery` and `pipeline-build`: `docs/toolkit/agent.adoc`,
written into the project by `toolkit init`.

Then `/procedure-etl-conversion:status` for the whole-conversion picture.
