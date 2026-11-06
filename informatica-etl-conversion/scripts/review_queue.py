#!/usr/bin/env python3
"""
review_queue.py - collapse the human-review items across many data contracts into one
distinct list, so a question that shows up in twelve contracts is answered once.

Usage (run with whichever Python 3 is on PATH - `python3` on macOS/Linux, `python` or
`py` on Windows):

    python3 review_queue.py list    [--dir discovery-out] [--all]
    python3 review_queue.py show    <group> [--dir discovery-out]
    python3 review_queue.py comment <group> "the decision" [--dir discovery-out]
                                    [--overwrite] [--dry-run]

`list`     one line per distinct question: how many items share it, its tag, its shape,
           and which contracts it appears in. Groups are numbered; the numbers are
           stable for a given set of contracts, so `show 3` and `comment 3` agree.
`show`     every item in one group, with its contract, full description, current
           comment, and resolver note.
`comment`  write one decision into every item in a group, across every contract that
           has it. The `--resolve` sweep then applies it everywhere at once.

Why this exists: the same idiom appears across many target tables, so the review queue
is mostly repeats. `toolkit agent discovery --resolve` applies one comment per item, and
items that repeat each other's change are both applied - so one decision broadcast to a
whole group is the cheap path through a long queue. Reading and commenting item by item
is the expensive one.

Grouping: items are bucketed by their `[TAG]` plus the *shape* of their description -
the description with object names, bare identifiers, quoted literals, and numbers
replaced by placeholders. Two items asking the same question about different columns
therefore land in the same group. Shaping is a heuristic for presentation only; it never
changes a contract. Always read a group with `show` before commenting on it.

Writing: `comment` reserializes the contract as 2-space-indented JSON, preserving key
order and the file's own trailing newline. That is byte-identical for contracts written
by a current toolkit. A contract written by an older toolkit used a different pretty
printer, so it gets reformatted once - cosmetic only, and `--resolve` rewrites it anyway.

No third-party packages, and no jq: this runs the same on Windows, macOS, and Linux.

Exit codes: 0 success, 2 usage error, 3 no contracts found, 4 no such group,
            5 a contract could not be parsed.
"""

import argparse
import json
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

CONTRACT_NAME = "data-contract.json"

TAG_RE = re.compile(r"^\[(?P<tag>[A-Z][A-Z ]*)\]\s*")
QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
QUALIFIED_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+")
# An upper-case identifier NOT followed by '(' - a bare column or table name rather
# than a function call, so TO_DATE(...) keeps its name and the group stays meaningful.
UPPER_IDENT_RE = re.compile(r"\b[A-Z][A-Z0-9_]+\b(?!\s*\()")
# A lower-case snake_case identifier. Target columns are usually written this way, and
# requiring an underscore is what keeps ordinary prose words out of it.
SNAKE_IDENT_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def shape(description):
    """The description with its specifics replaced by placeholders.

    Only ever used as a grouping key, never shown as the question: the list prints one
    member's real description instead, so aggressive shaping costs nothing in
    readability. That matters because the items worth collapsing differ exactly in the
    identifiers this removes.
    """
    text = TAG_RE.sub("", description)
    text = QUOTED_RE.sub("<literal>", text)
    text = QUALIFIED_RE.sub("<object>", text)
    text = UPPER_IDENT_RE.sub("<name>", text)
    text = SNAKE_IDENT_RE.sub("<name>", text)
    text = NUMBER_RE.sub("<n>", text)
    return " ".join(text.split())


def one_line(text, width=150):
    """Whitespace collapsed to a single line, truncated for the list view."""
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 3] + "..."


def tag_of(description):
    found = TAG_RE.match(description)
    return found.group("tag") if found else "UNTAGGED"


def load_contracts(root):
    """Every <root>/*/data-contract.json, plus <root>/data-contract.json."""
    if not root.is_dir():
        sys.stderr.write("review_queue: not a directory: {}\n".format(root))
        sys.stderr.write("hint: pass --dir, or run from the toolkit project holding "
                         "discovery-out/\n")
        sys.exit(3)

    paths = sorted(root.glob("*/" + CONTRACT_NAME))
    direct = root / CONTRACT_NAME
    if direct.is_file():
        paths.append(direct)
    if not paths:
        sys.stderr.write("review_queue: no {} under {}\n".format(CONTRACT_NAME, root))
        sys.stderr.write("hint: run 'toolkit agent discovery' first\n")
        sys.exit(3)

    contracts = []
    for path in paths:
        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except ValueError as err:
            sys.stderr.write("review_queue: {} is not valid JSON: {}\n".format(path, err))
            sys.exit(5)
        contracts.append({
            "path": path,
            "name": path.parent.name if path.name == CONTRACT_NAME else path.stem,
            "data": data,
            "trailing_newline": raw.endswith("\n"),
        })
    return contracts


