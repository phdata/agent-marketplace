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
| `/toolkit-pipeline:discover` | Dataspec → data contract, with the human-review resolve loop |
| `/toolkit-pipeline:build` | Approved contract → pipeline code, tests, datagen spec |

The dataspec field reference and per-tooling examples live in [references/](references/).

## Prerequisites

- **toolkit-core** (installed automatically as a dependency): toolkit binary, project, and a
  configured datasource. Skills preflight with `toolkit-check`.
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
