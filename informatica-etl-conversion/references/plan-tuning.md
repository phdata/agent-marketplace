# Reading and tuning the migration plan

## What gets written

| Path | What it is |
|---|---|
| `migration-plan/<ds>/plan.txt` | Human rendering — the file to read with the user |
| `migration-plan/<ds>/inventory.csv` | One row per object; for spreadsheets and stakeholder hand-offs |
| `tools/ds/snapshots/migration-plan/<ts>_<ds>.json` | Structured snapshot — the machine-readable source |

`toolkit ds show <ds>:migration-plan:latest` currently **fails** on plans containing
Informatica processes (`Unrecognized field "componentCount"`, all formats), so read the
snapshot JSON straight off disk:

```bash
SNAP=$(ls -1 tools/ds/snapshots/migration-plan/*_<ds>.json | sort | tail -1)
```

Snapshot shape:

```
summary{waveCount, groupCount, tableCount, unparsedPatternCount, diagnosticsCaptured}
waves[]{ number, groups[]{ name, wave, foundation, scores,
                           processes[]{ id, kind, patternCount, tables[], sqlStats, etlStats },
                           tables[]{ name, scores, writerProcesses, columnCount },
                           outboundContracts[] } }
plumbing[]
```

Wave numbers do not necessarily start at 0, and `processes`/`tables` can be absent on a group —
use `(.processes // [])` in every jq expression.

`inventory.csv` columns: `wave, group, object_type, name, kind, patterns, tables, calls,
statements, ctes, fatal_diagnostics, error_diagnostics, components, component_types,
expressions, script_tasks, custom_components, sql_fragments, complexity, priority, risk,
writers, columns, rows`. `object_type` is `PROCESS` or `TABLE`; process rows fill the ETL/SQL
stat columns, table rows fill the score columns.

## Reading plan.txt

1. Header: table/group/wave counts, unparseable pattern count, and the heuristic effects block
   — how many objects were held out and why. When it says a count "rests on naming convention
   alone", check those names against the real naming conventions before trusting them.
2. Wave table: one row per group with complexity, priority, and risk (band plus raw score).
3. Per group: `feeds X: A -> B` contract edges, then the process table, then the table table.

## Dispositions — objects held out of the plan

| Disposition | Meaning | What to do |
|---|---|---|
| `DEAD` | In the scan, absent from lineage, and query history exists — no observed usage | Genuine do-not-migrate candidate; confirm with an owner |
| `SET_ASIDE` | Absent from lineage, but lineage came only from imported files | "Not in the files" ≠ unused (analysts may read it directly) — review, don't schedule |
| `PLUMBING` | Temp/staging table inside a process | Nothing to do; collapsed out of the flow graph |
| `EXTERNAL` | Referenced by lineage but outside what was scanned — the plan calls these "outside the scanned estate" | A dependency callout — someone else owns it |
| `INTERFACE` | A file, queue, or service an ETL package reads or writes | Real work with no warehouse equivalent: rebuild as a stage, external table, unload, or connector |
| `PLACEHOLDER` | An ETL object naming nothing real (port-shape stubs like `DummySource`) | Ignore; held out so it doesn't weld unrelated pipelines together |
| `AUDIT_SINK` | Batch audit, load detail, event log | Written by much of the system and migrated by none of it — replace with the target platform's own observability |
| `EXCLUDED` | Excluded by `--exclude` | User's own call |

## Tuning knobs

| Knob | Default | Reach for it when |
|---|---|---|
| `--max-group-size <tables>` | tuned for large migrations | A group is too big for one team to migrate at once — splits it along the upstream lineage of its final tables. It caps *tables*, not mappings, so a group can still end up mapping-heavy: a real 121-group Teradata plan had one group with 83 Informatica mappings, which is one review queue. Check group sizes before converting |
| `--seed <table>` | none, repeatable | You want a split to fall on a boundary you care about; treats the table as an additional final output |
| `--exclude <table>` | none, repeatable | A table is already migrated or truly retired |
| `--hub-min-readers <count>` | | A widely-read table should (or shouldn't) be promoted into the shared foundation |
| `--hub-min-component-size <tables>` | | Only components at least this large get hub extraction |
| `--hub-max-tables <tables>` | | Cap on the shared-foundation group |
| `--jaccard-merge-threshold <0..1>` | | Two final tables with overlapping upstreams should migrate together (1 = identical upstreams only, 0 = merge anything) |

Small migrations (under ~50 tables) need the thresholds lowered or everything lands in one group:

```bash
toolkit ds migration-plan <ds> --hub-min-component-size 10 --hub-min-readers 4 --max-group-size 8
```

Persistent settings can live in `toolkit.conf` instead of flags, e.g. keeping a shared upstream
chain inside its main consumer's group rather than demoting it to the foundation:

```hocon
ds {
    migrationPlan {
        slicing {
            sharedClosureFraction = 1.0
        }
    }
}
```

Audit-sink name patterns live under `ds.migrationPlan.auditSinks.namePatterns` — worth
adjusting when the audit tables don't match the default naming.

## Re-cutting

Each run overwrites `plan.txt`/`inventory.csv` and adds a snapshot. Re-cutting after wave
execution has begun can rename groups and renumber waves; existing `waves/` directories then
refer to a plan that no longer exists. `/informatica-etl-conversion:status` detects this by
comparing modification times.
