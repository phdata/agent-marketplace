---
name: setup
description: Install and configure the phData Toolkit CLI end to end — verify Java, get the toolkit binary on PATH, authenticate, initialize a toolkit project, and extract Data Source tool defaults. Use when the toolkit is missing, toolkit-check fails, or a user is onboarding to phData Toolkit workflows.
---

# Toolkit CLI setup

Goal: a working `toolkit` command on PATH, an authenticated CLI, and an initialized toolkit
project. Two helper commands from this plugin are available in Bash while it is enabled:
`toolkit-check` (layered preflight; see exit codes below) and `toolkit-setup`
(mechanical helpers: `detect`, `path <dir>`, `project [dir]`).

Walk only the steps that are actually broken — find out first.

## Step 0 — diagnose

Run `toolkit-check`. Branch on the exit code:

| Exit | Meaning | Go to |
|---|---|---|
| 0 | Binary, project, and datasource config all present | Step 5 (verify + done) |
| 10 | `toolkit` not on PATH | Step 1 |
| 11 | Binary present but won't run (Java) | Step 2 |
| 12 | No toolkit project (`toolkit.conf`) | Step 4 |
| 13 | No datasource configured | Tell the user to run `/toolkit-core:connect` |

Also run `toolkit-setup detect` and keep its `key=value` output handy — it answers most of the
questions below (Java version, candidate installs, enclosing project).

## Step 1 — get the toolkit binary on PATH

Check `candidate_install` from `toolkit-setup detect`:

- **Candidate found** (a previously extracted `toolkit-cli-*` directory): confirm it with the
  user, then run `toolkit-setup path <dir>`. This invokes that install's own
  `toolkit admin shell`, which appends a managed PATH section to `~/.bashrc` / `~/.zshrc`
  (bash and zsh only). Tell the user to `source` the rc file or open a new shell, then re-run
  `toolkit-check --level binary`.
- **No candidate**: install via the official channel for the platform — confirm with the user,
  then run `toolkit-setup install`:
  - **macOS**: `brew tap phdata/toolkit && brew install toolkit-cli` — Homebrew manages Java as
    a dependency and puts `toolkit` on PATH automatically.
  - **Linux**: `curl -fsSL https://repo.phdata.io/toolkit-cli/install.sh | sh` — installs to
    `~/.local/opt/toolkit-cli` and adds it to PATH in the shell profile.
  - **Windows**: the helper prints the PowerShell command for the user to run:
    `irm https://repo.phdata.io/toolkit-cli/install.ps1 | iex`.

  Manual zip install also remains an option: https://toolkit.phdata.io/docs/toolkit-cli#download

After either path, note that the current Claude Code Bash session may not pick up rc-file/PATH
changes; if `toolkit` is still not found here, export it for this session
(`export PATH="$PATH:<install-dir>"`) and remind the user to open a new terminal for theirs.

## Step 2 — Java (only if `toolkit --version` fails)

The toolkit runs on the JVM and requires a Java LTS release: 11, 17, 21, or 25. Usually the
installers handle this (Homebrew installs Java as a dependency; the Linux/Windows installers
detect a missing JDK and guide the install). If `toolkit-check` exited 11 anyway:

- `java_version=none` in detect output: suggest a platform-appropriate install (macOS:
  `brew install temurin`; Linux: distro OpenJDK packages; Windows: `winget install` OpenJDK).
- Java present but toolkit still fails: run `toolkit --version` directly and show the user the
  error — likely an unsupported Java version or a corrupted/partial extract.

## Step 3 — authenticate

Most toolkit commands need an auth token. Have the **user** run `toolkit auth` themselves —
never enter credentials for them. Details:
https://toolkit.phdata.io/docs/toolkit-cli#auth-token

Notes:
- phData employees authenticate with the phData flow; customers use their own token.
- Some features (parts of `admin extract`, all `toolkit agent *` commands) are license-gated and
  fail with an authorization error if the license doesn't include them — that's expected, not a
  setup bug.

## Step 4 — initialize a toolkit project

A toolkit project is a directory with a `toolkit.conf`. Confirm the target directory with the
user (usually the repo or working directory they'll run migrations from), then:

```bash
toolkit-setup project <dir>
```

This runs `toolkit init` (skipped if `toolkit.conf` already exists) and then
`toolkit admin extract ds` to materialize the Data Source tool defaults (`tools/ds/` —
profile config, type mappings, codegen templates). If the extract step warns about
authentication, finish Step 3 and re-run `toolkit admin extract ds` from the project directory.

## Step 5 — verify and hand off

Re-run `toolkit-check`:

- exit 0 → setup is complete. If the user's next move is connecting a database, suggest
  `/toolkit-core:connect`; if they plan to use the toolkit agent commands (e.g. the
  toolkit-pipeline plugin) with their own LLM provider, `/toolkit-core:llm` configures that
  (optional — phData users get a Bedrock fallback automatically); if they just want to explore,
  `toolkit ds tutorial` is a zero-credential practice environment.
- exit 13 → the project has no datasource yet: hand off to `/toolkit-core:connect`.
- anything else → revisit the matching step above.
