---
name: discover
description: Run toolkit agent discovery to resolve a dataspec against a live datasource into a reviewable data contract, then walk the human-review resolve loop until the contract is approved. Use when the user has (or needs) a dataspec and wants source-to-target mappings, or mentions data contracts, discovery, or humanReviewItems.
---

# Discover: dataspec → approved data contract

`toolkit agent discovery` reads a dataspec, scans/profiles the live datasource, proposes
source-to-target column mappings with confidence scores, validates them against real data, and
emits a data contract. Items it isn't confident about are flagged for human review — the loop
below resolves them.

## Step 0 — preflight

```bash
toolkit-check || exit
```

On failure surface the `hint:` line and stop (`/toolkit-core:setup` / `/toolkit-core:connect`).

Additional prerequisites beyond toolkit-check:

- **Platform**: the pipeline process supports Snowflake and Databricks only — both the
  datasource being discovered and the spec's `targetPlatform`. If the user's datasource is
  another type, stop here and explain.
- **LLM access**: agent commands call an LLM. With no `llmClient` block in `toolkit.conf`, the
  toolkit falls back to Amazon Bedrock via the phData auth flow (works out of the box for phData
  consultants). Others need an `llmClient { type = openai|anthropic ... }` block — API key via
  `${ENV_VAR}`, never inline.
- **License**: `toolkit agent *` is license-gated; an authorization error means the user's token
  doesn't include agent access — that's a licensing conversation, not a config bug.
- **Cost note**: without a prebuilt index, each discovery run scans and profiles the datasource
  live. On large or shared warehouses, consider adding a datasource `filters` block in
  `toolkit.conf` to keep that scoped (see `/toolkit-core:connect`).

## Step 1 — locate or author the spec(s)

Ask for the dataspec YAML path(s). If the user doesn't have one, author it with them — the
interview and field reference live in the plugin's `references/spec-schema.md` and
`references/examples/` (two levels up from this skill's directory; same flow as
`/toolkit-pipeline:spec`): tooling,
target platform, target table, content (columns/grain/business rules), materialization + load
strategy, source context. One spec per target table, saved as `specs/<target_table>.yaml`.

## Step 2 — run discovery

One output subdirectory per spec — discovery always writes `<output-dir>/data-contract.json`
(the spec name does not change the filename), so shared dirs clobber each other:

```bash
toolkit agent discovery <datasource> specs/<name>.yaml --output ./discovery-out/<name>
```

For multiple specs, loop:

```bash
for f in specs/*.yaml; do
  name=$(basename "$f" .yaml)
  toolkit agent discovery <datasource> "$f" --output "./discovery-out/$name"
done
```

## Step 3 — review with the user

Read `discovery-out/<name>/discovery-report.txt`. Walk the user through:

- **Column mappings** — flag anything below ~0.7 confidence and any `x`-marked rows
- **ITEMS REQUIRING YOUR REVIEW** — each is a decision discovery refused to guess on:
  `[LOW CONFIDENCE]` mappings, `[COMPLEX TRANSFORM]` business logic, `[ASSERTION FAILED]`
  example-record mismatches, ambiguous sources
- **Warnings** — especially CRITICAL ones about failed assertions

Capture the user's decision on each item in their own words ("the age-band logic is correct,
keep it"; "map channel_code from DIM_CHANNEL.CODE instead").

## Step 4 — resolve

Edit `discovery-out/<name>/data-contract.json`: find each item under
`sourceToTarget.humanReviewItems[]` and write the user's decision into its `comment` field
(leave items the user has no opinion on untouched). Then:

```bash
toolkit agent discovery <datasource> specs/<name>.yaml --resolve ./discovery-out/<name>/data-contract.json
```

The positional datasource/spec arguments are required by the CLI but ignored on the resolve
path — pass the same ones. The resolver applies each comment via the LLM, drops resolved items
from `humanReviewItems`, sets `approvedByHuman: true` when none remain, and rewrites both the
contract and the report in place. Tooling, target platform, and target columns are structurally
locked — comments can't change the target schema. Contracts without comments pass through
unchanged, so sweeping a whole directory is safe.

Repeat Steps 3–4 until `humanReviewItems` is empty. Then hand off to
`/toolkit-pipeline:build`.
