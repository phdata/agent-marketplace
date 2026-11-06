# toolkit-datagen eval suite

Nine cases for `claude plugin eval`, covering the question this plugin exists to answer:
**does a request phrased in the user's own words reach the right skill, and stay away from it
when it shouldn't?**

```bash
# from the repo root
claude plugin eval ./toolkit-datagen --runs 3 --ablation none --trust-plugin -j 3
```

| Case | Should |
|---|---|
| `fake-customers-orders-csv` | fire `generate` — "50k rows of fake customers and their orders as CSV" |
| `seed-dev-postgres` | fire `generate` — seed a dev database from attached DDL, via `datagen jdbc` |
| `star-schema-demo` | fire `generate` — a fact plus three dimensions |
| `employees-with-managers` | fire `generate` — a self-referencing hierarchy |
| `run-existing-spec` | fire `generate` — run a spec the user already has |
| `synthetic-schema-copy` | fire `from-source` — "synthetic copy of our FINANCE schema" |
| `like-prod-not-prod` | fire `from-source` — "looks like prod but isn't prod" |
| `skip-unit-test-fixture` | **not** fire — three rows in a test fixture |
| `skip-prose-email` | **not** fire — one piece of prose where writing quality is the point |

Each case has two graders: a `tool_used` grader (the trigger check — `Skill` called at least
once for the seven positives, exactly zero times for the two negatives) and an `llm` grader on
the approach the response states.

## Two things to know before you trust a result

**1. The dependency has to be stripped, or nothing loads.** `toolkit-datagen` declares a
dependency on `toolkit-core`. The eval harness runs each case in a sandboxed HOME, so a
`claude plugin install toolkit-core` on the host is invisible inside it, and the plugin fails to
load with `dependency-unsatisfied` — **every skill is then unregistered and all seven positive
cases report `Skill called 0x`**, which looks exactly like a triggering failure and is not one.
Until the harness can resolve plugin dependencies for an inline target, evaluate a copy with the
`dependencies` block removed:

```bash
cp -R toolkit-datagen /tmp/dg-eval
python3 -c "import json;p='/tmp/dg-eval/.claude-plugin/plugin.json';d=json.load(open(p));d.pop('dependencies',None);json.dump(d,open(p,'w'),indent=2)"
claude plugin eval /tmp/dg-eval --runs 3 --ablation none --trust-plugin -j 3
```

Triggering depends on the skills' frontmatter, not on the dependency block, so this does not
weaken the trigger check. Check `plugin_errors` in a run's `trace.jsonl` (via `--keep-temp`) if
a result looks wrong.

**2. The sandbox cannot run the skills' own steps.** Cases allow `[Read, Glob, Grep, Skill]` —
no Bash, no Write — and file search outside the working directory is denied. So the agent cannot
run `toolkit datagen info provider`, validate a spec, write one to disk, or even read this
plugin's `references/`. Roughly one run in three therefore ends at "I can't run the toolkit
here, and the skill says not to hand-write rows instead" — which is the guardrail working. The
`llm` graders carry an explicit allowance for that, so they grade **routing and the no-fallback
guardrail**, not the quality of a generated spec. Spec quality is covered instead by the seven
examples under `references/examples/`, each verified against the real CLI.

Granting `Bash` would change what is being measured: the agent would need a real toolkit
install, a configured datasource, and permission to write to it.

## Expected results

Last full run (3 runs per case, `--ablation none`): **triggering 9/9 across all 27 runs** — every
positive fired a skill, neither negative did. Content graders: eight cases at 1.00,
`run-existing-spec` at 0.83 (one run reported the spec was missing from disk without naming
`datagen jdbc`).

So `--threshold 1.0` (the default) will fail the suite on normal run-to-run variance. Use
`--threshold 0.8` in CI, and read the `tool_used` graders as the real pass/fail signal — those
are the acceptance criterion. The `llm` graders are deliberately strict enough to fail
sometimes; a suite that is green by construction measures nothing.

Judge votes come from `haiku` by default (`--judge-model` to change it). A full 27-run pass costs
roughly $2–3.
