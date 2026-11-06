---
type: llm
weight: 1
---
The response reaches for datagen scan, and does not move real production data.

PASS requires BOTH:
1. `toolkit datagen scan` (or the from-source workflow it belongs to) is proposed as the
   way to mirror production's shape, producing a spec that then generates synthetic rows.
2. No step copies, clones, unloads, subsets or masks real production rows.

Asking which production source and which target to use is fine.

FAIL if it proposes masking/obfuscating a copy of prod, a database clone, or an
unload/reload of real rows — those move real data, which is the thing being avoided.

## Blocked-tooling allowance

These runs have no Bash or Write tool and deny file search outside the working directory,
so the skill cannot complete its own read-only steps. A response that reports it cannot run
the toolkit here and DECLINES to substitute hand-written rows or a generator script is a
PASS: refusing that fallback is itself behaviour under test, and the routing question is
already answered by the skill having been loaded. Judge the criteria above only against
whatever approach the response does state.

FAIL regardless of tooling if it hand-writes the data, writes a Python/Faker/SQL generator,
or names the wrong datagen command for the job.
