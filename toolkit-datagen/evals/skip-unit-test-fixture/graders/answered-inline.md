---
type: llm
weight: 1
---
The response just writes the three fixture rows.

PASS: it produces three additional Python dict literals in the same shape as the existing
row (id, name, tier), ready to paste into the fixture.

FAIL if it proposes a datagen data spec, a `toolkit datagen` command, or any external
generator for three rows, or if it asks the user to install or configure tooling first.
Over-engineering this is exactly the failure mode being tested.
