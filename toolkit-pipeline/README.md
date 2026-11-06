# toolkit-pipeline

Dataspec-driven pipeline generation with the phData Toolkit agent stack.

```
dataspec (YAML, one per target table)
   │   /toolkit-pipeline:spec — author or validate
   ▼
toolkit agent discovery <ds> <spec> --output discovery-out/<name>
   │   proposes source→target mappings against the live datasource,
   │   emits data-contract.json + discovery-report.txt
   ▼
human review loop                                /toolkit-pipeline:discover
   │   fill humanReviewItems[].comment, re-run with --resolve,
   │   repeat until approvedByHuman
   ▼
toolkit agent pipeline-build <ds> --contract ... --output pipeline-out/<name>
   │   /toolkit-pipeline:build
   ▼
DDL + initial/incremental transforms + data-quality tests + datagen spec
(sql, dbt, or pyspark — chosen in the dataspec, locked into the contract)
```

## Skills

| Skill | Purpose |
|---|---|
| `/toolkit-pipeline:spec` | Author or validate a DiscoveryConfig dataspec |
| `/toolkit-pipeline:discover` | Dataspec → data contract, with the grouped human-review queue and resolve loop |
| `/toolkit-pipeline:build` | Approved contract → pipeline code, tests, datagen spec |

The dataspec field reference and per-tooling examples live in [references/](references/).

## Bundled scripts

[scripts/](scripts/) is invoked by path from the plugin directory — plugin scripts are not on
PATH, and `CLAUDE_PLUGIN_ROOT` is not set for the Bash tool.

| Command | Purpose |
|---|---|
| `review_queue.py list [--dir discovery-out] [--all]` | Every contract's human-review items collapsed into one numbered list of distinct questions, biggest group first |
| `review_queue.py show <group>` | Every item in one group, with its contract, description, comment, and resolver note |
| `review_queue.py comment <group> "decision"` | Write one decision into every item in a group, across every contract that has it |

It exists because the review queue is mostly repeats — the same idiom across many target
tables — and `--resolve` applies one comment per item, so a single decision broadcast across a
group is the cheap path through a long queue. Python 3 standard library only (no jq), so it
behaves the same on Windows, macOS, and Linux.

The `mockdata/datagen-spec.yaml` that `build` emits per contract is a starting point, not a
finished spec — [toolkit-datagen](../toolkit-datagen/) tunes and runs it (and handles synthetic
data requests that have nothing to do with a pipeline).

## Prerequisites

- **toolkit-core** (installed automatically as a dependency): toolkit binary, project, and a
  configured datasource. Skills preflight with `toolkit_check.py`.
- **Platform**: the pipeline process supports **Snowflake and Databricks** only (datasource and
  `targetPlatform`). The other JDBC types toolkit-core can connect serve the broader toolkit
  workflows (scan/profile/diff/translate), not this plugin.
- **LLM access**: `toolkit agent *` commands call an LLM. With no `llmClient` block in
  `toolkit.conf` the toolkit falls back to Amazon Bedrock through the phData auth flow; non-phData
  users configure a provider with `/toolkit-core:llm` (Bedrock/OpenAI/Anthropic).
- **License**: agent commands are license-gated (`verifyAgentAccess`).
- Keep datasource `filters` scoped in `toolkit.conf` — discovery scans/profiles live on each run.

## Scope (v1)

This plugin starts from a dataspec the user supplies or authors interactively. The toolkit's
warehouse-wide modeling agents — `agent discovery-build` (index) and `agent data-modeling`
(model design from a use case) — are intentionally out of scope here; see the toolkit repo's
`demo/agent-pipeline` for the full-stack walkthrough that includes them. A future version may
add an indexed mode (`--use-index`) on top of these skills.
