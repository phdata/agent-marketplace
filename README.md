# phData Agent Marketplace

Claude Code plugin marketplace for phData's coding-agent extensions — plugins that package
[phData Toolkit](https://toolkit.phdata.io/docs) CLI workflows (skills, preflight scripts, hooks)
so engineering repos don't each carry their own `.claude/skills/`.

## Plugins

| Plugin | Description |
|---|---|
| [toolkit-core](toolkit-core/) | Toolkit CLI foundation: install, PATH setup, project init, JDBC connection/datasource configuration. Required by all other toolkit plugins. |
| [toolkit-pipeline](toolkit-pipeline/) | Dataspec-driven pipeline generation via `toolkit agent discovery` and `toolkit agent pipeline-build`: SQL, dbt, or PySpark transforms plus data-quality tests and a synthetic-data spec. |
| [toolkit-datagen](toolkit-datagen/) | Synthetic, fake, mock, and test data via `toolkit datagen`: the agent writes a data spec, the toolkit generates related tables at any volume to CSV or straight into a database, reproducibly via a seed. Also clones the shape of an existing database without copying rows. |
| [informatica-assessment](informatica-assessment/) | Assess an Informatica PowerCenter estate: export completeness, `ds collect etl`, `ds lineage`, and `ds migration-plan` into dependency-ordered scored waves with an inventory. Offline-capable; no LLM or agent license. |
| [informatica-etl-conversion](informatica-etl-conversion/) | Convert Informatica PowerCenter mappings into Snowflake or Databricks pipelines: `agent etl-extract` behind a dry-run cost gate, discovery with a grouped human-review queue, and pipeline-build — one migration-plan group at a time, or a small corpus in a single pass. |

The two Informatica plugins split along the line where the cost does: everything in
`informatica-assessment` is free and needs no LLM, while every conversion step is
license-gated and spends tokens. Either installs and runs without the other —
`informatica-etl-conversion` reads a plan off disk when there is one and converts the whole
corpus in one pass when there isn't.

## Install — Claude Code

Inside Claude Code:

```
/plugin marketplace add phdata/agent-marketplace
/plugin install toolkit-core@phdata
/plugin install toolkit-pipeline@phdata
/plugin install toolkit-datagen@phdata
/plugin install informatica-assessment@phdata
/plugin install informatica-etl-conversion@phdata
```

Dependencies install automatically from this marketplace: `toolkit-pipeline`,
`toolkit-datagen`, and `informatica-assessment` each pull in `toolkit-core`, and
`informatica-etl-conversion` pulls in `toolkit-core` and `toolkit-pipeline`.

For team/repo-wide auto-install, check a `.claude/settings.json` into the consuming repo —
see [docs/team-setup.md](docs/team-setup.md).

## Install — Cortex Code

Cortex Code consumes the same plugin format but not the marketplace catalog, so install each
plugin by its subdirectory:

```
cortex plugin install github:phdata/agent-marketplace/toolkit-core
cortex plugin install github:phdata/agent-marketplace/toolkit-pipeline
cortex plugin install github:phdata/agent-marketplace/toolkit-datagen
cortex plugin install github:phdata/agent-marketplace/informatica-assessment
cortex plugin install github:phdata/agent-marketplace/informatica-etl-conversion
```

Notes:

- Append `@<branch>` to pin a branch (e.g. `github:phdata/agent-marketplace/toolkit-core@feature/initial_plugin`
  while testing pre-release changes); the subdirectory path goes *before* the `@`.
- Cortex does not auto-install dependencies — install `toolkit-core` explicitly alongside any
  other plugin, plus `toolkit-pipeline` for `informatica-etl-conversion`.
- `cortex plugin update` re-fetches from the pinned source; `cortex plugin list` shows what's
  installed and enabled.
- Teams can also ship these via a Snowflake connection profile — see
  [docs/team-setup.md](docs/team-setup.md).

## Prerequisites

The plugins detect a missing or misconfigured Toolkit CLI and fix it with you
(`/toolkit-core:setup`), delegating installation to the official phData install scripts for
macOS, Linux, and Windows — see the
[install docs](https://toolkit.phdata.io/docs/toolkit-cli#installation). Most toolkit commands
also need an auth token (`toolkit auth`); some features are license-tiered (free vs pro).

## Contributing

- One directory per plugin, manifest at `<plugin>/.claude-plugin/plugin.json`.
- **No top-level `bin/` directory.** Plugins distributed through claude.ai organization settings
  are rejected at sync if they ship one, because `bin/` is added to the Bash `PATH` without
  appearing on the admin approval surface. Put executables in `scripts/` instead. They are then
  not on PATH, and `${CLAUDE_PLUGIN_ROOT}` resolves only in hook commands — never in the Bash
  tool — so a skill must be told the absolute path. `toolkit-core`'s SessionStart hook prints
  its scripts' paths into every session for exactly this reason.
- Run `claude plugin validate <plugin-dir>` before opening a PR.
- Local development: `claude --plugin-dir ./<plugin-dir>`, then `/reload-plugins` to pick up edits.
- Releases are git tags of the form `<plugin-name>--v<version>`, pushed with `claude plugin tag --push`.
