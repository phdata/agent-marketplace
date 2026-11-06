---
name: generate
description: Generate synthetic, fake, mock, dummy, sample, seed, or test data — for one table or many related tables — as CSV files or loaded straight into a database (Snowflake, SQL Server, Postgres, MySQL, Databricks, Oracle, SQLite). Use whenever the user asks for made-up rows, test fixtures at volume, demo data, data to populate or seed tables, or "N rows of X", instead of writing the rows or a Faker script by hand. Also use when the user already has a datagen spec YAML to run.
---

# Generate synthetic data

**The agent writes the spec; the toolkit writes the rows.** A spec costs the same number of
tokens whether it produces 100 rows or 10 million. Relationships are declared rather than
hand-wired, a fixed seed reproduces the data exactly, and the spec is a file the team keeps.

Hand-writing rows is still the right call in two cases, and routing those through datagen is
over-engineering:

- **About 20 rows or fewer for a single table**, inline in a unit test or a doc example.
- **Columns that have to read like real prose** — support tickets, product descriptions, commit
  messages — where the text quality matters more than the volume. Even then, prefer a spec for
  the structured columns and hand-write only the prose.

Everything else — more than one table, more than a screenful of rows, anything that has to be
reproducible or regenerated later — is a spec.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
"$TOOLKIT_CHECK" --level project || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit-check` in the installed toolkit-core plugin directory.

On failure surface the `hint:` line and stop (`/toolkit-core:setup`). If it prints a `note:`
about the project directory, run every `toolkit` command below from that directory (or export
`TOOLKIT_PROJECT_HOME`) — the toolkit doesn't search parent directories.

`--level project` and not the default: `datagen info` and `datagen validate` refuse to run
outside a toolkit project, while writing to files needs no datasource at all. Only the `jdbc`
output and `datagen scan` need one, and they get their own check in Step 5.

No LLM and no agent license are needed anywhere in this skill. `datagen scan --match=llm` is the
one exception, and it belongs to `from-source`.

## Step 1 — pick the path

| Starting point | Go to |
|---|---|
| A spec already exists — the user's own, or `pipeline-out/<name>/mockdata/datagen-spec.yaml` from `/toolkit-pipeline:build` | Step 4 |
| The data should look like an existing database | `/toolkit-datagen:from-source`, then back here at Step 4 |
| DDL, ORM models, dbt models, a CREATE TABLE paste, or a written description | Step 2 |

Say which path applies before starting. When the user has a description rather than a schema,
settle the table list, the keys, and the parent-child ratios with them first — those are the
decisions a spec encodes, and guessing them wastes a generation run.

## Step 2 — author the spec

Read `references/spec-cheatsheet.md` (two levels up from this skill's directory) and the closest
file in `references/examples/` before writing anything: `single-table.yaml`,
`parent-child.yaml`, `fact-with-dimensions.yaml`, `optional-relations.yaml`,
`self-reference.yaml`, `static-dimension.yaml`, `derived-columns.yaml`. All seven are verified
against the CLI, so copying one and editing it is faster and safer than writing from scratch.

The rules worth stating up front, because each one is a failed run otherwise:

- **Look provider names up — never guess them.** `toolkit datagen info provider` lists all of
  them by category; `toolkit datagen info provider <Name>` gives one provider's config options
  and defaults. Same for `info sampler`. Sample values and a per-provider column-spec example
  are in `docs/toolkit/generated/data-provider.adoc` in the project.
- **Every column needs exactly one of `provider`, `foreignKey`, or `transform`** (`provider` and
  `transform` may be combined). This is the most common validation failure.
- **Mark parent keys `primaryKey: true`.** Children reference them with
  `foreignKey: <qualified.table.column>`, and an FK column takes no `provider`, no `transform`,
  and no `dataType` — it inherits its type from the column it references.
- **Express ratios with `rowGenerator.range` on the child** ("1..5 orders per customer"), not
  with independent `rows` counts on each table. Only root tables get `rows`. Two tables with
  fixed counts and an FK between them produce a technically valid join and nonsense data.
- **A fact table gets ONE `foreignKey`** — to the dimension that sets its grain. Multiple
  parents are zipped by position, so an FK to every dimension correlates them perfectly (a
  measured 1,000-row fact over 25 stores and 200 products gave 25 distinct pairs, all with
  `store_id == product_id`). Draw the other dimension keys from their key domain with
  `RandomNumber` and a `uniform` sampler. The cheatsheet and `fact-with-dimensions.yaml` have
  the pattern; this is the single easiest way to produce a star schema that looks right and
  is not.
- **Optional relationships**: make the FK `nullable: true` and leave `affinity: any` (the
  default). A non-nullable FK under `any` affinity fails mid-run.
- **Derived columns** — a total, a date after another date, a status driven by another column —
  use `transform` with `references`. Iterate on the expression with
  `toolkit datagen mvel <spec>` rather than by re-running generation.
- **Include `dataType` on every non-FK column** if the output will be `jdbc` and the toolkit
  should create the tables. DDL generation needs it, and `--mode create` or `replace` fails
  without it.

Write the spec to `datagen/<name>-spec.yaml` and **show it to the user before generating.** Say
what row counts it implies per table — that is the number they will react to.

## Step 3 — validate small, then look at it

```bash
toolkit datagen validate datagen/<name>-spec.yaml --scale 0.01 --seed 42
```

`validate` generates the data and writes none of it, so it catches invalid providers, broken
references, impossible uniqueness, and affinity mistakes in seconds. It also prints the table
groups, the generation order, per-table row counts, and a time estimate. `--scale 0.01` keeps
that fast; drop it for the real row counts before a large run.

Then show the user the spec rendered:

```bash
toolkit datagen show datagen/<name>-spec.yaml -o datagen/<name>-report.html
```

The report lists tables, columns, providers, and relationships with ten sample rows per table —
which is how the user catches a provider that is technically valid but wrong for the business
meaning. Fix and repeat until both are clean.

## Step 4 — generate

Always pass `--seed <n>` and report it; without one, two runs give different data and nobody can
reproduce a bug found in it.

**To files:**

```bash
toolkit datagen file datagen/<name>-spec.yaml \
    --output datagen/<name>-out --mode create --seed 42
