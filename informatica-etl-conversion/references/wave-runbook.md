# Wave execution runbook

Mechanics behind `/informatica-etl-conversion:wave`.

## The corpus

Everything starts from `informatica-xml/` in the toolkit project: a directory of exported
PowerCenter XML, copied in with its structure intact, because the directory holding each file is
the `<folder>` segment of its plan process id. `/informatica-assessment:collect` puts it there,
and `:wave` copies it in when that plugin isn't in play.

Format facts that affect extraction, all handled rather than needing cleanup:

- One `MAPPING` element per mapping, and **several mappings can share a file** — which is why
  counts come from element matching, not `ls`, and why staging one file can drag in mappings
  belonging to other groups (see below).
- `DOCTYPE` declarations pointing at `powrmart.dtd` are normal; external entity resolution is
  off and the DTD is never fetched.
- Both `NAME="x"` and `NAME ="x"` appear in real exports, and case varies (`.xml`, `.XML`).
- A file that fails to parse is **warned about on the console and skipped** — not fatal, and
  recorded nowhere else. That is why the extract steps `tee` their output.
- Non-XML files are ignored, so an export shipped alongside logs or READMEs needs no cleaning.
- Mapping dependencies (sources, targets, mapplets, reusable transformations) must be in the
  export, inline or as sibling files. Without them, extraction sees ports whose definitions are
  missing and column derivations come out incomplete.

What a complete export contains, and what to ask the exporter for when something is missing, is
in `references/corpus-guide.md` in the informatica-assessment plugin. The analyzer scan in
`/informatica-assessment:collect` is the real completeness check — worth running even on the
direct path, since it is free and needs no datasource.

## Wave directory layout

```
waves/w<wave>-<group>/          planned mode — one directory per plan group
waves/all/                      direct mode  — one directory for the whole corpus
  xml/                          staged copies of this group's mapping XML (planned mode only)
  etl-extract-dryrun.log        tee'd cost preview  (the only record of it)
  etl-extract.log               tee'd extraction    (the only record of skipped files)
  etl-specs/                    <mapping>__<target>.discovery.yaml — the wave's live set
  etl-specs/_out-of-scope/      specs for mappings belonging to other groups
  discovery-out/<spec-stem>/    data-contract.json + discovery-report.txt
  pipeline-out/<spec-stem>/     build-report.txt, transforms/, tests/, mockdata/
  wave-report.md               human deliverable; nothing parses it
```

Directory id in planned mode: `w<wave>-<group>`, with the group name sanitized (direct mode
just uses `all`):

```bash
ID="w${WAVE}-$(printf '%s' "$GROUP" | tr -c 'A-Za-z0-9._-' '_')"
```

`printf` rather than `echo` — a trailing newline would become a trailing underscore. Plan group
names like `(default)` and `DW-2` sanitize to `_default_` and `DW-2`.

## Matching plan processes to XML files

Process ids are `informatica/<folder>/<mapping>`, where `<folder>` defaults to the XML file's
parent directory name at collect time. The mapping name is the last `/`-separated segment,
which is what `infa_plan.py processes` prints and `infa_corpus.py find` takes.

```bash
python3 <plugin>/scripts/infa_plan.py processes <ds> <wave> '<group>'   # mapping names in the group
python3 <plugin>/scripts/infa_corpus.py find <mapping>                  # files containing that mapping
```

**Content matching is authoritative** — export filenames frequently don't match mapping names
(`synthetic_dim_upsert.xml` holds `m_dim_thing_insupd`), so a filename search misses most
mappings. `infa_corpus.py` owns the pattern so it isn't retyped; the three details it encodes,
each of which fails silently when dropped:

- the space after `<MAPPING` excludes `<MAPPINGVARIABLE NAME="...">`, which otherwise inflates
  counts and can match a variable sharing a mapping's name
- `?` around `=` covers both `NAME="x"` and `NAME ="x"` (Repository Manager writes the latter)
- anchoring on `<MAPPING` rather than a bare `NAME=` avoids a workflow's `MAPPINGNAME ="x"`
  session attribute, which would return every workflow that schedules the mapping

When several files match, prefer the one whose parent directory equals the `<folder>` segment.

