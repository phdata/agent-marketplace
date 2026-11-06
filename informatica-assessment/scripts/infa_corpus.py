#!/usr/bin/env python3
"""
infa_corpus.py - read an Informatica PowerCenter export corpus.

Usage (run with whichever Python 3 is on PATH - `python3` on macOS/Linux, `python` or
`py` on Windows):

    python3 infa_corpus.py count [corpus-dir]             number of mappings in the corpus
    python3 infa_corpus.py list  [corpus-dir]             every mapping name, one per line
    python3 infa_corpus.py find  <mapping> [corpus-dir]   files containing that mapping

corpus-dir defaults to ./informatica-xml

Why this exists: the matching pattern is subtle in three ways that are easy to get wrong
when retyped, and getting them wrong fails silently.
  - requiring whitespace after <MAPPING excludes <MAPPINGVARIABLE NAME="...">, which would
    otherwise inflate counts and match variables that share a mapping's name
  - the optional spaces around '=' cover both NAME="x" (common) and NAME ="x", which
    Repository Manager writes
  - anchoring on '<MAPPING' rather than a bare NAME= avoids a workflow's MAPPINGNAME ="x"
    session attribute, which would otherwise return every workflow that schedules the
    mapping

Case-insensitive throughout: real exports use both .xml and .XML, and element case varies.
Unlike the line-based shell version this replaced, the whole file is searched at once, so a
<MAPPING element whose NAME attribute sits on a later line is now matched too.

Python 3 standard library only - no jq, no grep, no packages - so this behaves the same on
Windows, macOS, and Linux.

Exit codes: 0 success, 2 usage error, 3 corpus directory not found, 4 no match.
"""

import argparse
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

DEFAULT_CORPUS = "informatica-xml"

# <MAPPING ... NAME="the mapping name" ... >
#   \s        at least one space/newline after <MAPPING, so <MAPPINGVARIABLE cannot match
#   [^>]*     other attributes, possibly across lines, but never past the element's '>'
#   \s?=\s?   both NAME="x" and NAME ="x"
MAPPING_NAME = re.compile(r"<MAPPING\s[^>]*?\bNAME\s?=\s?\"([^\"]+)\"", re.IGNORECASE)


def mapping_name_pattern(name):
    """The same pattern, pinned to one literal mapping name."""
    return re.compile(
        r"<MAPPING\s[^>]*?\bNAME\s?=\s?\"{}\"".format(re.escape(name)),
        re.IGNORECASE,
    )


def xml_files(corpus):
    """Every *.xml in the corpus, any case, sorted for stable output."""
    return sorted(p for p in corpus.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".xml")


def read(path):
    """File text, tolerating the encodings real exports arrive in."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Repository Manager sometimes writes windows-1252; never fail the whole scan
        # because one file is not UTF-8.
        return path.read_text(encoding="latin-1")


def require_dir(corpus):
    if not corpus.is_dir():
        sys.stderr.write("infa_corpus: corpus directory not found: {}\n".format(corpus))
        sys.stderr.write("hint: pass the directory explicitly, or run from the toolkit "
                         "project holding {}/\n".format(DEFAULT_CORPUS))
        sys.exit(3)
    return corpus


def mapping_names(corpus):
    """Every mapping name in the corpus, in file order, duplicates kept.

    Duplicates are meaningful: the same mapping name can exist in two repository folders,
    and the count is of MAPPING elements, not of distinct names.
    """
    names = []
    for path in xml_files(corpus):
        names.extend(MAPPING_NAME.findall(read(path)))
    return names


def cmd_count(args):
    print(len(mapping_names(require_dir(Path(args.corpus)))))


def cmd_list(args):
    for name in sorted(mapping_names(require_dir(Path(args.corpus)))):
        print(name)


def cmd_find(args):
    corpus = require_dir(Path(args.corpus))
    pattern = mapping_name_pattern(args.mapping)
    matches = [p for p in xml_files(corpus) if pattern.search(read(p))]
    if not matches:
        sys.stderr.write("infa_corpus: no file in {} contains mapping '{}'\n"
                         .format(corpus, args.mapping))
        sys.exit(4)
    for path in matches:
        print(path)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="infa_corpus.py",
        description="Read an Informatica PowerCenter export corpus.")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("count", help="number of MAPPING elements in the corpus")
    p.add_argument("corpus", nargs="?", default=DEFAULT_CORPUS)
    p.set_defaults(func=cmd_count)

    p = sub.add_parser("list", help="every mapping name, sorted")
    p.add_argument("corpus", nargs="?", default=DEFAULT_CORPUS)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("find", help="which XML file(s) contain a mapping")
    p.add_argument("mapping")
    p.add_argument("corpus", nargs="?", default=DEFAULT_CORPUS)
    p.set_defaults(func=cmd_find)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
