---
type: llm
weight: 1
---
The response runs an EXISTING spec into Snowflake, safely, without rewriting it.

These runs have no Bash tool and the spec is pasted rather than on disk, so the command
cannot actually run. Judge the APPROACH. A response that stops to confirm the target or
reports that it cannot run the command in this session must PASS, provided it names the
right command and the right safeguards.

PASS requires BOTH:
1. `toolkit datagen jdbc` (not `file`) is identified as the way to load Snowflake, taking
   the pasted spec as given rather than redesigning it.
2. At least one safeguard before writing: confirming the target datasource, database or
   schema; validating the spec first; or flagging that the write mode defaults to
   `replace` and passing or recommending `--mode create` instead.

Credit, but never require: passing and reporting a `--seed`, or noting that the spec's own
database/schema fields decide where the tables land.

FAIL if it hand-writes INSERTs, converts the spec into a script, redesigns the spec from
scratch, or would fire a destructive `replace` run at the user's database without raising
it.

## Blocked-tooling allowance

These runs have no Bash or Write tool and deny file search outside the working directory,
so the skill cannot complete its own read-only steps. A response that reports it cannot run
the toolkit here and DECLINES to substitute hand-written rows or a generator script is a
PASS: refusing that fallback is itself behaviour under test, and the routing question is
already answered by the skill having been loaded. Judge the criteria above only against
whatever approach the response does state.

FAIL regardless of tooling if it hand-writes the data, writes a Python/Faker/SQL generator,
or names the wrong datagen command for the job.
