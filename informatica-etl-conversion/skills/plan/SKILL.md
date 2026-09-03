---
name: plan
description: Run ds migration-plan to decompose the Informatica estate's lineage into ordered, scored migration waves, then walk the waves, groups, and held-out objects with the user and tune until the cut is right. Use when the user wants a migration plan, wave sequencing, or an inventory for an Informatica conversion, or asks to re-cut an existing plan.
---

# Plan: lineage → ordered migration waves

`ds migration-plan` clusters the lineage graph into groups, orders them into waves by
dependency, and scores each for complexity, priority, and risk. Its output is the plan of
record for the rest of the conversion — this plugin keeps no separate wave file. Free path:
no LLM, no agent license.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
"$TOOLKIT_CHECK" || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit-check` in the installed toolkit-core plugin directory.

Lineage must exist (`/informatica-etl-conversion:lineage`).

## Step 1 — cut a plan

```bash
toolkit ds migration-plan legacy_dw
```

For a small estate (under ~50 tables) the defaults — tuned for hundreds of tables — collapse
everything into one group. Start from the small-estate preset instead:

```bash
toolkit ds migration-plan legacy_dw \
    --hub-min-component-size 10 --hub-min-readers 4 --max-group-size 8
```

Writes `migration-plan/legacy_dw/plan.txt`, `migration-plan/legacy_dw/inventory.csv`, and a
JSON snapshot under `tools/ds/snapshots/migration-plan/`.

## Step 2 — review from the artifacts, not the console

Never parse the command's own output — it truncates long lists. Read the written files:

- **`plan.txt`** is the human rendering and what you walk through with the user. On a large
  estate, read it in pieces (the summary table first, then the groups being discussed) rather
  than pulling the whole file into context.
- **The JSON snapshot** is the machine-readable source for counting, filtering, and anything
  the wave and status skills need:

  ```bash
  SNAP=$(ls -1 tools/ds/snapshots/migration-plan/*_legacy_dw.json | sort | tail -1)
  jq -r '.summary' "$SNAP"
  jq -r '.waves[] | .number as $w | .groups[]
         | [$w, .name, ((.processes // [])|length), ((.tables // [])|length)] | @tsv' "$SNAP"
  ```

  Read the file directly rather than through `toolkit ds show` — that command currently fails
  to deserialize migration-plan snapshots containing Informatica processes (an
  `Unrecognized field "componentCount"` error, in every format). Guard against nulls with
  `(.processes // [])` and don't assume wave numbering starts at 0.

Walk the user through, in this order:

1. **Summary** — wave count, group count, table count, unparsed patterns.
2. **The wave table** — which groups land in which wave, with complexity/priority/risk bands.
   Wave order is a dependency order: a group migrates after everything it reads from.
3. **Contract edges** (`feeds X: A -> B` lines) — cross-group dataflows. Each is a cutover
   constraint: sequence it, or dual-run the two sides.
4. **Co-migrate groups** — groups in a dependency cycle that must cut over together.
5. **Held-out objects** — audit sinks, interfaces, placeholders, plumbing, dead and set-aside
   tables. Each disposition means a different decision; the glossary and what to do about each
   is in the plugin's `references/plan-tuning.md` (two levels up from this skill's directory).
   Interfaces especially: files, queues, and services with no warehouse equivalent, which
   someone has to rebuild as a stage, an unload, or a connector.

## Step 3 — tune and re-cut

Re-run with adjusted knobs until the user agrees the cut matches how their teams actually
own the estate. The knob table and when to reach for each is in `references/plan-tuning.md`;
the ones that come up most:

- `--max-group-size N` — split groups too big for one team to migrate at once.
- `--seed <table>` — treat a table as a final output when splitting, to break a group along a
  boundary the user cares about.
- `--exclude <table>` — leave a table out entirely (already-migrated, or truly retired).
- `--hub-min-readers` / `--hub-min-component-size` — control what gets pulled into the shared
  foundation group.

Each re-run overwrites `plan.txt`/`inventory.csv` and adds a snapshot. Warn the user before
re-cutting once wave execution has started: group names and wave numbers can change, which
strands existing `waves/` directories —`/informatica-etl-conversion:status` flags that drift.

Then start execution with `/informatica-etl-conversion:wave`, taking the lowest-numbered wave
first (its foundation group, if there is one, feeds everything else).
