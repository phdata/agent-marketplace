---
name: from-source
description: Create synthetic data shaped like an existing database — same tables, columns, types, and plausible values — without copying real rows, using toolkit datagen scan. Use when the user wants test or demo data "like production", a masked or synthetic copy of a schema, or to seed a dev environment that mirrors another database.
---

# Shape synthetic data like an existing database

`toolkit datagen scan` reads a live database's metadata and writes a data spec that mirrors it:
one table spec per table, one column spec per column, with a data provider guessed per column
from its name and JDBC type. The result is a starting point to correct, not a finished spec —
then `/toolkit-datagen:generate` takes over from Step 3 here.

**What to tell the user up front, because it is the reason to use this rather than a copy:** the
scan reads catalog metadata and JDBC result-set types. It runs a `SELECT` against each matched
table to read the result-set metadata, but **the rows are never fetched**. No production data
leaves the source database, and none of it reaches the generated spec.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
python3 "$TOOLKIT_CHECK" --level connect --datasource <source-ds> || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit_check.py` in the installed toolkit-core plugin directory.

The source needs a real connection — hand off to `/toolkit-core:connect` if there isn't one. The
scanning user needs data-source scan rights plus `SELECT` on every table to be matched.

Establish now whether the **target** is the same datasource, a different one, or files. A
synthetic copy usually lands somewhere else, and the spec's `database`/`schema` fields carry the
source's names unless they are edited.

## Step 1 — scan

```bash
toolkit datagen scan <source-ds> \
    --filter 'PROD_DB.FINANCE.*' \
    --spec datagen/<name>-spec.yaml
```

**Keep the filter tight.** A `SELECT` runs against every matched table, so an unfiltered scan of
a large account is slow and touches far more than the user asked about. Confirm the filter with
the user before running it. Filters take `*` and `?`, up to two periods, and unspecified
namespaces are implicitly included — so `PROD_DB` means `PROD_DB.*.*`. Several `--filter` flags
are allowed and a table needs to match only one.

Without `--spec` the file lands in the current directory as `<source>-spec.yaml`.

Two knobs worth knowing:

- `--min-score <1-100>` (default 50) — the threshold for matching a column to a provider.
  Raise it when the spec comes back with odd provider choices; a column that matches nothing
  falls back to a type-appropriate random provider, which is usually the safer default.
- `--views-as-tables` — include views as table specs. Only when the user actually wants to
  generate into them.
- `--match Score|llm|hybrid` (default `Score`) — `llm` and `hybrid` ask an LLM to match columns
  to providers, which needs a configured LLM client (`/toolkit-core:llm`). Better matches on
  cryptic column names, at the cost of a round trip per batch and a license-gated dependency.
  Start with the default.

## Step 2 — review what the scan could not know

This is the whole job. A scanned spec is structurally right and semantically naive; walk these
four with the user before generating anything.

1. **Relationships.** The scan only knows the foreign keys the source database actually
   declares. Estates that enforce referential integrity in the ETL instead — most warehouses —
   come back with no `foreignKey` at all, which means every table generates independently and
   nothing joins. Ask which columns are really keys, then add `foreignKey` on the child and
   `primaryKey: true` on the parent, and delete the child FK column's `provider`.
2. **Row ratios.** Every scanned table gets an independent row count. Replace the child counts
   with `rowGenerator.range` ("1..5 orders per customer") and leave `rows` only on the roots.
   Without this, a thousand customers and a thousand orders means one order each.
3. **Providers that are wrong for the business meaning.** The classic is a `STATUS` or `TYPE`
   column getting `RandomString` — valid data that no query will ever filter on usefully.
   Replace those with `Enum` and the real value set (with real probabilities, if the user knows
   them), or `FileData` for a long list. The same goes for codes, flags, and anything whose
   domain the user can recite.
4. **Dimensions that must hold real values.** Region names, currency codes, a product catalog:
   point the table at a CSV with `rowGenerator.staticSource` and `provider: StaticSource` on
   those columns. See `references/examples/static-dimension.yaml`.

Also check whether the scanned row counts are what the user wants at all. They describe the
source's shape, not the target's size — `--scale` at generation time is the lever, not editing
every table.

`references/spec-cheatsheet.md` (two levels up from this skill's directory) has the field
reference for all of the above.

## Step 3 — continue in `generate`

Pick up at `/toolkit-datagen:generate` Step 3: validate at `--scale 0.01`, render the HTML
report, show the user, then generate with a reported `--seed`.

One thing to re-confirm there, since the spec came from a real database: the `database` and
`schema` in every table spec are the **source's** names. Generating into the same datasource
with `--mode replace` would overwrite the tables that were just scanned. Edit them to the target's
names, confirm the datasource, and keep `--mode create`.
