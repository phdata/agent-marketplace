#!/usr/bin/env python3
"""
infa_plan.py - read the migration plan produced by `toolkit migration plan`.

Usage (run with whichever Python 3 is on PATH - `python3` on macOS/Linux, `python` or
`py` on Windows):

    python3 infa_plan.py groups    <datasource>                   TSV: wave, group, mappings, tables
    python3 infa_plan.py processes <datasource> <wave> <group>    mapping names in that group
    python3 infa_plan.py wave-id   <wave> <group>                 wave directory name
    python3 infa_plan.py snapshot  <datasource>                   path to the latest snapshot
    python3 infa_plan.py summary   <datasource>                   the plan's summary block

Reads <project>/tools/migration/snapshots/migration-plan/<timestamp>_<datasource>.json directly.
`toolkit migration show <ds>:migration-plan:latest` cannot be used: it fails to deserialize any
plan containing Informatica processes (`Unrecognized field "componentCount"`), in every
format.

Three shapes in that snapshot bite when queried by hand, so they are handled here once:
  - a group's `processes` and `tables` keys may be absent entirely
  - wave numbers do not necessarily start at 0
  - only processes with kind INFORMATICA_MAPPING are this plugin's work; a group can hold
    SQL scripts or be table-only

Process ids are `informatica/<folder>/<mapping>`; `processes` prints the mapping name only
(the last segment), which is what infa_corpus.py's `find` takes.

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

MAPPING_KIND = "INFORMATICA_MAPPING"
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
        sys.stderr.write("infa_plan: no migration-plan snapshot for datasource '{}' under {}\n"
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
        sys.stderr.write("infa_plan: {} is not valid JSON: {}\n".format(path, err))
        sys.exit(5)


def iter_groups(plan):
    """(wave_number, group) for every group, in snapshot order."""
    for wave in plan.get("waves") or []:
        for group in wave.get("groups") or []:
            yield wave.get("number"), group


def mappings_in(group):
    """The Informatica mapping names in a group, in snapshot order."""
    names = []
    for process in group.get("processes") or []:
        if process.get("kind") != MAPPING_KIND:
            continue
        # 'informatica/<folder>/<mapping>' -> '<mapping>'
        names.append(str(process.get("id", "")).split("/")[-1])
    return names


def sanitize(name):
    """Directory-safe form of a plan group name, e.g. '(default)' -> '_default_'."""
    return UNSAFE_CHARS.sub("_", name)


def cmd_groups(args):
    plan = load_plan(args.datasource)
    for number, group in iter_groups(plan):
        print("\t".join([
            str(number),
            str(group.get("name", "")),
            str(len(mappings_in(group))),
            str(len(group.get("tables") or [])),
        ]))


def cmd_processes(args):
    plan = load_plan(args.datasource)
    found_group = False
    for number, group in iter_groups(plan):
        if number != args.wave or group.get("name") != args.group:
            continue
        found_group = True
        for name in mappings_in(group):
            print(name)
    if not found_group:
        sys.stderr.write("infa_plan: no group named '{}' in wave {}\n"
                         .format(args.group, args.wave))
        sys.stderr.write("hint: run 'infa_plan.py groups {}' to list wave/group names "
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
        prog="infa_plan.py",
        description="Read a toolkit migration plan snapshot.")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("groups", help="TSV: wave, group, mappings, tables")
    p.add_argument("datasource")
    p.set_defaults(func=cmd_groups)

    p = sub.add_parser("processes", help="mapping names in one group")
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
