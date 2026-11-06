---
name: wave
description: Convert Informatica mappings into pipelines end to end — one migration-plan group, or a whole small corpus when there is no plan: agent etl-extract behind a dry-run cost gate, agent discovery against the target warehouse, a grouped review queue to approved contracts, then agent pipeline-build. Use when the user wants to convert or migrate mappings, a wave, or a plan group, or to resume a partially converted one.
---

# Wave: plan group → generated pipelines

Runs in one of two modes:

- **Planned** — one **plan group** per run; a wave is its groups in sequence. Groups within a
  wave are independent by construction, so one group is also the right size for a review queue:
  one schema or domain, one reviewer's competence. Groups the plan marks as co-migrating (a
  dependency cycle) run together as a single combined group.
- **Direct** — no plan; the whole corpus is converted in one run. Right when there are few
  mappings. Everything below is identical except Step 1 (where the mapping list comes from) and
  Step 2 (what gets staged); the dry-run gate, review queue, build, and report are unchanged.

The plan comes from the separate **informatica-assessment** plugin
(`/informatica-assessment:plan`), which writes `migration-plan/<ds>/plan.txt` and a snapshot.
This plugin reads those files if they are there and needs nothing else from it — direct mode is
a complete path on its own.

```bash
ls -d migration-plan/*/ 2>/dev/null
```

A plan present means planned mode, but **ask rather than assume** — a user may have a plan and
deliberately not be following it. No plan and a corpus past roughly 50 mappings: say once that
the assessment (dependency-ordered waves, dead-code and interface detection, complexity and risk
scores) is free, needs no LLM, and would otherwise be someone's manual sequencing problem later.
Then do what they ask.

Unlike the assessment plugin's skills, this one needs an LLM and an agent license.

