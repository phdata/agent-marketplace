#!/usr/bin/env python3
"""
toolkit_setup.py - mechanical helpers behind the /toolkit-core:setup skill.

Usage (run with whichever Python 3 is on PATH - `python3` on macOS/Linux, `python` or
`py -3` on Windows; the SessionStart hook prints the interpreter it found):

    python3 toolkit_setup.py detect          print key=value facts about this machine's
                                             toolkit state
    python3 toolkit_setup.py install         install the Toolkit CLI by running the official
                                             repo.phdata.io install script (macOS and Linux;
                                             prints the official Windows commands elsewhere)
    python3 toolkit_setup.py path <dir>      put a manually-extracted <dir> on PATH by
                                             running that install's own
                                             `toolkit admin shell` (bash/zsh managed section)
    python3 toolkit_setup.py project [dir]   initialize a toolkit project in dir
                                             (default: cwd) via `toolkit init`, then extract
                                             Data Source tool defaults via
                                             `toolkit admin extract ds`

Boundaries (by design):
  - never edits shell rc files itself - `toolkit admin shell` / the installers own that
  - delegates installation entirely to the official install scripts at repo.phdata.io
    (the single source of truth - no separate install logic is maintained here);
    manual zip docs: https://toolkit.phdata.io/docs/toolkit-cli#installation
  - never runs `toolkit auth` - credentials are the user's to enter

Python 3 standard library only. `curl` and `sh` are still used for the install step, on
purpose: the official installer is a shell script, and curl honours the proxy and TLS
configuration that a consultant's machine is likely to already have set up.

Exit codes: 0 success, 2 usage error, 1 operation failed.
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Same directory, so the conf-finding and HOCON parsing live in exactly one place.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import toolkit_check  # noqa: E402

INSTALL_URL = "https://repo.phdata.io/toolkit-cli/install.sh"
INSTALL_DOCS = "https://toolkit.phdata.io/docs/toolkit-cli#installation"

# Where a manually-extracted CLI is likely to be sitting, newest wins.
CANDIDATE_GLOBS = (
    ("~/Downloads", "toolkit-cli-*"),
    ("~", "toolkit-cli-*"),
    ("/opt", "toolkit-cli-*"),
    ("~/.local/opt", "toolkit-cli*"),
)

LLM_BLOCK = re.compile(r"llmClient\s*\{")
LLM_TYPE = re.compile(r"type\s*=\s*(.+)")


def first_line(text):
    lines = (text or "").splitlines()
    return lines[0] if lines else ""


def run(command, **kwargs):
    """subprocess.run that never raises on a missing binary."""
    try:
        return subprocess.run(command, **kwargs)
    except OSError:
        return None


def java_version():
    if not shutil.which("java"):
        return "none"
    probe = run(["java", "-version"], capture_output=True, text=True)
    if probe is None:
        return "none"
    # java -version writes to stderr; quotes would break key=value parsing.
    line = first_line(probe.stderr or probe.stdout)
    return line.replace('"', "'")


def toolkit_facts():
    path = shutil.which("toolkit")
    if not path:
        return "none", "none"
    probe = run(["toolkit", "--version"], capture_output=True, text=True)
    version = first_line(probe.stdout) if probe and probe.returncode == 0 else ""
    return path, version or "unknown"


def candidate_install():
    """Newest extracted CLI install that isn't on PATH yet, if any."""
    best = None
    best_mtime = -1.0
    for parent, pattern in CANDIDATE_GLOBS:
        base = Path(parent).expanduser()
        if not base.is_dir():
            continue
        for directory in base.glob(pattern):
            binary = directory / "toolkit"
            if not (directory.is_dir() and binary.is_file() and os.access(binary, os.X_OK)):
                continue
            mtime = directory.stat().st_mtime
            if mtime > best_mtime:
                best, best_mtime = directory, mtime
    return str(best) if best else "none"


def llm_client(conf):
    """The llmClient block's `type`, or 'none'.

    phData users fall back to Amazon Bedrock via the toolkit auth flow when none is set.
    """
    inside = False
    for raw in conf.read_text(encoding="utf-8", errors="replace").splitlines():
        if not inside:
            if LLM_BLOCK.search(raw):
                inside = True
            continue
        found = LLM_TYPE.search(raw)
        if found:
            return re.sub(r'["{}]', "", found.group(1)).strip() or "none"
    return "none"


def cmd_detect(_args):
    print("os={}".format(platform.system()))
    print("arch={}".format(platform.machine()))
    print("java_version={}".format(java_version()))

    path, version = toolkit_facts()
    print("toolkit_path={}".format(path))
    print("toolkit_version={}".format(version))
    print("candidate_install={}".format(candidate_install()))

    conf = toolkit_check.find_project_conf()
    print("project_conf={}".format(conf if conf else "none"))

    if conf is None:
        print("datasource_count=0")
        print("datasources=")
        print("llm_client=none")
        return 0

    names = toolkit_check.list_datasources(conf)
    print("datasource_count={}".format(len(names)))
    print("datasources={}".format(",".join(names)))
    print("llm_client={}".format(llm_client(conf)))
    return 0


