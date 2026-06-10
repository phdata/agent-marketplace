---
name: spec
description: Author or validate a DiscoveryConfig dataspec — the YAML describing a target table (columns, grain, business rules, load strategy) consumed by toolkit agent discovery. Use when the user wants to define a new pipeline target, has a dataspec to check, or asks what a dataspec needs to contain.
---

# Author a dataspec

A dataspec is one YAML file per target table. Full field reference: the plugin's
`references/spec-schema.md` (two levels up from this skill's directory); complete examples per
tooling under `references/examples/`. Read the schema reference before writing anything.

## If the user already has a YAML

Read it and validate against the schema reference:

- `content` present and substantive (target table + columns + grain + rules)?
- `tooling`/`materialization` combination legal (per-tooling enums)?
- `loadStrategy` keys spelled right (`type`, `change_detection`, `watermark_column`, ...)?
- `targetPlatform` consistent with tooling (pyspark → databricks unless they know better)?
- No hand-written `targetRequirement`/`resolvedTransformation` (producer-only fields)?

Report problems with concrete fixes; small gaps (missing grain, vague rules) matter more than
formatting — discovery quality tracks spec quality.

## If authoring from scratch — interview, then write

Gather, in order (skip what the user already said):

1. **Tooling**: `sql`, `dbt`, or `pyspark` — what should pipeline-build emit?
2. **Target platform**: `snowflake` or `databricks` (pyspark defaults to databricks).
3. **Target table**: name plus database/schema.
4. **Content** — the heart of the spec:
   - If the user has DDL for the target, paste it in and set `format: ddl`.
   - Otherwise `format: natural_language`: columns (name, source or "derived from X",
     nullability), the grain ("one row per ..."), and business rules (derivations, filters,
     SCD expectations). Push for the grain and rules — they drive the generated tests.
5. **Materialization + load strategy**: offer defaults — dimensions:
   `materialization: merge` + `loadStrategy.type: incremental_merge` with
   `change_detection: watermark`; append-only facts: `incremental_append`; small/reference
   tables: `full_refresh`/`ctas`.
6. **Context**: where the source data lives (database/schema/tables, source system names).
   This steers discovery's search — and if the datasource has a `filters` block in
   `toolkit.conf`, that bounds what discovery can see at all.

Write the file as `specs/<target_table>.yaml` in the working directory (one spec per target
table), show it to the user, and point at `/toolkit-pipeline:discover` as the next step.
