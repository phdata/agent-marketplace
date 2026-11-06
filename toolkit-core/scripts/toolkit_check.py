#!/usr/bin/env python3
"""
toolkit_check.py - layered preflight checks for the phData Toolkit CLI.

Usage:
    python3 toolkit_check.py [--level python|binary|project|datasource|connect]
                             [--datasource NAME] [--quiet] [--hook]
                             [--list-datasources]

Levels are cumulative (python -> binary -> project -> datasource -> connect); the first
failure stops the run. Default level: datasource - everything that can be verified without
touching the network. The connect level is opt-in because it runs `toolkit ds list`, which
connection-tests the configured datasources.

Exit codes:
    0   all requested checks passed
    2   usage error
    10  toolkit binary not on PATH
    11  binary present but won't run (Java problem)
    12  no toolkit project found (no toolkit.conf in cwd, parents, or $TOOLKIT_PROJECT_HOME)
    13  no datasource configured in toolkit.conf
    14  connectivity probe failed
    15  Python itself is too old (the `toolkit-check` launcher also uses 15 when no
        Python 3 can be found at all - the one check this file cannot perform, since it
        needs an interpreter to run)

Output contract (machine-parsable, stable):
    ok <level>: <detail>
    fail <level>: <detail>
    hint: <the single actionable fix>

Workflow-plugin skills should run this (or --level connect before commands that hit the
database) and, on a non-zero exit, surface the hint: line to the user and stop.

Modes:
    --quiet             no output, exit code only
    --hook              SessionStart hook mode: PATH lookup only (no JVM start), prints a
                        short advisory when the toolkit is missing, and ALWAYS exits 0 so
                        sessions are never blocked
    --list-datasources  print configured datasource names (one per line) and exit; used by
                        toolkit_setup.py and the /toolkit-core skills

Known limitation: the datasource level parses toolkit.conf textually. Datasources defined in
HOCON include files, or declared entirely on one line, are not detected; define them in
toolkit.conf as a block, or rely on --level connect for the authoritative answer.

Project resolution: this script walks parent directories to FIND toolkit.conf, but the
toolkit itself does not - it reads $TOOLKIT_PROJECT_HOME/toolkit.conf (default
./toolkit.conf). When the conf is found in a parent, the ok-project output adds a note: line
telling the caller to run toolkit commands from that directory or export
TOOLKIT_PROJECT_HOME. The connect-level probe sets TOOLKIT_PROJECT_HOME itself, so it is
correct from any cwd.

Python 3 standard library only - no third-party packages - so it behaves the same on
Windows, macOS, and Linux.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

LEVELS = ("python", "binary", "project", "datasource", "connect")
MIN_PYTHON = (3, 8)

# Exit codes, named so the contract is readable at the call sites.
EXIT_USAGE = 2
EXIT_NO_BINARY = 10
EXIT_JAVA = 11
EXIT_NO_PROJECT = 12
EXIT_NO_DATASOURCE = 13
EXIT_CONNECT = 14
EXIT_PYTHON = 15

CONF_NAME = "toolkit.conf"
INSTALL_DOCS = "https://toolkit.phdata.io/docs/toolkit-cli#installation"

# A datasource name opening a block at depth 1: `name {`, `"name" {`, `name = {`.
BLOCK_NAME = re.compile(r'^"?([A-Za-z][A-Za-z0-9_-]*)"?\s*(?:=\s*)?\{')
# The line that opens the datasources block, in block form.
DATASOURCES_OPEN = re.compile(r"(?:^|[^A-Za-z0-9_])(?:ds\.)?datasources\s*\{")
# Dot-path form: `ds.datasources.name { ... }` / `datasources.name { ... }`.
DOT_PATH = re.compile(r"^\s*(?:ds\.)?datasources\.([A-Za-z][A-Za-z0-9_-]*)")


class Reporter:
    """The ok/fail/hint output contract, honouring --quiet."""

    def __init__(self, quiet):
        self.quiet = quiet

    def say(self, text):
        if not self.quiet:
            print(text)

    def ok(self, level, detail):
        self.say("ok {}: {}".format(level, detail))

    def note(self, detail):
        self.say("note: {}".format(detail))

    def fail(self, code, level, detail, hint):
        self.say("fail {}: {}".format(level, detail))
        self.say("hint: {}".format(hint))
        sys.exit(code)


def strip_comments(line):
    """HOCON line comments: // and #."""
    return re.sub(r"#.*", "", re.sub(r"//.*", "", line))