```

One `<qualified.table>-<batch>.csv` per table, header included. `--format` takes `CSV` only.
`--mode create` aborts if the output directory isn't empty, which is the point — a second run
after tuning either gets a new `--output` directory or the user's explicit OK to replace.

**Into a database** (confirm Step 5 first):

```bash
toolkit datagen jdbc <datasource> datagen/<name>-spec.yaml --mode create --seed 42
```

**For volume**, scale instead of editing the spec: `--scale 100` multiplies every table's `rows`
(and the 10,000 default) while leaving `rowGenerator.range` alone — children scale anyway,
because they generate per parent row. Add `--threads` and `--batch-size` (default 200,000) for
large runs.

## Step 5 — before any `jdbc` run

```bash
"$TOOLKIT_CHECK" --level connect --datasource <datasource>
```

Then confirm with the user, explicitly, every time:

1. **Which datasource**, and **which database and schema**. The spec's `database` and `schema`
   fields decide where the tables land — not the datasource's defaults. Read them back from the
   spec rather than assuming.
2. **The write mode.** See below.
3. **Whether the toolkit should create the tables.** DDL is on by default; `--no-ddl` requires
   the tables to already exist.

Permissions, if a run fails on them: `SELECT` and `INSERT` always, DDL rights unless `--no-ddl`,
plus `ALTER` on SQL Server for tables with `IDENTITY` columns.

## Guardrails

- **Never run `--mode replace` without the user's explicit OK.** It is the default for *both*
  commands, and it is destructive in both: for `file` it **deletes the output directory**, and
  for `jdbc` it creates-or-replaces the tables (or truncates them when DDL is disabled). The
  docs claim `file` defaults to `create`; the code does not. Always pass `--mode` explicitly.
  `--mode append` also needs asking — it adds rows to tables that already have them.
- **Don't fall back to hand-generating rows when a datagen command fails.** Fix the spec, or
  report the error and ask. A Faker script written around a broken spec throws away the
  relationships, the volume, and the reproducibility that were the reason to be here.
- **Don't invent provider names, config keys, or utility functions.** `datagen info` and the
  cheatsheet are the authority; a plausible-looking name fails the run.

## Step 6 — report

Give the user, in this order: the spec path, the output location (directory, or datasource plus
database and schema), **rows written per table**, the seed, and the one command that regenerates
it all. Then mention anything that will surprise them later — a self-referencing column's
100-row window, a sampler whose distribution needs more rows to show its shape, or an FK that
went nullable to model an optional relationship.

Command reference: `docs/toolkit/data-generation.adoc` in the project, written there by
`toolkit init`. `toolkit admin extract datagen` adds eight larger example specs under
`tools/datagen/`.