## Step 0 — preflight and gates

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
python3 "$TOOLKIT_CHECK" || exit
python3 "$TOOLKIT_CHECK" --list-datasources
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit_check.py` in the installed toolkit-core plugin directory.

- **The corpus**: everything below reads PowerCenter XML from `informatica-xml/` in the toolkit
  project. If it isn't there, ask for the directory of exported XML and copy it in, **preserving
  the directory structure exactly as exported**:

  ```bash
  cp -R <export-dir>/ informatica-xml/
  ```

  Structure matters because the directory holding each file is the `<folder>` segment of a plan
  process id (`informatica/<folder>/<mapping>`), which is what keeps same-named mappings from
  different repository folders apart and what Step 1 uses to disambiguate a mapping found in
  several files. A flat export works too. Don't rename directories inside `informatica-xml/`
  after an import — in planned mode that changes process ids and can strand a running plan.
  `references/corpus-guide.md` in the informatica-assessment plugin covers what a usable export
  contains; producing the export is the Informatica team's job, not a step here.
- **Target datasource**: this is a *different* datasource from the legacy one used for
  assessment — the warehouse the pipelines will be built against. Establish which one it is
  before anything else, and confirm it with the user rather than inferring it from the
  datasource list. If none is configured, stop and hand off to `/toolkit-core:connect`; the
  legacy source datasource is not a substitute. Once named, probe it:
  `toolkit_check.py --level connect --datasource <target-ds>`.
- **Target platform**: `agent discovery` and `pipeline-build` support Snowflake and Databricks
  only. Another target: stop here and explain.
- **Target datasource filters**: discovery scans and profiles the warehouse live on *every*
  spec, so an unscoped datasource makes each run slow and lets unrelated tables compete as
  mapping candidates. Confirm the datasource has a `filters` block naming the landing
  database and schema:

  ```bash
  grep -A 4 'filters' toolkit.conf
  ```

  Missing or too broad, fix it before extracting — `/toolkit-core:connect` writes the block:
  `filters { patterns = [ "LANDING_DB.RAW.*" ] }`. This is also what keeps discovery honest
  about landed data: scoped to the landing schema, a spec whose sources never arrived fails
  for an obvious reason instead of matching something plausible elsewhere in the warehouse.
- **Extraction flags**: `--source-dialect` (the legacy database's dialect), `--target-platform`,
  and the output tooling are not recorded anywhere between runs. Confirm all three with the
  user each time rather than guessing from earlier logs — the dry-run log preserves the counts,
  not the flags.
- **Tooling environment**, if the answer to tooling is dbt or pyspark: `pipeline-build` (Step 7)
  executes the generated code, and resolves the tool on the PATH of the shell running
  `toolkit` — so the virtualenv has to be **activated in that shell**, not just installed.
  `dbt` for dbt, `databricks-connect` for pyspark; `sql` needs nothing extra. Check now, because
  the tooling is locked into every spec at Step 4 and changing it later means re-extracting:

  ```bash
  which dbt                  # dbt: also needs a profiles.yml matching --dbt-profile
  which databricks-connect   # pyspark: also needs its cluster/workspace config
  ```

  Missing, the build still "succeeds" — execution is marked `SKIPPED` and the judge retry loop
  never engages, leaving unexecuted code with a clean-looking report across the whole wave.
- **Process kinds** (planned mode): every process in the group must be `INFORMATICA_MAPPING`.
  SQL scripts, stored procedures, or SSIS packages in the group are outside this plugin — stop
  and say so. A group with *no* processes at all is table-only: real migration scope, but
  nothing this skill converts — say that and move to the next group rather than running an
  empty wave. In direct mode the corpus is Informatica XML by construction, so there's nothing
  to check.
- **LLM access**: with no `llmClient` block in `toolkit.conf`, the toolkit falls back to Amazon
  Bedrock via the phData auth flow (works out of the box for phData consultants). Others
  configure a provider with `/toolkit-core:llm`.
- **License**: `toolkit agent *` is license-gated; an authorization error means the user's token
  doesn't include agent access — a licensing conversation, not a config bug.
- **Plan freshness** (planned mode): if `migration-plan/<ds>/plan.txt` is newer than an
  existing wave directory, the plan was re-cut underneath it — surface that before doing
  anything else.
- **Resume**: if `waves/<id>/` already exists, resume by skipping stages whose artifacts are
  present. Never delete a wave directory; a clean redo is the user's own `rm`.

## Step 1 — pick the group, find its mappings

**Direct mode:** there is no group to pick and nothing to stage — the set is every mapping in
the corpus, and Step 3 runs `etl-extract` over `informatica-xml/` itself. Skip to Step 3. The
wave directory is `waves/all/`, holding outputs only. Count what's about to be converted so the
user sees the scope:

```bash
python3 <plugin>/scripts/infa_corpus.py count
```

**Planned mode:**

```bash
python3 <plugin>/scripts/infa_plan.py groups legacy_dw                    # wave, group, mappings, tables
python3 <plugin>/scripts/infa_plan.py processes legacy_dw <wave> <group>  # this group's mapping names
```

**Check the group's size before going further.** The review queue in Step 6 is per group, and
a group's mappings all land in it at once. Real migrations produce lopsided groups — a 121-group
Teradata plan had a median of a few mappings but one group with 83. Past roughly 20 mappings,
say so and offer the choice: re-cut the plan with a smaller `--max-group-size` (back to
`/informatica-assessment:plan`), or proceed knowing the review queue will be long and is
best worked in one sitting. Discovery cost scales the same way — one run per spec.

Then locate each mapping's XML by **content** — export filenames often don't match mapping
names, so a filename search misses most of them:

```bash
python3 <plugin>/scripts/infa_corpus.py find <mapping>
```

This plugin bundles small scripts in its `scripts/` directory (two levels up from this
skill's directory) that own the fiddly parsing — the mapping-name regex and the plan
snapshot's shape. They are not on PATH; invoke them by path from the plugin directory,
with whichever Python 3 is available (`python3`, or `python`/`py` on Windows). Prefer them
over retyping the patterns: the regex has three easy-to-miss details, and getting any of
them wrong fails silently.

When several files match one mapping, prefer the one whose parent directory equals the
`<folder>` segment of the process id. Unmatched mappings: show them to the user with the likely
causes (a directory renamed inside `informatica-xml/` since the import, or the mapping dropped
from a re-export) and resolve together. Edge cases are in the plugin's
`references/wave-runbook.md`.

## Step 2 — stage the group's XML

**Direct mode:** nothing to stage. Set `WAVE=waves/all` and `SRC=informatica-xml`, then go to
Step 3 — `waves/all/` holds outputs only.

**Planned mode:**

```bash
WAVE="waves/$(python3 <plugin>/scripts/infa_plan.py wave-id <wave> '<group>')"
SRC="$WAVE/xml"
mkdir -p "$SRC"
cp <matched files> "$SRC/"          # prefix with the folder name on filename collisions
```

`infa_plan.py wave-id` sanitizes the group name for use as a directory — plan groups are named
things like `(default)`, which becomes `_default_`.

Stage **copies into one directory and run `etl-extract` once over it**: the run makes a single
global LLM batch with expression deduplication across the whole group, where per-file runs
would multiply it. The copies also record exactly which files the wave converted.

One caveat to raise now: a staged file holding several mappings brings its other mappings along,
so extraction may emit specs belonging to other groups. That's handled in Step 4 by moving
them aside — never by editing the XML.

## Step 3 — dry-run cost gate

`$WAVE` and `$SRC` come from Step 2. The `mkdir` matters in direct mode, where Step 2 was
skipped and nothing has created the wave directory yet:

```bash
mkdir -p "$WAVE"

