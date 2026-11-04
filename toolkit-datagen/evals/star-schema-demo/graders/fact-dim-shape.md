---
type: llm
weight: 1
---
The response plans the star schema as datagen work, and the fact's dimensions end up
INDEPENDENT of each other.

These runs have no Bash and no Write tool, so judge the APPROACH the response states, not
executed output. Laying out the design and asking the user to confirm before generating is
the documented behaviour and passes on that ground alone if the design is right.

PASS requires BOTH:
1. phData Toolkit datagen is the mechanism — a data spec, or `toolkit datagen` commands.
   Spec YAML, or a description of the tables/keys/providers it will contain, both count.
2. The fact can be grouped by any two dimensions independently. Either of these satisfies
   it:
   - ONE foreignKey from the fact to its grain dimension, with the other dimension keys
     drawn from their key domains (e.g. RandomNumber bounded by each dimension's row
     count); or
   - foreign keys to every dimension TOGETHER WITH an explicit acknowledgement that
     multiple parents are zipped positionally and that this correlates the dimensions.

Credit, but never require: a `uniform` sampler on a key draw, a `rowGenerator` range for
fact rows, a date dimension from a sequence provider, `dataType` for DDL generation, or a
`--seed`.

FAIL if it hand-writes rows, writes a Python/Faker/SQL generator, leaves the four tables
with no key linking fact to dimensions at all, or declares a foreignKey to all three
dimensions with no mention of the correlation that causes.

## Blocked-tooling allowance

These runs have no Bash or Write tool and deny file search outside the working directory,
so the skill cannot complete its own read-only steps. A response that reports it cannot run
the toolkit here and DECLINES to substitute hand-written rows or a generator script is a
PASS: refusing that fallback is itself behaviour under test, and the routing question is
already answered by the skill having been loaded. Judge the criteria above only against
whatever approach the response does state.

FAIL regardless of tooling if it hand-writes the data, writes a Python/Faker/SQL generator,
or names the wrong datagen command for the job.
