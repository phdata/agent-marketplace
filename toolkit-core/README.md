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

## Bundled scripts

Both live in `scripts/` and are invoked by absolute path — **not** added to PATH. Plugins
distributed through claude.ai organization settings may not ship a top-level `bin/`, and
`CLAUDE_PLUGIN_ROOT` is only set for hook commands, never for the Bash tool. The SessionStart
hook therefore prints their absolute paths into every session, and the skills use those:

```
phData toolkit-core scripts (not on PATH -- invoke by absolute path, with python3):
  /…/toolkit-core/scripts/toolkit_check.py, /…/toolkit-core/scripts/toolkit_setup.py
python: /usr/bin/python3 (3.12.4) -- the plugins' scripts are Python 3 stdlib only
```

Both scripts are **Python 3, standard library only**, so they behave the same on Windows,
macOS, and Linux. Run them with whichever Python 3 is on PATH — the `python:` line above names
the interpreter the hook found, and that is the one to use.

### `toolkit_check.py`

Layered preflight. Levels are cumulative; the first failure stops the run and prints a single
`hint:` line naming the fix.

```
python3 toolkit_check.py [--level python|binary|project|datasource|connect] [--datasource NAME] [--quiet] [--hook] [--list-datasources]
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
| 15 | Python is missing or too old (see below) |

Defaults to `--level datasource` — everything verifiable without the network. `--level connect`
is opt-in because it runs `toolkit ds list`, which connection-tests datasources.
`--list-datasources` prints configured datasource names (parsed from `toolkit.conf`).
`--level python` checks only the interpreter, which is the cheapest way for a skill to confirm
the other plugins' scripts can run at all. `--project-dir` prints the enclosing project's
directory and exits 12 if there is none — it starts no JVM and does not need the toolkit binary,
so it is the cheap way to resolve a path inside the project (the toolkit's own docs under
`docs/toolkit/`, for instance) from any working directory.

Workflow-plugin usage pattern:

```bash
python3 "$TOOLKIT_CHECK" || exit   # surface the hint: line to the user and stop
```

Known limitation: the datasource level parses `toolkit.conf` textually; datasources defined via
HOCON `include` files aren't detected (use `--level connect` for the authoritative answer).

Project resolution: `toolkit_check.py` walks parent directories to *find* `toolkit.conf`, but the
toolkit itself reads only `$TOOLKIT_PROJECT_HOME/toolkit.conf` (default `./toolkit.conf`). When
the conf lives in a parent directory, `ok project` is followed by a `note:` line — run toolkit
commands from that directory or export `TOOLKIT_PROJECT_HOME`. The connect-level probe sets
`TOOLKIT_PROJECT_HOME` itself, so it is correct from any cwd.

### `toolkit_setup.py`

Mechanical helpers behind `/toolkit-core:setup`:

```
python3 toolkit_setup.py detect          # key=value facts: os, java, toolkit path, candidate installs, project, datasources
python3 toolkit_setup.py install         # runs the official repo.phdata.io install script (macOS/Linux; prints Windows commands)
python3 toolkit_setup.py path <dir>      # register a manually-extracted <dir> on PATH via 'toolkit admin shell'
python3 toolkit_setup.py project [dir]   # 'toolkit init' + 'toolkit admin extract ds'
```

Installation delegates entirely to the official install scripts at `repo.phdata.io` — the single
source of truth across macOS, Linux, and Windows; this plugin maintains no install logic of its
own. It never edits shell rc files itself (the installer and `toolkit admin shell` own that) and
never runs `toolkit auth` (credentials are the user's to enter).

### `toolkit-check` — the launcher, and the Python check

`scripts/toolkit-check` is a ~60-line POSIX `sh` script, with `scripts/toolkit-check.cmd` as
its `cmd` twin for Windows. They are the only things here that are not Python. It exists because of one unavoidable gap: **you cannot run a Python script to find out
whether Python is installed.** It holds no logic — it resolves an interpreter (`python3`, then
`python`, then `py -3`) and hands every argument straight to `toolkit_check.py`.

When no Python 3 is found it reports that itself, in the same `fail:`/`hint:` contract, and exits
15:

```
fail python: no python3, python, or py -3 found on PATH
hint: install Python 3.8 or newer (…) — every phData plugin script needs it
```

It uses shell builtins only — no `dirname`, no `cat` — so it still resolves its own location and
prints a useful message on a machine whose `PATH` is half-broken, which is exactly when it gets
called. On Windows, where it does not run, invoke `python toolkit_check.py` (or
`py -3 toolkit_check.py`) directly; the session-start line names the interpreter.

## Platform support

| | macOS / Linux | Windows + Git Bash | Windows, no Git Bash |
|---|---|---|---|
| `toolkit_check.py`, `toolkit_setup.py` and every other plugin's scripts | yes | yes | yes — run them with `python` or `py -3` |
| `scripts/toolkit-check` (sh launcher) | yes | yes | no — use `toolkit-check.cmd` |
| `scripts/toolkit-check.cmd` (Windows launcher) | n/a | n/a | yes |
| The `SessionStart` hook | yes | yes | needs one settings entry, below |

The Python is portable by construction: standard library only, `pathlib` for every path, no
POSIX-only modules, and the Windows batch launcher (`toolkit.bat`) is recognized alongside the
shell one when looking for an extracted install. Output is also hardened for Windows consoles:
they default to the locale encoding, which cannot represent an arrow in a join path or the
toolkit's own status glyphs, so the scripts degrade those to `?` rather than dying with
`UnicodeEncodeError` mid-report.

Claude Code runs hook commands through **bash by default — including on Windows, as long as Git
Bash is present** — and falls back to PowerShell only on a Windows machine without it. So the sh
launcher covers every common setup, and the shipped `hooks.json` needs no platform branching.

**Windows without Git Bash** is the one case the shipped hook cannot serve: under PowerShell,
`${CLAUDE_PLUGIN_ROOT}` reads as an undefined PowerShell variable, and PowerShell cannot run the
sh launcher anyway. `scripts/toolkit-check.cmd` is there for that case — the same launcher,
written for `cmd`, resolving `py -3` / `python` / `python3`. Wire it up by adding one entry to
your own `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "shell": "powershell",
            "command": "& \"$env:CLAUDE_PLUGIN_ROOT\\scripts\\toolkit-check.cmd\" --hook"
          }
        ]
      }
    ]
  }
}
```

That entry is deliberately **not** in the plugin's own `hooks.json`: it would run on macOS and
Linux too, where `pwsh` is usually absent, and a hook that fails in every session is worse than
one that is missing in a rare one. Without it, nothing breaks — the announcement line simply does
not print, and skills fall back to their documented path (`<plugin>/scripts/toolkit_check.py`,
run with `python`).

## Hook

A `SessionStart` hook runs `scripts/toolkit-check --hook` (the launcher). It always prints the
absolute paths of the bundled scripts and the Python interpreter it found — that is how skills
in this plugin and in every dependent plugin learn both — adds a short advisory when the toolkit
binary is missing, and always exits 0 so it never blocks a session. A missing Python is likewise
an advisory, not a failure: the Toolkit CLI is a JVM application, so `toolkit` commands still
work even when none of the plugins' scripts can run.

## Prerequisites

**Python 3.8+** for the bundled scripts — standard library only, no packages to install. Every
phData plugin's scripts are Python, so this is the one prerequisite shared across all of them;
the SessionStart hook reports a missing or too-old interpreter.

Java LTS 11/17/21/25 for the Toolkit CLI itself (the installers handle this — Homebrew manages it
as a dependency) and a phData Toolkit auth token for most commands (`toolkit auth`); some
features are license-tiered (free vs pro). Install docs:
https://toolkit.phdata.io/docs/toolkit-cli#installation