**Nothing matched?** (`infa_corpus.py find` exits 4.) Likely causes, in order: a directory inside
`informatica-xml/` was renamed since the import, which also changes process ids; the mapping was
dropped from a re-export copied over the corpus; the plan predates the current corpus. Show the
user the unmatched ids and resolve together — the collected store keeps the original file path
but is toolkit-internal and not for querying.

Counting the corpus (for sizing, and for direct mode's scope):

```bash
python3 <plugin>/scripts/infa_corpus.py count
```

## Multi-mapping files

A staged file holding several mappings emits specs for all of them. Expected; handle it after
extraction, never by editing the XML:

```bash
mkdir -p waves/<id>/etl-specs/_out-of-scope
# for each spec whose <mapping> prefix is not in the group's process list:
mv "waves/<id>/etl-specs/<mapping>__<target>.discovery.yaml" waves/<id>/etl-specs/_out-of-scope/
```

Keep them. When that mapping's own group runs, re-extraction is cheap — translated expressions
are cached on disk under `tools/agent/etl-extract/cache/`.

## Review queue presentation

A review item is `{"description": "...", "comment": ""}`, plus a `resolverNote` once a sweep has
refused to apply its comment. There is no category field — the kind is a bracket tag at the
front of the description. Collapse the whole wave into distinct questions, biggest first:

```bash
python3 <plugin>/scripts/review_queue.py list    --dir waves/<id>/discovery-out
python3 <plugin>/scripts/review_queue.py show    <group> --dir waves/<id>/discovery-out
python3 <plugin>/scripts/review_queue.py comment <group> "decision" --dir waves/<id>/discovery-out
python3 <plugin>/scripts/review_queue.py status  --dir waves/<id>/discovery-out
```

Items bucket by tag plus the *shape* of the description (identifiers, quoted literals and
numbers replaced by placeholders), so the same question asked about twelve different mappings
is one group and one decision. `comment` writes that decision into every member item across
every affected contract, preserving each file's key order and formatting.

| Tag | What discovery is asking |
|---|---|
| `[LOW CONFIDENCE]` | It found a source column but isn't sure it's the right one |
| `[UNMAPPED]` | It found no source for a target column |
| `[MULTIPLE CANDIDATES]` | Several plausible sources; pick one |
| `[COMPLEX TRANSFORM]` | Business logic it won't guess at |
| `[JOIN FAILED]` | A join path it couldn't validate against real data |
| `[ASSERTION FAILED]` | Its proposed mapping contradicts example records |
| `[LOAD STRATEGY]` | An incremental load with no change-detection method chosen |
| `[SPEC AMBIGUITY]` | An ambiguity `etl-extract` recorded from the original mapping — a question about the Informatica logic, not about the warehouse |

The prose version of each item is in the matching `discovery-report.txt` under
`ITEMS REQUIRING YOUR REVIEW` — read that to the user rather than raw JSON.

`[PROCEDURAL LOOP]` and `[LOOP REWRITE HINT]` are deliberately absent: discovery can emit the
first, but only for a spec whose `resolvedTransformation.advisory` is set, and that is set in
exactly one place — the stored-procedure spec assembler. An Informatica wave never produces
either. They belong to procedure-etl-conversion.

Present a set of near-identical items as one decision:

> Six contracts translate an Informatica `TO_DATE(port, 'MM/DD/YYYY')` where the source column
> is a string. Discovery flagged all six as low confidence. Proposal: `TRY_TO_DATE` with a null
> on unparseable values, rather than failing the load. Does that match how the current mappings
> behave?

Write the answer into every affected item's `comment` field, then sweep the whole group with
`--resolve`. Items the user didn't address keep an empty comment and stay queued.

## Resume and redo

| Situation | What happens |
|---|---|
| `waves/<id>/` exists | Resume: skip staging if `xml/` is populated (planned mode), extraction if `etl-specs/` has specs, discovery per spec if its `data-contract.json` exists, build per contract if its `build-report.txt` exists |
| User wants a clean redo | They delete the directory themselves — the skill never deletes |
| Corpus corrected mid-migration | Re-run collect with `--replace-all`, re-run lineage, re-cut the plan; group names and wave numbers may change and existing wave directories go stale |
| Contract already approved | The `--resolve` sweep passes it through unchanged; safe to include in every sweep |

## Co-migrating groups

When the plan lists groups as co-migrating (a dependency cycle), run them as one combined
group: stage all their mappings into a single wave directory and use one review queue. They
have to cut over together anyway, and splitting the queue would hide the coupling.
