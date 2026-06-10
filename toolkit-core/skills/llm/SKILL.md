---
name: llm
description: Configure the optional llmClient block in toolkit.conf so toolkit agent commands (discovery, pipeline-build, fix-sql, codegen ask) can call an LLM — Amazon Bedrock, OpenAI, or Anthropic. Use when agent commands fail for lack of an LLM, when switching providers or models, or when onboarding to the toolkit agent workflows.
---

# Configure the toolkit LLM client (optional)

`toolkit agent *` commands (and `toolkit codegen ask/prompt`) call an LLM, configured by a
top-level `llmClient` block in `toolkit.conf` — a peer of `connections` and `ds`.

**phData consultants work without any block**: the toolkit falls back to Amazon Bedrock and the
phData auth flow brokers access automatically. Even then, recommend adding the Bedrock example
block: the fallback runs on short AWS SDK default timeouts, and long agent calls (pipeline-build
judge loops) can exceed them — the examples set `requestTimeout`/`socketTimeout` to `1000s`.

## Step 0 — current state

`toolkit-check --level project` finds the `toolkit.conf` to edit; `toolkit-setup detect` reports
`llm_client=<type|none>`. `none` + phData auth = Bedrock fallback — functional, but add the
Bedrock block anyway for the 1000s timeouts.

## Step 1 — pick a provider

Supported `type` values (case-insensitive): `AmazonBedrock`, `openai`, `anthropic`.

| Provider | When | Credentials |
|---|---|---|
| `AmazonBedrock` | phData auth flow (no block needed at all), or own AWS account with Bedrock access | AWS default chain (env/SSO/profile) |
| `anthropic` | Direct Anthropic API key | `ANTHROPIC_API_KEY` |
| `openai` | OpenAI (or compatible endpoint via `url`) | `OPENAI_API_KEY` |

## Step 2 — write the block

Read the matching example, `examples/<provider>.conf`, in this skill's directory and merge the
`llmClient` block into the project's `toolkit.conf` at the top level.

**Secrets rule (same as connections): API keys go in as `${ENV_VAR}` references, never literal
values.** For `openai`/`anthropic` the `apiKey` line can also be omitted entirely — the client
falls back to reading the standard env var directly.

**Timeouts: default both `requestTimeout` and `socketTimeout` to `1000s`** (Bedrock and OpenAI;
the Anthropic client doesn't expose timeout settings). Unset values fall back to short SDK/HTTP
defaults that long agent runs routinely exceed.

## Step 3 — verify

The cheapest end-to-end probe is one prompt round-trip:

```bash
toolkit codegen ask "Reply with the single word: ok"
```

A model response means the client works. Triage:

| Symptom | Fix |
|---|---|
| `Could not resolve substitution` | export the API-key env var |
| 401/403 from provider | wrong/expired key, or AWS credentials not active (`aws sts get-caller-identity`) |
| authorization error from toolkit itself | agent features are license-gated — `toolkit auth` / license tier, not LLM config |
| unknown model id | check the provider's current model list; update `model` |
