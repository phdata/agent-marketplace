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
toolkit-check || exit
```

On failure surface the `hint:` line and stop. If it prints a `note:` about the project
directory, run every `toolkit` command below from that directory (or export
`TOOLKIT_PROJECT_HOME`). Same LLM + license prerequisites as discovery
(Bedrock fallback for phData users, `/toolkit-core:llm` to configure another provider;
`toolkit agent *` is license-gated).

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
than presenting the code as clean. Then walk the transforms: does the incremental load respect
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

For dbt contracts, the generated project files belong in the user's dbt repo — offer to move
them and run `dbt parse` if dbt is installed locally.
