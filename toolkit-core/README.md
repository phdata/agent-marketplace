# toolkit-core

Foundation plugin for the [phData Toolkit CLI](https://toolkit.phdata.io/docs). Owns the full
prerequisite chain — toolkit binary on PATH → Java OK → toolkit project (`toolkit.conf`) →
JDBC connection + datasource configured — so workflow plugins (e.g. `toolkit-pipeline`) can
declare a dependency on it and preflight with one command.

## Skills

| Skill | Purpose |
|---|---|
| `/toolkit-core:setup` | Guided install + configuration: Java, binary on PATH, auth, project init |
| `/toolkit-core:connect` | Add/verify a JDBC connection + datasource for any supported type, including driver installs |
| `/toolkit-core:llm` | Configure the optional `llmClient` block (Bedrock/OpenAI/Anthropic) for `toolkit agent *` commands |
| `/toolkit-core:status` | Doctor-style report of the current toolkit state |

## Bash commands (on PATH while the plugin is enabled)

### `toolkit-check`

Layered preflight. Levels are cumulative; the first failure stops the run and prints a single
`hint:` line naming the fix.

```
toolkit-check [--level binary|project|datasource|connect] [--datasource NAME] [--quiet] [--hook] [--list-datasources]
```

| Exit | Meaning |
|---|---|
| 0 | all requested checks passed |
| 2 | usage error |
| 10 | toolkit binary not on PATH |
| 11 | binary present but won't run (Java problem) |
| 12 | no toolkit project (`toolkit.conf`) found |
| 13 | no datasource configured |
| 14 | connectivity probe failed |

Defaults to `--level datasource` — everything verifiable without the network. `--level connect`
is opt-in because it runs `toolkit ds list`, which connection-tests datasources.
`--list-datasources` prints configured datasource names (parsed from `toolkit.conf`).

Workflow-plugin usage pattern:

```bash
toolkit-check || exit   # surface the hint: line to the user and stop
```

Known limitation: the datasource level parses `toolkit.conf` textually; datasources defined via
HOCON `include` files aren't detected (use `--level connect` for the authoritative answer).

Project resolution: `toolkit-check` walks parent directories to *find* `toolkit.conf`, but the
toolkit itself reads only `$TOOLKIT_PROJECT_HOME/toolkit.conf` (default `./toolkit.conf`). When
the conf lives in a parent directory, `ok project` is followed by a `note:` line — run toolkit
commands from that directory or export `TOOLKIT_PROJECT_HOME`. The connect-level probe sets
`TOOLKIT_PROJECT_HOME` itself, so it is correct from any cwd.

### `toolkit-setup`

Mechanical helpers behind `/toolkit-core:setup`:

```
toolkit-setup detect          # key=value facts: os, java, toolkit path, candidate installs, project, datasources
toolkit-setup install         # runs the official repo.phdata.io install script (macOS/Linux; prints Windows commands)
toolkit-setup path <dir>      # register a manually-extracted <dir> on PATH via 'toolkit admin shell'
toolkit-setup project [dir]   # 'toolkit init' + 'toolkit admin extract ds'
```

Installation delegates entirely to the official install scripts at `repo.phdata.io` — the single
source of truth across macOS, Linux, and Windows; this plugin maintains no install logic of its
own. It never edits shell rc files itself (the installer and `toolkit admin shell` own that) and
never runs `toolkit auth` (credentials are the user's to enter).

## Hook

A `SessionStart` hook runs `toolkit-check --hook`: silent when the toolkit is present, injects a
short advisory into context when it's missing, and always exits 0 — it never blocks a session.

## Prerequisites

Java LTS 11/17/21/25 (the installers handle this — Homebrew manages it as a dependency) and a
phData Toolkit auth token for most commands (`toolkit auth`); some features are license-tiered
(free vs pro). Install docs: https://toolkit.phdata.io/docs/toolkit-cli#installation
