---
name: build
description: Run toolkit agent pipeline-build to generate pipeline code from approved data contracts — SQL, dbt, or PySpark transforms plus data-quality tests and a synthetic-data (datagen) spec. Use after discovery produces contracts, or when the user wants to generate, regenerate, apply, or test pipelines from contracts.
---

# Build: data contract → pipeline code

`toolkit agent pipeline-build` generates, per contract: DDL, initial + incremental load
transforms, data-quality test SQL, and a datagen spec for synthetic test data — in the tooling
(sql/dbt/pyspark) recorded in the contract. A judge-feedback loop re-runs validations until the
generated code passes or retries are exhausted.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
"$TOOLKIT_CHECK" || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit-check` in the installed toolkit-core plugin directory.

On failure surface the `hint:` line and stop. If it prints a `note:` about the project
directory, run every `toolkit` command below from that directory (or export
`TOOLKIT_PROJECT_HOME`). Same LLM + license prerequisites as discovery
(Bedrock fallback for phData users, `/toolkit-core:llm` to configure another provider;
`toolkit agent *` is license-gated).

**Tooling on PATH (dbt and pyspark contracts).** The build doesn't just generate code — it
executes it against an ephemeral schema in the datasource, and that's what the judge loop
grades. The runner resolves the tool with `which`, against the PATH of the shell running
`toolkit`:

| Contract tooling | Needs on PATH | What it runs |
|---|---|---|
| `sql` | nothing extra | statements over JDBC |
| `dbt` | `dbt` | `dbt deps`, then `dbt build --vars '{schema: <ephemeral>}'` (plus `--profile` from the contract) in the transforms directory |
| `pyspark` | `databricks-connect` | `python3 <each>.py` with `PIPELINE_BUILD_SCHEMA` / `_DATABASE` / `_CLUSTER_ID` in the environment |

So a virtualenv holding dbt or databricks-connect must be **activated in the shell that runs
`toolkit agent pipeline-build`** — not merely installed somewhere. Check before building:

```bash
which dbt                  # dbt contracts   — also needs a profiles.yml matching the contract's profile
which databricks-connect   # pyspark contracts — also needs its cluster/workspace config
```

If the tool isn't found, the build **does not fail**: execution is marked `SKIPPED`, and
because the judge-feedback loop only re-runs on `ERROR` or `FAIL`, it never engages. The result
is generated, never-executed, never-corrected code with a clean-looking report. Tell the user
before spending the run, not after.

Then verify the contract(s): each `discovery-out/<name>/data-contract.json` should have
`approvedByHuman: true` / empty `humanReviewItems`. If review items remain, send the user back
to `/toolkit-pipeline:discover` (Step 3) — or, only with their explicit OK, pass
`--force-unresolved` and note the generated code will embed unreviewed guesses.

## Step 1 — build

One output subdirectory per contract:

```bash
for d in discovery-out/*/; do
  name=$(basename "$d")
  toolkit agent pipeline-build <datasource> \
      --contract "$d/data-contract.json" \
      --output "./pipeline-out/$name"
done
```

Knobs worth mentioning when relevant: `--max-retries N` (judge-feedback attempts, default 3;
0 disables), `--llm-effort None|Low|Medium|High` (default Low — raise for gnarly transforms).
Tooling comes from the contract, not a flag.

## Step 2 — review the output

Typical per-table layout under `pipeline-out/<name>/` (sql tooling shown):

```
build-report.txt                 # what was generated, judge verdicts, retries
build-result.json
judge-report-attempt-<n>.json    # one per judge attempt
transforms/ddl/create_<name>.sql # plus sequences etc. when the design needs them
transforms/transform/initial_load_<name>.sql
transforms/transform/incremental_load_<name>.sql
tests/                           # data-quality test SQL from the contract's assertions
tests/test-config.yaml
mockdata/datagen-spec.yaml       # synthetic-data spec for toolkit datagen
```

Test file paths are agent-chosen and vary by run and tooling (`tests/sql/`, bare `tests/`, or
for dbt nested under `tests/tests/` with companion YAML) — list the directory rather than
assuming. Full-refresh tables get a single `load_<name>.sql` instead of the
initial/incremental pair.

Read `build-report.txt` first — surface judge failures or exhausted retries to the user rather
than presenting the code as clean. Check its `EXECUTION` section too: a status of `SKIPPED`
with a warning like `dbt is not installed or not on PATH` means nothing was ever run, so the
judge verdict above it rests on code review alone. Fix the environment and rebuild rather than
reporting that pipeline as validated. Then walk the transforms: does the incremental load respect
the contract's load strategy (watermark/merge keys)? Do the tests cover the grain and not-null
assertions?

## Step 3 — optional next actions (each touches the datasource — confirm first)

- **Apply** DDL and initial load:
  `toolkit ds exec <datasource> --file pipeline-out/<name>/transforms/ddl/create_<name>.sql`
  then the `initial_load_*.sql` transform.
- **Seed synthetic data** (e.g. into a dev/test schema):
  `toolkit datagen jdbc <datasource> pipeline-out/<name>/mockdata/datagen-spec.yaml`
- **Run the generated tests**:
  `toolkit ds exec <datasource> --file <a test .sql under pipeline-out/<name>/tests/>` — a
  failing test returns rows; empty results mean pass.

Command reference: the `pipeline-build` section of `docs/toolkit/agent.adoc`, written into the
project by `toolkit init`.

For dbt contracts, the generated project files belong in the user's dbt repo — offer to move
them and run `dbt parse` if dbt is installed locally.
