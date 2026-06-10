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

### `toolkit-setup`

Mechanical helpers behind `/toolkit-core:setup`:

```
toolkit-setup detect          # key=value facts: os, java, toolkit path, candidate installs, project, datasources
toolkit-setup path <dir>      # register <dir> on PATH via that install's own 'toolkit admin shell'
toolkit-setup project [dir]   # 'toolkit init' + 'toolkit admin extract ds'
```

It never edits shell rc files itself, never downloads the CLI (license-gated), and never runs
`toolkit auth` (credentials are the user's to enter).

## Hook

A `SessionStart` hook runs `toolkit-check --hook`: silent when the toolkit is present, injects a
short advisory into context when it's missing, and always exits 0 — it never blocks a session.

## Prerequisites

A phData Toolkit license and download access (https://toolkit.phdata.io/docs/toolkit-cli#download).
The plugin can detect and guide, but cannot install the CLI for you.