def cmd_install(_args):
    existing = shutil.which("toolkit")
    if existing:
        print("note: toolkit already on PATH at {} — nothing to install".format(existing))
        return 0

    system = platform.system()
    if system not in ("Darwin", "Linux"):
        sys.stderr.write("Run the official installer for Windows:\n")
        sys.stderr.write(
            "  PowerShell:     irm https://repo.phdata.io/toolkit-cli/install.ps1 | iex\n"
        )
        sys.stderr.write(
            "  Command Prompt: curl -fsSL "
            "https://repo.phdata.io/toolkit-cli/install.cmd -o install.cmd "
            "&& install.cmd\n"
        )
        return 1

    if not shutil.which("curl") or not shutil.which("sh"):
        sys.stderr.write(
            "error: the official installer is a shell script fetched with curl, and "
            "curl or sh is missing.\n"
        )
        sys.stderr.write("Install it manually instead: {}\n".format(INSTALL_DOCS))
        return 1

    # The official install script owns download, SHA256 verification, placement
    # (~/.local/opt/toolkit-cli), and shell-profile PATH setup.
    env = dict(os.environ)
    shim_dir = None
    if not shutil.which("sha256sum"):
        # Temporary shim: the installer calls sha256sum, which stock macOS lacks (the
        # native tool is `shasum -a 256`). Provide it on PATH until the upstream fallback
        # lands in the toolkit repo's cli/linux/install.sh.
        shim_dir = tempfile.mkdtemp()
        shim = Path(shim_dir) / "sha256sum"
        shim.write_text('#!/bin/sh\nexec shasum -a 256 "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
        env["PATH"] = "{}{}{}".format(env.get("PATH", ""), os.pathsep, shim_dir)

    try:
        fetch = subprocess.Popen(["curl", "-fsSL", INSTALL_URL], stdout=subprocess.PIPE)
        shell = subprocess.Popen(["sh"], stdin=fetch.stdout, env=env)
        if fetch.stdout:
            fetch.stdout.close()
        returncode = shell.wait()
        fetch.wait()
    finally:
        if shim_dir:
            shutil.rmtree(shim_dir, ignore_errors=True)

    return 0 if returncode == 0 else 1


def cmd_path(args):
    install_dir = Path(args.directory.rstrip("/\\")).expanduser()
    binary = install_dir / "toolkit"
    if not (binary.is_file() and os.access(binary, os.X_OK)):
        sys.stderr.write("error: no executable 'toolkit' in {}\n".format(install_dir))
        return 1
    # Delegates rc-file editing to the toolkit's managed-section logic (bash/zsh).
    probe = run([str(binary), "admin", "shell"])
    return 0 if probe and probe.returncode == 0 else 1


def cmd_project(args):
    target = Path(args.directory).expanduser() if args.directory else Path.cwd()
    if not target.is_dir():
        sys.stderr.write("error: directory does not exist: {}\n".format(target))
        return 1
    if not shutil.which("toolkit"):
        sys.stderr.write(
            "error: toolkit not on PATH — run 'toolkit_setup.py path <install-dir>' first\n"
        )
        return 1

    if (target / "toolkit.conf").is_file():
        print("note: {}/toolkit.conf already exists, skipping 'toolkit init'".format(target))
    else:
        init = run(["toolkit", "init"], cwd=str(target))
        if not init or init.returncode != 0:
            return 1

    extract = run(["toolkit", "admin", "extract", "ds"], cwd=str(target))
    if not extract or extract.returncode != 0:
        print(
            "warn: 'toolkit admin extract ds' failed — authentication/license may be "
            "required."
        )
        print("warn: run 'toolkit auth', then 'toolkit admin extract ds' from {}.".format(target))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="toolkit_setup.py",
        description="Mechanical helpers behind the /toolkit-core:setup skill.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("detect", help="key=value facts about this machine").set_defaults(
        func=cmd_detect
    )
    sub.add_parser("install", help="install the Toolkit CLI").set_defaults(
        func=cmd_install
    )

    p_path = sub.add_parser("path", help="put a manually-extracted install on PATH")
    p_path.add_argument("directory")
    p_path.set_defaults(func=cmd_path)

    p_project = sub.add_parser("project", help="initialize a toolkit project")
    p_project.add_argument("directory", nargs="?", default="")
    p_project.set_defaults(func=cmd_project)

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        sys.stderr.write(
            "usage: toolkit_setup.py detect | install | path <toolkit-install-dir> "
            "| project [dir]\n"
        )
        return 2

    if not args.command:
        sys.stderr.write(
            "usage: toolkit_setup.py detect | install | path <toolkit-install-dir> "
            "| project [dir]\n"
        )
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