def collect_items(contracts):
    items = []
    for contract in contracts:
        stm = contract["data"].get("sourceToTarget") or {}
        for index, item in enumerate(stm.get("humanReviewItems") or []):
            description = item.get("description", "")
            items.append({
                "contract": contract,
                "index": index,
                "description": description,
                "comment": item.get("comment", "") or "",
                "note": item.get("resolverNote", "") or "",
                "tag": tag_of(description),
                "shape": shape(description),
            })
    return items


def group_items(items):
    buckets = {}
    for item in items:
        buckets.setdefault((item["tag"], item["shape"]), []).append(item)
    # Biggest groups first - that is the order worth working in. Ties break on tag then
    # shape so the numbering is stable across runs for an unchanged set of contracts.
    return sorted(buckets.values(), key=lambda g: (-len(g), g[0]["tag"], g[0]["shape"]))


def pick(groups, number):
    if number < 1 or number > len(groups):
        sys.stderr.write("review_queue: no group {} (there are {})\n"
                         .format(number, len(groups)))
        sys.exit(4)
    return groups[number - 1]


def needs_attention(group):
    """An item with no comment needs a decision; one with a resolver note needs a
    better one, because the last sweep refused to apply what it had. Only a group that
    is commented across the board and carries no note is genuinely waiting on nothing
    but the next --resolve."""
    return any(not item["comment"] or item["note"] for item in group)


def cmd_list(groups, show_all):
    total = sum(len(g) for g in groups)
    undecided = sum(1 for g in groups for i in g if not i["comment"])
    rejected = sum(1 for g in groups for i in g if i["note"])
    waiting = total - undecided - rejected
    hidden = [g for g in groups if not needs_attention(g)]

    print("{} review item(s) across {} distinct question(s)".format(total, len(groups)))
    print("  {} need a decision".format(undecided))
    if rejected:
        print("  {} were commented and NOT APPLIED by the last sweep".format(rejected))
    if waiting:
        print("  {} commented, waiting on the next --resolve".format(waiting))
    if hidden and not show_all:
        print("")
        print("({} group(s) need nothing and are hidden - pass --all to see them)"
              .format(len(hidden)))
    print("")

    shown = 0
    for number, group in enumerate(groups, start=1):
        if not show_all and not needs_attention(group):
            continue
        shown += 1
        contracts = sorted({i["contract"]["name"] for i in group})
        commented = sum(1 for i in group if i["comment"])
        notes = sum(1 for i in group if i["note"])

        flags = []
        if notes:
            flags.append("{} NOT APPLIED - read the resolver note before recommenting"
                         .format(notes))
        elif commented:
            flags.append("{}/{} already commented".format(commented, len(group)))

        example = one_line(TAG_RE.sub("", group[0]["description"]))
        print("#{}  {}x  [{}]  {}".format(number, len(group), group[0]["tag"], example))
        if len(group) > 1:
            print("      e.g. above; {} items differing only in names/values"
                  .format(len(group)))
        print("      contracts: {}".format(", ".join(contracts)))
        if flags:
            print("      {}".format("; ".join(flags)))
        print("")

    if shown:
        print("Read one group before deciding:   review_queue.py show <group>")
        print("Answer it everywhere at once:     review_queue.py comment <group> \"...\"")
    else:
        print("Nothing needs a decision. Sweep the contracts with --resolve.")


def cmd_show(groups, number):
    group = pick(groups, number)
    print("#{}  {} item(s)  [{}]".format(number, len(group), group[0]["tag"]))
    print("shape: {}".format(group[0]["shape"]))
    print("")
    for item in sorted(group, key=lambda i: (i["contract"]["name"], i["index"])):
        print("  {} (item {})".format(item["contract"]["name"], item["index"] + 1))
        print("    {}".format(item["description"]))
        if item["comment"]:
            print("    comment: {}".format(item["comment"]))
        if item["note"]:
            print("    NOT APPLIED: {}".format(item["note"]))
        print("")


