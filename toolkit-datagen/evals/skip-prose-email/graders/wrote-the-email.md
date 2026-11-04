---
type: llm
weight: 1
---
The response writes the email.

PASS: it contains an actual customer complaint email in prose — something that reads like
a person wrote it, covering the damaged order and the earlier unanswered contact.

FAIL if it instead proposes a datagen data spec, a `toolkit datagen` command, or a
generator for the email text, or asks the user to configure tooling first.
