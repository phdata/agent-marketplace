# phData Agent Marketplace

Claude Code plugin marketplace for phData's coding-agent extensions — plugins that package
[phData Toolkit](https://toolkit.phdata.io/docs) CLI workflows (skills, preflight scripts, hooks)
so engineering repos don't each carry their own `.claude/skills/`.

## Plugins

| Plugin | Description |
|---|---|
| [toolkit-core](toolkit-core/) | Toolkit CLI foundation: install, PATH setup, project init, JDBC connection/datasource configuration. Required by all other toolkit plugins. |
| [toolkit-pipeline](toolkit-pipeline/) | Dataspec-driven pipeline generation via `toolkit agent discovery` and `toolkit agent pipeline-build`: SQL, dbt, or PySpark transforms plus data-quality tests and a synthetic-data spec. |
| [informatica-etl-conversion](informatica-etl-conversion/) | Informatica PowerCenter conversion: survey the mappings (collect, lineage, `ds migration-plan`) and convert them wave by wave via `agent etl-extract`, discovery with a grouped review queue, and pipeline-build — or convert a handful of mappings in a single pass. |

## Install — Claude Code

Inside Claude Code:

```
/plugin marketplace add phdata/agent-marketplace
/plugin install toolkit-core@phdata
/plugin install toolkit-pipeline@phdata
/plugin install informatica-etl-conversion@phdata
```

Dependencies install automatically from this marketplace: `toolkit-pipeline` pulls in
`toolkit-core`, and `informatica-etl-conversion` pulls in both.

For team/repo-wide auto-install, check a `.claude/settings.json` into the consuming repo —
see [docs/team-setup.md](docs/team-setup.md).

## Install — Cortex Code

Cortex Code consumes the same plugin format but not the marketplace catalog, so install each
plugin by its subdirectory:

```
cortex plugin install github:phdata/agent-marketplace/toolkit-core
cortex plugin install github:phdata/agent-marketplace/toolkit-pipeline
cortex plugin install github:phdata/agent-marketplace/informatica-etl-conversion
```

Notes:

- Append `@<branch>` to pin a branch (e.g. `github:phdata/agent-marketplace/toolkit-core@feature/initial_plugin`
  while testing pre-release changes); the subdirectory path goes *before* the `@`.
- Cortex does not auto-install dependencies — install `toolkit-core` explicitly alongside
  `toolkit-pipeline`, and all three for `informatica-etl-conversion`.
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