def cmd_comment(groups, number, text, overwrite, dry_run):
    group = pick(groups, number)
    if not text.strip():
        sys.stderr.write("review_queue: the decision text is empty\n")
        sys.exit(2)

    touched, skipped = [], []
    for item in group:
        if item["comment"] and not overwrite:
            skipped.append(item)
            continue
        items = item["contract"]["data"]["sourceToTarget"]["humanReviewItems"]
        items[item["index"]]["comment"] = text
        touched.append(item)

    if not dry_run:
        for contract in {id(i["contract"]): i["contract"] for i in touched}.values():
            body = json.dumps(contract["data"], indent=2, ensure_ascii=False)
            if contract["trailing_newline"]:
                body += "\n"
            contract["path"].write_text(body, encoding="utf-8")

    verb = "would comment" if dry_run else "commented"
    print("{} {} item(s) in group #{}:".format(verb, len(touched), number))
    for item in sorted(touched, key=lambda i: i["contract"]["name"]):
        print("  {} (item {})".format(item["contract"]["name"], item["index"] + 1))
    if skipped:
        print("left {} item(s) with an existing comment alone "
              "(pass --overwrite to replace):".format(len(skipped)))
        for item in sorted(skipped, key=lambda i: i["contract"]["name"]):
            print("  {} (item {}): {}".format(item["contract"]["name"],
                                              item["index"] + 1, item["comment"]))
    if touched and not dry_run:
        print("")
        print("Now sweep every contract with 'toolkit agent discovery <ds> <spec> "
              "--resolve <contract>'.")


def cmd_status(contracts):
    """Per-contract approval and open-item counts - the progress view."""
    rows = []
    for contract in contracts:
        stm = contract["data"].get("sourceToTarget") or {}
        items = stm.get("humanReviewItems") or []
        rows.append((
            contract["name"],
            bool(contract["data"].get("approvedByHuman")),
            len(items),
            sum(1 for i in items if (i.get("comment") or "")),
            sum(1 for i in items if (i.get("resolverNote") or "")),
        ))

    width = max([len(r[0]) for r in rows] + [8])
    print("{}  {:<8} {:>4} {:>9} {:>11}".format(
        "contract".ljust(width), "approved", "open", "commented", "notapplied"))
    for name, approved, total, commented, notes in sorted(rows):
        print("{}  {:<8} {:>4} {:>9} {:>11}".format(
            name.ljust(width), "yes" if approved else "no", total, commented, notes))

    approved_count = sum(1 for r in rows if r[1])
    print("")
    print("{}/{} contract(s) approved; {} open item(s)"
          .format(approved_count, len(rows), sum(r[2] for r in rows)))
    if approved_count < len(rows):
        print("Unapproved contracts are not built: pipeline-build skips them.")


def main(argv=None):
    dir_help = ("directory holding <name>/data-contract.json "
                "(default: discovery-out)")
    # Declared twice on purpose, so --dir works on either side of the subcommand.
    # SUPPRESS on the subcommand copy means an absent flag there leaves the value the
    # main parser already set, instead of overwriting it with the default.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", metavar="DIR", default=argparse.SUPPRESS,
                        help=dir_help)

    parser = argparse.ArgumentParser(
        prog="review_queue.py",
        description="Collapse human-review items across data contracts into one "
                    "distinct list.")
    parser.add_argument("--dir", default="discovery-out", metavar="DIR", help=dir_help)
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", parents=[common],
                            help="one line per distinct question")
    p_list.add_argument("--all", action="store_true",
                        help="include groups that need nothing")

    sub.add_parser("status", parents=[common],
                   help="per-contract approval and open-item counts")

    p_show = sub.add_parser("show", parents=[common], help="every item in one group")
    p_show.add_argument("group", type=int)

    p_comment = sub.add_parser("comment", parents=[common],
                               help="write one decision across a whole group")
    p_comment.add_argument("group", type=int)
    p_comment.add_argument("text")
    p_comment.add_argument("--overwrite", action="store_true",
                           help="replace comments that are already there")
    p_comment.add_argument("--dry-run", action="store_true",
                           help="print what would change, write nothing")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    contracts = load_contracts(Path(args.dir))
    if args.command == "status":
        cmd_status(contracts)
        return 0

    groups = group_items(collect_items(contracts))
    if not groups:
        print("No human-review items in {} contract(s) under {} - nothing to review."
              .format(len(contracts), args.dir))
        return 0

    if args.command == "list":
        cmd_list(groups, args.all)
    elif args.command == "show":
        cmd_show(groups, args.group)
    elif args.command == "comment":
        cmd_comment(groups, args.group, args.text, args.overwrite, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
