# Team setup: auto-install phData plugins

## Claude Code (per-repo)

To give everyone working in a repo the phData plugins automatically, check this into the repo's
`.claude/settings.json` (create the file if it doesn't exist, or merge these keys into it):

```json
{
  "extraKnownMarketplaces": {
    "phdata": {
      "source": { "source": "github", "repo": "phdata/agent-marketplace" }
    }
  },
  "enabledPlugins": {
    "toolkit-core@phdata": true,
    "toolkit-pipeline@phdata": true
  }
}
```

What happens: the next time a teammate opens Claude Code in that repo and trusts the workspace,
the marketplace is registered and the listed plugins are installed and enabled for that project.

Notes:

- Only enable the plugins the repo actually uses. `toolkit-pipeline` pulls in `toolkit-core`
  automatically as a dependency, but listing both keeps intent explicit.
- Access uses the teammate's own GitHub credentials. For a private marketplace repo, everyone
  needs read access to `phdata/agent-marketplace` and working GitHub auth (`gh auth status`).
- The plugins check for the Toolkit CLI at session start and stay quiet when it's present. If a
  teammate is missing the toolkit, they'll be pointed at `/toolkit-core:setup`.
- Enterprise managed settings can force-enable these org-wide instead; the JSON shape is the same.

## Cortex Code (per-user or via connection profile)

Cortex Code installs each plugin individually (it does not read the marketplace catalog):

```
cortex plugin install github:phdata/agent-marketplace/toolkit-core
cortex plugin install github:phdata/agent-marketplace/toolkit-pipeline
```

Install both — Cortex does not resolve the `toolkit-core` dependency automatically. For a team
baseline, administrators can ship plugins as part of a Snowflake connection profile so every
user of that profile gets them by default; see the
[Cortex Code plugin docs](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-plugins).
