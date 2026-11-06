---
name: discover
description: Run toolkit agent discovery to resolve a dataspec against a live datasource into a reviewable data contract, then work the human-review queue — all contracts' items collapsed into one distinct list so a repeated question is answered once and applied everywhere — until every contract is approved. Use when the user has (or needs) a dataspec and wants source-to-target mappings, or mentions data contracts, discovery, humanReviewItems, or resolving review items.
---

# Discover: dataspec → approved data contract

`toolkit agent discovery` reads a dataspec, scans/profiles the live datasource, proposes
source-to-target column mappings with confidence scores, validates them against real data, and
emits a data contract. Items it isn't confident about are flagged for human review — the loop
below resolves them.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
"$TOOLKIT_CHECK" || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit-check` in the installed toolkit-core plugin directory.

On failure surface the `hint:` line and stop (`/toolkit-core:setup` / `/toolkit-core:connect`).
If it prints a `note:` about the project directory, run every `toolkit` command below from that
directory (or export `TOOLKIT_PROJECT_HOME`) — the toolkit doesn't search parent directories.

Additional prerequisites beyond toolkit-check:

- **Platform**: the pipeline process supports Snowflake and Databricks only — both the
  datasource being discovered and the spec's `targetPlatform`. If the user's datasource is
  another type, stop here and explain.
- **LLM access**: agent commands call an LLM. With no `llmClient` block in `toolkit.conf`, the
  toolkit falls back to Amazon Bedrock via the phData auth flow (works out of the box for phData
  consultants). Others configure a provider with `/toolkit-core:llm` (Bedrock/OpenAI/Anthropic).
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

## Step 3 — build one review queue across every contract

**Do this before reading any single report.** The review queue is mostly repeats: the same
idiom appears across many target tables, so one decision can resolve a dozen items. Reading
contract by contract asks the user the same question over and over, and invites answering it
inconsistently — which the resolver then rejects.

```bash
python3 <plugin>/scripts/review_queue.py list
```

`review_queue.py` is bundled in this plugin's `scripts/` directory (two levels up from this
skill's directory). Plugin scripts are not on PATH and `CLAUDE_PLUGIN_ROOT` isn't set for the
Bash tool, so invoke it by path. It is Python 3 standard library only — no jq, no packages — so
the same command works on Windows (`python` or `py`), macOS, and Linux. Default input directory
is `discovery-out`; pass `--dir` for anything else.

It collapses `sourceToTarget.humanReviewItems[]` from every `*/data-contract.json` into one
numbered list of **distinct questions**, biggest group first, each with a real example, the
contracts it appears in, and whether it still needs a decision:

```
#1  7x  [LOW CONFIDENCE]  Target column signup_dt maps to RAW.CUSTOMER.CREATED_TS via
        TO_DATE(CREATED_TS, 'MM/DD/YYYY') at confidence 0.52
      e.g. above; 7 items differing only in names/values
      contracts: dim_customer, dim_product, fact_sales, ...
```

Items are grouped by their `[TAG]` plus the *shape* of the description — identifiers, quoted
literals and numbers replaced by placeholders — so the same question about different columns
lands in one group. Grouping is a presentation heuristic and never touches a contract.

Report to the user: how many raw items there are versus how many distinct questions, and the
tag spread. That ratio is the whole point ("31 items, but really 9 decisions").

| Tag | What discovery is asking |
|---|---|
| `[LOW CONFIDENCE]` | It found a source column but isn't sure it's the right one |
| `[UNMAPPED]` | It found no source for a target column |
| `[MULTIPLE CANDIDATES]` | Several plausible sources; confirm the one it picked is authoritative |
| `[COMPLEX TRANSFORM]` | Business logic it won't guess at — verify the expression |
| `[JOIN FAILED]` | A join path it couldn't validate against real data (match rates are in the description) |
| `[ASSERTION FAILED]` | Its proposed mapping contradicts the spec's example records |
| `[LOAD STRATEGY]` | An incremental load with no change-detection method chosen (watermark, cdc_column, hash_diff, key_match, key_not_exists) |
| `[SPEC AMBIGUITY]` | An ambiguity carried from the dataspec — a question about intent, not about the warehouse |
| `[PROCEDURAL LOOP]` | The source load was row-by-row; build it set-based and ignore the translated loop |

## Step 4 — decide, one group at a time

Work the list in order — the biggest group buys the most. For each:

```bash
python3 <plugin>/scripts/review_queue.py show 1
```

**Always `show` before deciding.** It prints every item in the group with its contract, full
description, and any existing comment, which is how you confirm the group really is one
question rather than two that happen to share a shape. If it isn't, comment the members
individually instead.

Then put *one* proposal to the user, in concrete terms, and capture the answer in their own
words:

> Seven contracts translate an Informatica-style `TO_DATE(col, 'MM/DD/YYYY')` where the source
> column is a string, all flagged low confidence. Proposal: `TRY_TO_DATE`, null on unparseable
> values rather than failing the load. Does that match how these loads behave today?

Write the decision into every item in the group at once:

```bash
python3 <plugin>/scripts/review_queue.py comment 1 "Use TRY_TO_DATE; null on unparseable values rather than failing the load."
```

That writes the `comment` field of each member item across every affected contract, preserving
key order and formatting (`--dry-run` to preview, `--overwrite` to replace existing comments).
Leave groups the user has no opinion on uncommented — they stay queued rather than being
guessed at.

Also read `discovery-out/<name>/discovery-report.txt` for the contracts the user cares most
about: the `ITEMS REQUIRING YOUR REVIEW` section states each item in prose, and the column
mapping table shows confidence per column and any `x`-marked rows. Worth a look for anything
below ~0.7 confidence, and for CRITICAL warnings, which the queue doesn't carry.

## Step 5 — sweep every contract

```bash
for d in discovery-out/*/; do
  toolkit agent discovery <datasource> specs/"$(basename "$d")".yaml --resolve "$d/data-contract.json"
done
```

The positional datasource/spec arguments are required by the CLI but ignored on the resolve
path. The resolver applies each comment via the LLM, drops resolved items from
`humanReviewItems`, and sets `approvedByHuman: true` when none remain, rewriting both the
contract and the report in place. Contracts with no comments pass through unchanged, so
sweeping them all is safe.

Two properties of the resolver that shape how to use the queue:

- **Each commented item is all-or-nothing.** An item whose amendments name something the
  contract doesn't have, or that contradict how an earlier item changed the same mapping or
  join, is left open with a `resolverNote` and *none* of its amendments are applied.
- **Items that ask for the same change are all applied.** This is why broadcasting one decision
  across a group is safe, and why inconsistent per-item answers are the thing that actually
  breaks a sweep.

## Step 6 — re-queue and repeat

```bash
python3 <plugin>/scripts/review_queue.py list
```

Items that survived the sweep are flagged `NOT APPLIED` with the resolver's reason — read it
with `show` before commenting again, because the second comment has to address *why the first
was refused*, not restate it. A group whose members are all commented with no note needs
nothing but the next sweep.

Repeat Steps 4–6 until every contract reports `approvedByHuman: true`. Tooling, target
platform and target columns are structurally locked, so a comment can never change the target
schema — a genuinely wrong target means fixing the dataspec and re-running discovery (Step 2),
not commenting harder.

Command reference: the `discovery` section of `docs/toolkit/agent.adoc`, written into the
project by `toolkit init`.

Then hand off to `/toolkit-pipeline:build`.
