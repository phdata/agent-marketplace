---
type: llm
weight: 1
---
The response seeds the database through datagen, and the `sale` rows join to both parents.

These runs have no Bash tool, so the `toolkit datagen` commands cannot actually run. Judge
the APPROACH. Two responses must both PASS: one that writes the spec and names the commands
to run, and one that explains it cannot run them here and states the spec and commands it
would use. Refusing to substitute hand-written INSERTs or a generator script when datagen
cannot run is correct behaviour, not a failure.

PASS requires ALL:
1. A datagen data spec, or `toolkit datagen` commands, as the mechanism.
2. `toolkit datagen jdbc` identified as the way to load Postgres — not only CSV files.
3. Every `sale` row carries a valid `store_id` AND a valid `product_id`. Any of these
   satisfies it:
   - a foreignKey to one parent plus the other key drawn from that parent's key domain
     (e.g. RandomNumber bounded by its row count) — the better answer, since datagen zips
     multiple parents positionally and would otherwise correlate them;
   - foreign keys to both parents; or
   - foreign keys to both plus an explicit note about the positional zipping.

Credit, but never require: `dataType` on non-FK columns for DDL generation, confirming the
target datasource/database/schema first, avoiding the destructive default write mode, or a
`--seed`.

FAIL if it hand-writes INSERT statements, writes a generator script, proposes CSV as the
only output, or leaves either key unable to join (e.g. a random product_id outside the
product table's key range).

## Blocked-tooling allowance

These runs have no Bash or Write tool and deny file search outside the working directory,
so the skill cannot complete its own read-only steps. A response that reports it cannot run
the toolkit here and DECLINES to substitute hand-written rows or a generator script is a
PASS: refusing that fallback is itself behaviour under test, and the routing question is
already answered by the skill having been loaded. Judge the criteria above only against
whatever approach the response does state.

FAIL regardless of tooling if it hand-writes the data, writes a Python/Faker/SQL generator,
or names the wrong datagen command for the job.
