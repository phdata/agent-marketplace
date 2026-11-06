#!/usr/bin/env python3
"""
plan.py - read a migration plan produced by `toolkit migration plan`.

Usage (run with whichever Python 3 is on PATH - `python3` on macOS/Linux, `python` or
`py -3` on Windows):

    python3 plan.py groups    <datasource>                     TSV: wave, group, counts by kind, tables
    python3 plan.py processes <datasource> <wave> <group>       every process id in that group
    python3 plan.py processes <datasource> <wave> <group> --kind SCRIPT_FILE
    python3 plan.py kinds     <datasource>                      how many processes of each kind, estate-wide
    python3 plan.py wave-id   <wave> <group>                    directory-safe name for a group
    python3 plan.py snapshot  <datasource>                      path to the latest snapshot
    python3 plan.py summary   <datasource>                      the plan's summary block

Unlike the conversion plugins' readers, this one assumes nothing about what the estate holds:
an assessment is the step that finds out. `groups` therefore breaks each group down by process
kind rather than counting one of them, and `processes` returns every kind unless `--kind`
narrows it.

The four kinds a plan can contain, and who converts them:

    SCRIPT_FILE         an imported script file - a stored procedure, a BTEQ script, a job.
                        Convertible for SQL Server and Oracle via procedure-etl-conversion.
    INFORMATICA_MAPPING a mapping from an ETL import. Convertible via
                        informatica-etl-conversion.
    SSIS_PACKAGE        an SSIS package from an ETL import or catalog DDL collection.
                        Assessable only - no converter today.
    QUERY_PATTERN       a single query pattern with no file provenance, typically from
                        collected query history. Assessable only.

A group with processes but none of a convertible kind is still real migration work; a group with
no processes at all is table-only. Both are easy to misreport as untouched, which is why `groups`
prints the breakdown.

Reads <project>/tools/migration/snapshots/migration-plan/<timestamp>_<datasource>.json directly,
rather than through `toolkit migration show <ds>:migration-plan:latest`. That command fails to
deserialize any plan containing Informatica or SSIS processes (`Unrecognized field
"componentCount"`, in every format) because the field is a computed getter with no constructor
parameter; a plan of only SQL-only processes round-trips fine, since `etlStats` is null on those.
Reading the file works either way, and starts no JVM.

Two snapshot shapes bite when queried by hand, so they are handled here once:
  - a group's `processes` and `tables` keys may be absent entirely
  - wave numbers do not necessarily start at 0

Python 3 standard library only - no jq, no packages - so this behaves the same on Windows,
macOS, and Linux.

Exit codes: 0 success, 2 usage error, 3 no snapshot or no such group, 5 snapshot is not valid
JSON.
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

# Every kind a plan can hold, in the order the breakdown prints them.
KINDS = ("SCRIPT_FILE", "INFORMATICA_MAPPING", "SSIS_PACKAGE", "QUERY_PATTERN")
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
        sys.stderr.write("plan: no migration-plan snapshot for datasource '{}' under {}\n"
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
        sys.stderr.write("plan: {} is not valid JSON: {}\n".format(path, err))
        sys.exit(5)


def iter_groups(plan):
    """(wave_number, group) for every group, in snapshot order."""
    for wave in plan.get("waves") or []:
        for group in wave.get("groups") or []:
            yield wave.get("number"), group


def processes_in(group, kind=None):
    """Process ids in a group, in snapshot order, optionally of one kind only."""
    return [
        str(process.get("id", ""))
        for process in group.get("processes") or []
        if kind is None or process.get("kind") == kind
    ]


def counts_by_kind(group):
    """How many processes of each known kind the group holds, plus anything unrecognized."""
    tally = {kind: 0 for kind in KINDS}
    other = 0
    for process in group.get("processes") or []:
        kind = process.get("kind")
        if kind in tally:
            tally[kind] += 1
        else:
            other += 1
    return tally, other


def sanitize(name):
    """Directory-safe form of a plan group name, e.g. '(default)' -> '_default_'."""
    return UNSAFE_CHARS.sub("_", name)


def cmd_groups(args):
    plan = load_plan(args.datasource)
    print("\t".join(["wave", "group", "processes"] + [k.lower() for k in KINDS]
                     + ["other", "tables"]))
    for number, group in iter_groups(plan):
        tally, other = counts_by_kind(group)
        total = sum(tally.values()) + other
        print("\t".join([
            str(number),
            str(group.get("name", "")),
            str(total),
        ] + [str(tally[k]) for k in KINDS] + [
            str(other),
            str(len(group.get("tables") or [])),
        ]))


def cmd_kinds(args):
    """Estate-wide process counts by kind — what this plan actually contains."""
    plan = load_plan(args.datasource)
    totals = {kind: 0 for kind in KINDS}
    other = 0
    groups = 0
    tables = 0
    for _, group in iter_groups(plan):
        groups += 1
        tables += len(group.get("tables") or [])
        tally, extra = counts_by_kind(group)
        other += extra
        for kind in KINDS:
            totals[kind] += tally[kind]

    convertible = {
        "SCRIPT_FILE": "procedure-etl-conversion (SQL Server / Oracle procedures)",
        "INFORMATICA_MAPPING": "informatica-etl-conversion",
        "SSIS_PACKAGE": "no converter - assessable only",
        "QUERY_PATTERN": "no converter - assessable only",
    }
    width = max(len(k) for k in KINDS)
    for kind in KINDS:
        print("{}  {:>6}   {}".format(kind.ljust(width), totals[kind], convertible[kind]))
    if other:
        print("{}  {:>6}   unrecognized kind - a newer toolkit than this script knows"
              .format("OTHER".ljust(width), other))
    print("")
    print("{} group(s), {} table(s), {} process(es)".format(
        groups, tables, sum(totals.values()) + other))


def cmd_processes(args):
    plan = load_plan(args.datasource)
    found_group = False
    for number, group in iter_groups(plan):
        if number != args.wave or group.get("name") != args.group:
            continue
        found_group = True
        for path in processes_in(group, args.kind):
            print(path)
    if not found_group:
        sys.stderr.write("plan: no group named '{}' in wave {}\n"
                         .format(args.group, args.wave))
        sys.stderr.write("hint: run 'plan.py groups {}' to list wave/group names exactly as "
                         "the plan spells them\n".format(args.datasource))
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
        prog="plan.py",
        description="Read a toolkit migration plan snapshot.")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("groups", help="TSV: wave, group, counts by kind, tables")
    p.add_argument("datasource")
    p.set_defaults(func=cmd_groups)

    p = sub.add_parser("kinds", help="estate-wide process counts by kind")
    p.add_argument("datasource")
    p.set_defaults(func=cmd_kinds)

    p = sub.add_parser("processes", help="process ids in one group")
    p.add_argument("datasource")
    p.add_argument("--kind", choices=KINDS, default=None,
                   help="only processes of this kind (default: every kind)")
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
