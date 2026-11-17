#!/usr/bin/env python3
"""
proc_plan.py - read the migration plan produced by `toolkit migration plan`,
for the stored procedures in it.

Usage (run with whichever Python 3 is on PATH - `python3` on macOS/Linux, `python` or
`py` on Windows):

    python3 proc_plan.py groups    <datasource>                   TSV: wave, group, procedures, tables
    python3 proc_plan.py processes <datasource> <wave> <group>    procedure script paths in that group
    python3 proc_plan.py wave-id   <wave> <group>                 wave directory name
    python3 proc_plan.py snapshot  <datasource>                   path to the latest snapshot
    python3 proc_plan.py summary   <datasource>                   the plan's summary block

Reads <project>/tools/migration/snapshots/migration-plan/<timestamp>_<datasource>.json directly,
rather than through `toolkit migration show <ds>:migration-plan:latest`. A plan holding only
stored procedures would in fact round-trip through that command - `etlStats` is null on SQL-only
processes, so the field that breaks it is never written - but the moment the same plan also holds
Informatica mappings or SSIS packages it fails to deserialize in every format
(`Unrecognized field "componentCount"`). Reading the file works either way, and starts no JVM.

Three shapes in that snapshot bite when queried by hand, so they are handled here once:
  - a group's `processes` and `tables` keys may be absent entirely
  - wave numbers do not necessarily start at 0
  - only processes with kind SCRIPT_FILE are this plugin's work; a group can also hold
    Informatica mappings, SSIS packages, bare query patterns, or be table-only

A SCRIPT_FILE process id IS the collected script's file path, so `processes` prints those paths
verbatim - they are what `etl-extract` takes as input. Match them to the .sql files on disk by
basename when the collection directory has been moved since the plan was cut.

Python 3 standard library only - no jq, no packages - so this behaves the same on Windows,
macOS, and Linux.

Exit codes: 0 success, 2 usage error, 3 no snapshot found, 5 snapshot is not valid JSON.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Windows consoles, and any redirected output, default to the locale encoding - cp1252 on
# most Western installs - which cannot represent characters that routinely show up in the
# text these scripts print back: arrows in a join path, the toolkit's own status glyphs,
# CJK in a table or column name. Printing one raises UnicodeEncodeError and kills the
# script mid-report, so degrade to a replacement character instead of dying.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # not a TextIOWrapper (captured/replaced stream)
        pass

PROCEDURE_KIND = "SCRIPT_FILE"
# Every character a directory name may keep; anything else becomes '_'. Mirrors the
# `tr -c 'A-Za-z0-9._-' '_'` this script replaced, so wave directory names do not change.
UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def project_root():
    """The toolkit project, the way the toolkit itself resolves it."""
    return Path(os.environ.get("TOOLKIT_PROJECT_HOME") or ".")


def latest_snapshot(datasource):
    directory = project_root() / "tools" / "migration" / "snapshots" / "migration-plan"
    # Snapshot names are '<timestamp>_<datasource>.json', so a plain sort is newest-last.
    candidates = sorted(directory.glob("*_{}.json".format(datasource)))
    if not candidates:
        sys.stderr.write("proc_plan: no migration-plan snapshot for datasource '{}' under {}\n"
                         .format(datasource, directory))
        sys.stderr.write("hint: run 'toolkit migration plan {}' first, from the toolkit "
                         "project directory\n".format(datasource))
        sys.exit(3)
    return candidates[-1]


def load_plan(datasource):
    path = latest_snapshot(datasource)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as err:
        sys.stderr.write("proc_plan: {} is not valid JSON: {}\n".format(path, err))
        sys.exit(5)


def iter_groups(plan):
    """(wave_number, group) for every group, in snapshot order."""
    for wave in plan.get("waves") or []:
        for group in wave.get("groups") or []:
            yield wave.get("number"), group


def procedures_in(group):
    """The stored-procedure script paths in a group, in snapshot order.

    A SCRIPT_FILE id is the file path the script was collected from, so it is returned whole
    rather than reduced to a last segment: the path is what identifies the procedure.
    """
    return [
        str(process.get("id", ""))
        for process in group.get("processes") or []
        if process.get("kind") == PROCEDURE_KIND
    ]


def sanitize(name):
    """Directory-safe form of a plan group name, e.g. '(default)' -> '_default_'."""
    return UNSAFE_CHARS.sub("_", name)


def cmd_groups(args):
    plan = load_plan(args.datasource)
    for number, group in iter_groups(plan):
        print("\t".join([
            str(number),
            str(group.get("name", "")),
            str(len(procedures_in(group))),
            str(len(group.get("tables") or [])),
        ]))


def cmd_processes(args):
    plan = load_plan(args.datasource)
    found_group = False
    for number, group in iter_groups(plan):
        if number != args.wave or group.get("name") != args.group:
            continue
        found_group = True
        for path in procedures_in(group):
            print(path)
    if not found_group:
        sys.stderr.write("proc_plan: no group named '{}' in wave {}\n"
                         .format(args.group, args.wave))
        sys.stderr.write("hint: run 'proc_plan.py groups {}' to list wave/group names "
                         "exactly as the plan spells them\n".format(args.datasource))
        sys.exit(3)


def cmd_wave_id(args):
    print("w{}-{}".format(args.wave, sanitize(args.group)))


def cmd_snapshot(args):
    print(latest_snapshot(args.datasource))


def cmd_summary(args):
    plan = load_plan(args.datasource)
    summary = plan.get("summary") or {}
    if not summary:
        print("(this snapshot has no summary block)")
        return
    width = max(len(k) for k in summary)
    for key in sorted(summary):
        print("{}  {}".format(key.ljust(width), summary[key]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="proc_plan.py",
        description="Read the stored procedures in a toolkit migration plan snapshot.")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("groups", help="TSV: wave, group, procedures, tables")
    p.add_argument("datasource")
    p.set_defaults(func=cmd_groups)

    p = sub.add_parser("processes", help="procedure script paths in one group")
    p.add_argument("datasource")
    # The snapshot stores wave numbers as JSON numbers, so compare as an int.
    p.add_argument("wave", type=int)
    p.add_argument("group")
    p.set_defaults(func=cmd_processes)

    p = sub.add_parser("wave-id", help="wave directory name for a group")
    p.add_argument("wave")
    p.add_argument("group")
    p.set_defaults(func=cmd_wave_id)

    p = sub.add_parser("snapshot", help="path to the latest plan snapshot")
    p.add_argument("datasource")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("summary", help="the plan's summary block")
    p.add_argument("datasource")
    p.set_defaults(func=cmd_summary)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
