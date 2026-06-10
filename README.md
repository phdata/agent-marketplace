# phData Agent Marketplace

Claude Code plugin marketplace for phData's coding-agent extensions — plugins that package
[phData Toolkit](https://toolkit.phdata.io/docs) CLI workflows (skills, preflight scripts, hooks)
so engineering repos don't each carry their own `.claude/skills/`.

## Plugins

| Plugin | Description |
|---|---|
| [toolkit-core](toolkit-core/) | Toolkit CLI foundation: install, PATH setup, project init, JDBC connection/datasource configuration. Required by all other toolkit plugins. |
| [toolkit-pipeline](toolkit-pipeline/) | Dataspec-driven pipeline generation via `toolkit agent discovery` and `toolkit agent pipeline-build`: SQL, dbt, or PySpark transforms plus data-quality tests and a synthetic-data spec. |

## Install (individual)

Inside Claude Code:

```
/plugin marketplace add phdata/agent-marketplace
/plugin install toolkit-core@phdata
/plugin install toolkit-pipeline@phdata
```

Installing `toolkit-pipeline` automatically installs its `toolkit-core` dependency from this
marketplace.

## Install (team / repo-wide)

Check a `.claude/settings.json` into the consuming repo so the plugins auto-install for everyone
who trusts the workspace — see [docs/team-setup.md](docs/team-setup.md).

## Prerequisites

The plugins detect a missing or misconfigured Toolkit CLI and fix it with you
(`/toolkit-core:setup`): on macOS via the Homebrew tap (`brew install toolkit-cli`), on
Linux/Windows via the official install scripts — see the
[install docs](https://toolkit.phdata.io/docs/toolkit-cli#installation). Most toolkit commands
also need an auth token (`toolkit auth`); some features are license-tiered (free vs pro).

## Contributing

- One directory per plugin, manifest at `<plugin>/.claude-plugin/plugin.json`.
- Run `claude plugin validate <plugin-dir>` before opening a PR.
- Local development: `claude --plugin-dir ./<plugin-dir>`, then `/reload-plugins` to pick up edits.
- Releases are git tags of the form `<plugin-name>--v<version>`, pushed with `claude plugin tag --push`.
