---
type: llm
weight: 1
---
The response clones the schema's shape with a datagen scan rather than copying data.

PASS requires BOTH:
1. `toolkit datagen scan` against the FINANCE source is the route to a spec (rather than
   hand-authoring every table, or copying/unloading real rows).
2. A filter scoped to the FINANCE schema is used or called for, rather than scanning the
   whole account.

Credit, but do not require, any of: stating that the scan reads metadata and result-set
types and does not fetch real rows; warning that a scanned spec has no relationships or
row ratios until they are added; retargeting the spec's database/schema to the dev
account before generating.

FAIL if it proposes copying, cloning, unloading or masking the real production rows, or
ignores datagen scan entirely in favour of writing the whole spec by hand.

## Blocked-tooling allowance

These runs have no Bash or Write tool and deny file search outside the working directory,
so the skill cannot complete its own read-only steps. A response that reports it cannot run
the toolkit here and DECLINES to substitute hand-written rows or a generator script is a
PASS: refusing that fallback is itself behaviour under test, and the routing question is
already answered by the skill having been loaded. Judge the criteria above only against
whatever approach the response does state.

FAIL regardless of tooling if it hand-writes the data, writes a Python/Faker/SQL generator,
or names the wrong datagen command for the job.
