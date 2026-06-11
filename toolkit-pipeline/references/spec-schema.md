# DiscoveryConfig dataspec reference

The dataspec is the YAML file consumed by `toolkit agent discovery <datasource> <spec.yaml>`.
It describes ONE target table: what it should contain, where the data comes from, and how it
should be built. Discovery resolves it against the live datasource into a reviewable data
contract; `toolkit agent pipeline-build` then generates the code from that contract.

The schema is polymorphic on `tooling` — that field selects the output flavor and unlocks a few
tooling-specific keys. Enum values are case-insensitive (`merge` and `MERGE` both parse).

## Common fields (all tooling types)

| Field | Required | Values / notes |
|---|---|---|
| `tooling` | no (default `sql`) | `sql`, `dbt`, `pyspark` |
| `content` | **yes** | The spec itself: target table, columns, grain, business rules. Free text — see `format`. |
| `format` | no (default `natural_language`) | `natural_language`, `ddl`, `example_records`, `erwin`, `mixed` — how to interpret `content` |
| `context` | no | Domain context: source systems, where the data lands (database/schema), source-table hints |
| `systemContext` | no | Extra system-level context passed to the LLM |
| `targetPlatform` | no | `snowflake`, `databricks`. Defaults: `snowflake` for sql/dbt, `databricks` for pyspark |
| `materialization` | no | Per-tooling, see below |
| `loadStrategy` | no | See below |

Per-tooling `materialization` values:

| tooling | materialization |
|---|---|
| `sql` | `merge`, `insert`, `ctas`, `dynamic_table` |
| `dbt` | `table`, `view`, `incremental`, `ephemeral` |
| `pyspark` | `merge`, `overwrite`, `append`, `ignore` (Spark write modes) |

## `loadStrategy`

```yaml
loadStrategy:
  type: incremental_merge        # full_refresh | incremental_append | incremental_merge
  change_detection: watermark    # watermark | cdc_column | hash_diff
  watermark_column: updated_at   # when change_detection = watermark
  cdc_type_column: op_type       # when change_detection = cdc_column
  cdc_delete_value: D            # value in cdc_type_column that marks deletes
  soft_delete_column: is_deleted # when delete_handling = soft_delete
  delete_handling: ignore        # ignore | soft_delete | hard_delete
```

All keys optional except `type` once the block is present. Sensible defaults when omitted
entirely: discovery picks a strategy and records its reasoning in the contract.

## Tooling-specific fields

- `dbt` only: `dbtProfile` — dbt profile name to reference in generated artifacts.
- `pyspark` only: `computeType` (`serverless` default, or `cluster`) and `clusterId`
  (needed when `computeType: cluster` — the parser doesn't enforce it up front).

## Advanced producer fields (normally omit)

`targetRequirement` and `resolvedTransformation` are populated by upstream toolkit agents
(e.g. `agent data-modeling`, `agent etl-extract`), not by hand. Constraint:
`resolvedTransformation` requires `targetRequirement` — emit both or neither. Hand-authored
specs should use `content`/`context` and let discovery do the analysis.

## Writing good `content`

Whatever the `format`, discovery needs to learn from `content`:

1. **Target table** (name, and database/schema if not implied by the datasource)
2. **Columns** — names, types if known, nullability, and for each either a source reference or
   a note that it's derived (and from what)
3. **Grain** — what one row means (drives uniqueness tests)
4. **Business rules** — derivations, filters, SCD expectations, exclusions

`context` should say where source data lives (database/schema/tables) so discovery searches the
right place — and if the datasource has a `filters` block in `toolkit.conf`, that bounds what
discovery can see at all.

Complete examples: [examples/sql-spec.yaml](examples/sql-spec.yaml),
[examples/dbt-spec.yaml](examples/dbt-spec.yaml),
[examples/pyspark-spec.yaml](examples/pyspark-spec.yaml).
