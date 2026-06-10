---
name: status
description: Show a doctor-style report of the phData Toolkit CLI installation — binary, Java, project, datasources, and optional connectivity. Use when the user asks whether the toolkit is set up, why a toolkit command might be failing, or wants a health check before starting toolkit work.
---

# Toolkit status

Run both helpers and render one readable report:

```bash
toolkit-check            # layered checks: binary -> project -> datasource
toolkit-setup detect     # raw facts: os, java, install path, project, datasources
```

Present a short table: binary (path + version), Java, project (`toolkit.conf` path), datasources
(names), and LLM client (`llm_client` from detect; `none` means the phData Bedrock fallback for
agent commands). Use the `ok`/`fail` lines from `toolkit-check` as the source of truth and
`detect` output for the detail values.

If the user wants connectivity verified too (this touches the network and connection-tests the
datasource), add:

```bash
toolkit-check --level connect --datasource <name>
```

End with the recommended next step:

- `fail binary`/`fail java`/`fail project` → `/toolkit-core:setup`
- `fail datasource` or `fail connect` → `/toolkit-core:connect`
- all ok → nothing to fix; workflow plugins (e.g. `/toolkit-pipeline:discover`) are ready to use.