def find_project_conf():
    """The enclosing project's toolkit.conf, or None.

    $TOOLKIT_PROJECT_HOME wins, as it does for the toolkit itself; otherwise walk up from
    the current directory.
    """
    home = os.environ.get("TOOLKIT_PROJECT_HOME")
    if home:
        candidate = Path(home) / CONF_NAME
        if candidate.is_file():
            return candidate

    current = Path.cwd()
    for directory in [current] + list(current.parents):
        candidate = directory / CONF_NAME
        if candidate.is_file():
            return candidate
    return None


def list_datasources(conf):
    """Datasource names defined in a toolkit.conf, sorted and deduplicated.

    Handles the block form (`ds { datasources { name { ... } } }`) by tracking brace depth
    inside the datasources block, and the dot-path form (`ds.datasources.name { ... }`) by
    line match. Textual on purpose: this must not start a JVM.
    """
    names = set()
    inside = False
    depth = 0

    for raw in conf.read_text(encoding="utf-8", errors="replace").splitlines():
        line = strip_comments(raw)

        if not inside:
            if not DATASOURCES_OPEN.search(line):
                continue
            inside = True
            depth = 0
            # Keep only what follows `datasources`, so the opening brace is counted below.
            line = re.sub(r".*datasources\s*", "", line)

        if depth == 1:
            found = BLOCK_NAME.match(line.lstrip())
            if found:
                names.add(found.group(1))

        opens = line.count("{")
        closes = line.count("}")
        depth += opens - closes
        if depth <= 0 and (opens or closes):
            inside = False

    for raw in conf.read_text(encoding="utf-8", errors="replace").splitlines():
        found = DOT_PATH.match(strip_comments(raw))
        if found:
            names.add(found.group(1))

    return sorted(names)


def scripts_dir():
    """Where these scripts live, for the hook's announcement.

    Hook commands are the one context where CLAUDE_PLUGIN_ROOT resolves; fall back to this
    file's own directory.
    """
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        return str(Path(root.rstrip("/")) / "scripts")
    return str(Path(__file__).resolve().parent)


def python_invocation():
    """How a skill should invoke these scripts, using the interpreter running right now."""
    return "{} {}".format(sys.executable or "python3", Path(__file__).name)


def run_hook():
    """SessionStart mode: announce, advise, never block."""
    directory = scripts_dir()
    print(
        "phData toolkit-core scripts (not on PATH -- invoke by absolute path, with "
        "python3): {d}/toolkit_check.py, {d}/toolkit_setup.py".format(d=directory)
    )
    print(
        "python: {} ({}.{}.{}) -- the plugins' scripts are Python 3 stdlib only".format(
            sys.executable or "python3", *sys.version_info[:3]
        )
    )

    if shutil.which("toolkit"):
        return 0

    print(
        "The phData Toolkit CLI ('toolkit') is not on PATH in this session. If the user\n"
        "asks for Toolkit work (ds scan/profile, sql translate, datagen, agent\n"
        "discovery/pipeline-build, ...), suggest running /toolkit-core:setup first to\n"
        "install and configure it (Homebrew tap on macOS, install scripts on\n"
        "Linux/Windows). Install docs:\n" + INSTALL_DOCS
    )
    return 0


def check_python(report):
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info < MIN_PYTHON:
        report.fail(
            EXIT_PYTHON,
            "python",
            "Python {} is too old; the plugins' scripts need {}.{}+".format(
                version, *MIN_PYTHON
            ),
            "install a newer Python 3 and make sure it is the one on PATH "
            "(python3 --version)",
        )
    report.ok("python", "{} ({})".format(sys.executable or "python3", version))


