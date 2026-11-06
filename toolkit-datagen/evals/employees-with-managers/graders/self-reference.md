---
type: llm
weight: 1
---
The response models the manager relationship as a datagen self-reference.

PASS requires BOTH:
1. A datagen data spec (or `toolkit datagen` commands) as the mechanism.
2. The manager link is a foreign key from the employee table back to its OWN key column
   (e.g. `manager_id` with `foreignKey: employee_id`), not a second employee-like table
   and not a randomly generated manager id unconnected to any employee.

Credit, but do not require, either: making `manager_id` nullable so some employees have
no manager, or noting that a self-reference draws from recently generated rows and that
the first row references itself.

FAIL if it hand-writes rows, writes a generator script, or gives managers an id that
does not reference a real employee.

## Blocked-tooling allowance

These runs have no Bash or Write tool and deny file search outside the working directory,
so the skill cannot complete its own read-only steps. A response that reports it cannot run
the toolkit here and DECLINES to substitute hand-written rows or a generator script is a
PASS: refusing that fallback is itself behaviour under test, and the routing question is
already answered by the skill having been loaded. Judge the criteria above only against
whatever approach the response does state.

FAIL regardless of tooling if it hand-writes the data, writes a Python/Faker/SQL generator,
or names the wrong datagen command for the job.