toolkit agent etl-extract "$SRC" \
    --etl-platform=informatica-pc \
    --source-dialect=<oracle|mssql|teradata|snowflake|databricks> \
    --target-platform=<SNOWFLAKE|DATABRICKS> \
    --dry-run 2>&1 | tee "$WAVE/etl-extract-dryrun.log"
```

Show the user the counts and task list verbatim, then get two decisions before spending
anything:

1. **The filtered targets.** Extraction skips staging-shaped (`STG_`, `STAGING_`, `S_`) and
   audit-shaped (`BATCH_*`, `*_AUDIT`, `*_LOAD_DETAIL`, anything containing `audit`) targets by
   default, because they're by-products of the ETL rather than its business output — and on the
   target platform the generated pipelines build their own staging. Confirm that's right for
   this group, or re-run with `--include-staging` / `--include-audit`.
2. **The cost.** The projected LLM calls are right there in the dry-run line. Get an explicit
   go-ahead.

## Step 4 — extract the specs

```bash
toolkit agent etl-extract "$SRC" \
    --etl-platform=informatica-pc \
    --source-dialect=<d> --target-platform=<SNOWFLAKE|DATABRICKS> \
    [--tool=SQL|DBT|PYSPARK] [--dbt-profile <name>] \
    --output "$WAVE/etl-specs" 2>&1 | tee "$WAVE/etl-extract.log"