def check_binary(report):
    toolkit = shutil.which("toolkit")
    if not toolkit:
        report.fail(
            EXIT_NO_BINARY,
            "binary",
            "toolkit not found on PATH",
            "run /toolkit-core:setup to install and configure the Toolkit CLI",
        )

    try:
        probe = subprocess.run(
            ["toolkit", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ran = probe.returncode == 0
    except OSError:
        ran = False

    if not ran:
        if shutil.which("java"):
            java = subprocess.run(
                ["java", "-version"], capture_output=True, text=True
            )
            first = (java.stderr or java.stdout or "").splitlines()
            java_line = first[0] if first else "unknown"
            report.fail(
                EXIT_JAVA,
                "java",
                "toolkit found at {} but 'toolkit --version' failed "
                "(java present: {})".format(toolkit, java_line),
                "run /toolkit-core:setup to diagnose the install "
                "(Java version, corrupted install)",
            )
        report.fail(
            EXIT_JAVA,
            "java",
            "toolkit found at {} but won't run and no 'java' on PATH".format(toolkit),
            "install Java (e.g. 'brew install temurin'), then run /toolkit-core:setup",
        )

    report.ok("binary", toolkit)


def check_project(report):
    conf = find_project_conf()
    if conf is None:
        report.fail(
            EXIT_NO_PROJECT,
            "project",
            "no {} found in {}, its parents, or $TOOLKIT_PROJECT_HOME".format(
                CONF_NAME, Path.cwd()
            ),
            "run /toolkit-core:setup to initialize a toolkit project here",
        )
    report.ok("project", conf)

    conf_dir = conf.resolve().parent
    # Normalize before comparing, so a trailing slash or a relative
    # TOOLKIT_PROJECT_HOME does not trigger a spurious note.
    home = os.environ.get("TOOLKIT_PROJECT_HOME") or ""
    home_dir = Path(home).resolve() if home and Path(home).is_dir() else None
    if conf_dir != Path.cwd().resolve() and conf_dir != home_dir:
        report.note(
            "the toolkit only reads $TOOLKIT_PROJECT_HOME/{} (default ./{}) \u2014 run "
            "toolkit commands from {} or export TOOLKIT_PROJECT_HOME={}".format(
                CONF_NAME, CONF_NAME, conf_dir, conf_dir
            )
        )
    return conf, conf_dir


def check_datasource(report, conf, wanted):
    names = list_datasources(conf)
    if not names:
        report.fail(
            EXIT_NO_DATASOURCE,
            "datasource",
            "no datasources defined under ds.datasources in {}".format(conf),
            "run /toolkit-core:connect to add a connection and datasource",
        )
    if wanted and wanted not in names:
        report.fail(
            EXIT_NO_DATASOURCE,
            "datasource",
            "datasource '{}' not found in {} (configured: {})".format(
                wanted, conf, " ".join(names)
            ),
            "run /toolkit-core:connect to add the '{}' datasource".format(wanted),
        )
    report.ok("datasource", " ".join(names))


def check_connect(report, conf_dir, wanted):
    """`toolkit ds list` connection-tests datasources.

    Scope it with --datasource when only one matters, since any broken datasource fails the
    whole listing. TOOLKIT_PROJECT_HOME pins the probe to the conf we found, whatever the
    cwd.
    """
    env = dict(os.environ, TOOLKIT_PROJECT_HOME=str(conf_dir))
    command = ["toolkit", "ds", "list"] + ([wanted] if wanted else [])
    probe = subprocess.run(command, capture_output=True, text=True, env=env)
    if probe.returncode == 0:
        report.ok(
            "connect",
            "toolkit ds list succeeded{}".format(" for " + wanted if wanted else ""),
        )
        return

    detail = ""
    for line in (probe.stdout + probe.stderr).splitlines():
        if "⛔" in line:
            detail = re.sub(r"^⛔\S*\s*", "", line).strip()
            break
    report.fail(
        EXIT_CONNECT,
        "connect",
        detail or "toolkit ds list failed",
        "run /toolkit-core:connect to verify the connection (env vars exported? "
        "driver jar in lib/? network/VPN?)",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--level", default="datasource", choices=LEVELS)
    parser.add_argument("--datasource", default="")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--hook", action="store_true")
    parser.add_argument("--list-datasources", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        # argparse exits 2 on a bad flag or an invalid --level, which is the usage code
        # this script's contract already specifies.
        sys.stderr.write(
            "usage: toolkit_check.py [--level python|binary|project|datasource|connect] "
            "[--datasource NAME] [--quiet] [--hook] [--list-datasources]\n"
        )
        return EXIT_USAGE

    if args.help:
        print(__doc__.strip())
        return 0

    if args.hook:
        return run_hook()

    report = Reporter(args.quiet)

    if args.list_datasources:
        conf = find_project_conf()
        if conf is None:
            return EXIT_NO_PROJECT
        for name in list_datasources(conf):
            print(name)
        return 0

    check_python(report)
    if args.level == "python":
        return 0

    check_binary(report)
    if args.level == "binary":
        return 0

    conf, conf_dir = check_project(report)
    if args.level == "project":
        return 0

    check_datasource(report, conf, args.datasource)
    if args.level == "datasource":
        return 0

    check_connect(report, conf_dir, args.datasource)
    return 0


if __name__ == "__main__":
    sys.exit(main())
