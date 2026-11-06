---
type: llm
weight: 1
---
The response routes this to phData Toolkit datagen rather than hand-writing data.

PASS requires BOTH:
1. It works toward a datagen data spec (YAML with tables/columns, or `toolkit datagen`
   commands such as validate/file/jdbc) as the way to produce the rows.
2. It treats customers and orders as RELATED tables — a foreign key from orders to
   customers, and/or a per-customer order ratio (rowGenerator range) — rather than two
   independent tables.

FAIL if it writes out CSV rows itself, writes a Python/Faker/SQL generator script, or
only describes generating data with no reference to a data spec or a toolkit datagen
command.

Asking the user clarifying questions first (output location, datasource, schema) is fine
and does not by itself fail, as long as the datagen route is clear.

## Blocked-tooling allowance

These runs have no Bash or Write tool and deny file search outside the working directory,
so the skill cannot complete its own read-only steps. A response that reports it cannot run
the toolkit here and DECLINES to substitute hand-written rows or a generator script is a
PASS: refusing that fallback is itself behaviour under test, and the routing question is
already answered by the skill having been loaded. Judge the criteria above only against
whatever approach the response does state.

FAIL regardless of tooling if it hand-writes the data, writes a Python/Faker/SQL generator,
or names the wrong datagen command for the job.