```

`--tool=dbt` requires `--dbt-profile`; ask before running, and make sure the tooling
environment checked at Step 0 is still the active one — the choice made here is written into
every spec in the wave and carried through to the contracts. The `tee` is load-bearing — this
command writes no manifest or report, and files it couldn't parse are warned about on the
console and nowhere else. Read the log for those warnings and surface each skipped file.

Then, before any discovery runs:

- **Move out-of-group specs aside** (planned mode only — in direct mode every spec is in
  scope). Spec files are `<mapping>__<target>.discovery.yaml`; any whose mapping isn't in the
  group's process list goes to `waves/<id>/etl-specs/_out-of-scope/`. Keep them — they're free
  to re-extract when that mapping's own group runs, thanks to the expression cache.
- **Review the specs with the user**, one per target table: the inferred `loadStrategy` and
  `materialization` (derived deterministically from Update Strategy, Router, Joiner, Filter and
  watermark evidence — no LLM guessing), any low-confidence column derivations, and the
  `Ambiguities / human review` section. Each spec keeps the original Informatica expression
  next to its translation, which is what to look at when a derivation seems wrong.
- Note once: workflow orchestration and scheduling are **not** in these specs — `etl-extract`
  works at mapping level. `analyzer-out/dependency.txt` is the record for rebuilding schedules,
  as a separate manual exercise.

## Step 5 — discovery

Discovery resolves each spec against real data in the target warehouse and emits a data
contract. One output subdirectory per spec — it always writes `<output-dir>/data-contract.json`,
so a shared directory clobbers:

```bash
for f in "$WAVE"/etl-specs/*.discovery.yaml; do
  name=$(basename "$f" .discovery.yaml)
  [ -f "$WAVE/discovery-out/$name/data-contract.json" ] && continue   # resume
  toolkit agent discovery <target-ds> "$f" --output "$WAVE/discovery-out/$name"
done
```

Each run scans and profiles live, bounded by the datasource `filters` confirmed at Step 0.

A spec whose sources aren't landed in the target yet won't fail loudly — it comes back with
failed assertions and low-confidence mappings that read like problems with the mapping. If a
contract looks inexplicably bad, check whether its sources actually arrived before spending
review time on it.

## Step 6 — the grouped review queue

This is where the group pays off: the same Informatica idiom appears across many mappings, so
one decision resolves many items at once.

1. **Collapse the group's items into one list of distinct questions.** An item is
   `{description, comment, resolverNote?}` — its kind is a `[TAG]` prefix on the description:

   ```bash
   python3 <plugin>/scripts/review_queue.py list --dir "$WAVE/discovery-out"
   ```

   Bundled in this plugin's `scripts/` directory (two levels up from this skill's directory);
   invoke it by path, since plugin scripts aren't on PATH. Python 3 standard library only, so
   it behaves the same on Windows (`python`/`py`), macOS, and Linux. It buckets items by tag
   plus the shape of the description — identifiers, literals and numbers replaced — so the
   same question about different mappings lands in one group, biggest group first.

   Tell the user the ratio: a wave of 40 contracts routinely collapses to a handful of real
   decisions, and that ratio is what makes a long queue workable in one sitting.

   Also read each `discovery-report.txt` for the mappings the user cares most about — the
   `ITEMS REQUIRING YOUR REVIEW` section states each item in prose, and CRITICAL warnings
   don't appear in the queue at all.

2. **Work the list in order, biggest group first.** `review_queue.py show <n>` prints every
   item in a group with its contract and full description — always read that before deciding,
   to confirm the group is one question and not two that share a shape. Then put one proposal
   to the user ("every `TO_DATE(..., 'MM/DD/YYYY')` becomes `TRY_TO_DATE`, null on failure —
   agreed?"), and capture the answer in their own words. What each tag is asking is tabulated
   in the runbook.

3. **Write the decision across the whole group at once:**

   ```bash
   python3 <plugin>/scripts/review_queue.py comment <n> "<the user's decision>" \
       --dir "$WAVE/discovery-out"
   ```

   It writes the `comment` field of every member item in every affected contract, preserving
   key order and formatting (`--dry-run` previews, `--overwrite` replaces existing comments).
   Leave groups the user had no opinion on uncommented — they stay queued rather than guessed
   at. Consistency is not cosmetic here: the resolver applies items that ask for the same
   change, but leaves an item open when its amendments contradict how an earlier item changed
   the same mapping or join.

4. **Sweep the whole group**:

   ```bash
   for f in "$WAVE"/etl-specs/*.discovery.yaml; do
     name=$(basename "$f" .discovery.yaml)
     contract="$WAVE/discovery-out/$name/data-contract.json"
     [ -f "$contract" ] || continue          # spec whose discovery hasn't run
     toolkit agent discovery <target-ds> "$f" --resolve "$contract"
   done
   ```

   The positional datasource and spec are required by the CLI but ignored on the resolve path.
   The resolver applies each comment, drops resolved items, and sets `approvedByHuman: true`
   when none remain. Contracts without comments pass through unchanged, so sweeping them all is
   safe.

5. **Re-queue and repeat** until every contract is approved
   (`review_queue.py status --dir "$WAVE/discovery-out"` gives the per-contract view). Each
   commented item is all-or-nothing: one the resolver refused comes back flagged
   `NOT APPLIED` with its reason, and the next comment has to address that reason rather than
   restate the decision. Target tooling, platform, and columns are structurally locked — a
   comment can't change the target schema, so a genuinely wrong target means going back to
   Step 4, not commenting harder.

## Step 7 — build

```bash
for d in "$WAVE"/discovery-out/*/; do
  name=$(basename "$d")
  contract="$d/data-contract.json"
  [ -f "$WAVE/pipeline-out/$name/build-report.txt" ] && continue      # already built
  python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("approvedByHuman") else 1)' \
      "$contract" || continue                                         # unapproved
  toolkit agent pipeline-build <target-ds> \
      --contract "$contract" --output "$WAVE/pipeline-out/$name"
done
```

The approval guard is the loop's, not a matter of remembering: anything it skips goes back
through Step 6. `--force-unresolved` overrides it only with the user's explicit OK, and
produces code embedding unreviewed guesses. Read every `build-report.txt` — judge failures and exhausted
retries go into the wave report, not glossed over. For dbt and pyspark waves, check each
report's `EXECUTION` section as well: `SKIPPED` means the tool wasn't on PATH and nothing was
executed, so fix the environment and rebuild rather than recording the wave as converted.

For reading the generated output, the `--max-retries` / `--llm-effort` knobs, and the optional
apply / seed / test follow-ups, use `/toolkit-pipeline:build` — the mechanics are identical.

## Step 8 — wave report

Write `waves/<id>/wave-report.md` for the user: mappings found and staged, specs emitted,
contracts approved, pipelines built; staging and audit targets skipped; files that failed to
parse; specs moved to `_out-of-scope/`; judge failures;
and, in planned mode, the group's outbound contract edges restated as cutover constraints
("this group feeds MART_FIN.SALES_DETAIL — sequence or dual-run that boundary"). Finish with
the next group to run — or, in direct mode, note that deployment order across the converted
mappings was never analyzed, so someone has to sequence the cutover by hand.

Command reference for `etl-extract`, `discovery` and `pipeline-build`: `docs/toolkit/agent.adoc`,
written into the project by `toolkit init`.

Then `/informatica-etl-conversion:status` for the whole-migration picture.
