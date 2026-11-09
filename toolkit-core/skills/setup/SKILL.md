---
name: setup
description: Install and configure the phData Toolkit CLI end to end — verify Java, get the toolkit binary on PATH, authenticate, initialize a toolkit project, and extract Data Source tool defaults. Use when the toolkit is missing, toolkit_check.py fails, or a user is onboarding to phData Toolkit workflows.
---

# Toolkit CLI setup

> `toolkit_check.py` and `toolkit_setup.py` below are scripts bundled with this plugin, **not**
> commands on PATH. Invoke them by the absolute paths the SessionStart hook prints at
> session start (`<plugin>/scripts/…`); `CLAUDE_PLUGIN_ROOT` is not set for Bash.

Goal: a working `toolkit` command on PATH, an authenticated CLI, and an initialized toolkit
project. Two helper commands from this plugin are available in Bash while it is enabled:
`toolkit_check.py` (layered preflight; see exit codes below) and `toolkit_setup.py`
(mechanical helpers: `detect`, `path <dir>`, `project [dir]`).

Walk only the steps that are actually broken — find out first.

## Step 0 — diagnose

Run the preflight. Use the `toolkit-check` launcher here rather than the Python file
directly — this is the one skill that runs on a machine where nothing is set up yet, and the
launcher is what reports a missing Python:

```bash
"<scripts dir from the SessionStart hook>/toolkit-check"
```

Branch on the exit code:

| Exit | Meaning | Go to |
|---|---|---|
| 0 | Binary, project, and datasource config all present | Step 5 (verify + done) |
| 10 | `toolkit` not on PATH | Step 1 |
| 11 | Binary present but won't run (Java) | Step 2 |
| 12 | No toolkit project (`toolkit.conf`) | Step 4 |
| 13 | No datasource configured | Tell the user to run `/toolkit-core:connect` |
| 15 | No Python 3, or older than 3.8 | Step 0a |

### Step 0a — Python is missing

Every bundled script in every phData plugin is Python 3 (standard library only), so exit 15
means none of them can run — including the rest of this skill. The Toolkit CLI itself is a JVM
application and is unaffected, so plain `toolkit` commands still work.

Surface the `hint:` line, and point the user at `brew install python` on macOS, their package
manager on Linux, or https://www.python.org/downloads/ on Windows. Then have them re-run the
launcher. Do not try to work around it by rewriting the scripts' logic inline.

Also run `toolkit_setup.py detect` and keep its `key=value` output handy — it answers most of the
questions below (Java version, candidate installs, enclosing project).

## Step 1 — get the toolkit binary on PATH

Check `candidate_install` from `toolkit_setup.py detect`:

- **Candidate found** (a previously extracted `toolkit-cli-*` directory): confirm it with the
  user, then run `toolkit_setup.py path <dir>`. This invokes that install's own
  `toolkit admin shell`, which appends a managed PATH section to `~/.bashrc` / `~/.zshrc`
  (bash and zsh only). Tell the user to `source` the rc file or open a new shell, then re-run
  `toolkit_check.py --level binary`.
- **No candidate**: confirm with the user, then run `toolkit_setup.py install`. It delegates to the
  official phData install script — the single source of truth for installation:
  - **macOS / Linux**: runs `https://repo.phdata.io/toolkit-cli/install.sh`, which downloads the
    CLI, verifies its SHA256, installs to `~/.local/opt/toolkit-cli`, adds it to PATH in the
    shell profile (bash/zsh/fish), and prints JDK guidance if Java is missing.
  - **Windows**: prints the official commands for the user to run —
    PowerShell `irm https://repo.phdata.io/toolkit-cli/install.ps1 | iex`.

  Alternatives if the user prefers: Homebrew on macOS (`brew tap phdata/toolkit && brew install
  toolkit-cli` — then `brew upgrade` owns updates and Java comes as a dependency), or the manual
  zip install (https://toolkit.phdata.io/docs/toolkit-cli#installation).

After either path, note that the current Claude Code Bash session may not pick up rc-file/PATH
changes; if `toolkit` is still not found here, export it for this session
(`export PATH="$PATH:<install-dir>"`) and remind the user to open a new terminal for theirs.

## Step 2 — Java (only if `toolkit --version` fails)

The toolkit runs on the JVM and requires a Java LTS release: 11, 17, 21, or 25. Usually the
installers handle this (Homebrew installs Java as a dependency; the Linux/Windows installers
detect a missing JDK and guide the install). If `toolkit_check.py` exited 11 anyway:

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
python3 "$TOOLKIT_SETUP" project <dir>
```

This runs `toolkit init` (skipped if `toolkit.conf` already exists) and then
`toolkit admin extract ds` to materialize the Data Source tool defaults (`tools/ds/` —
profile config, type mappings, codegen templates). If the extract step warns about
authentication, finish Step 3 and re-run `toolkit admin extract ds` from the project directory.

`toolkit init` also writes the full command documentation to `docs/toolkit/*.adoc` in the
project — `data-source.adoc`, `agent.adoc`, `analyzer.adoc`, `sql.adoc`, `toolkit-cli.adoc` and
the rest. Point the user at those, and read them yourself, whenever config syntax or a command's
behavior is unclear; they are the same docs published at https://toolkit.phdata.io/docs but
available offline and matched to the installed version. One caveat: some per-command synopsis
blocks are unresolved `include::` directives, so for exact flags `toolkit <command> --help`
stays authoritative.

## Step 5 — verify and hand off

Re-run `toolkit_check.py`:

- exit 0 → setup is complete. If the user's next move is connecting a database, suggest
  `/toolkit-core:connect`; if they plan to use the toolkit agent commands (e.g. the
  toolkit-pipeline plugin) with their own LLM provider, `/toolkit-core:llm` configures that
  (optional — phData users get a Bedrock fallback automatically); if they just want to explore,
  `toolkit ds tutorial` is a zero-credential practice environment.
- exit 13 → the project has no datasource yet: hand off to `/toolkit-core:connect`.
- anything else → revisit the matching step above.
