---
name: collect
description: Copy in a supplied directory of exported Informatica PowerCenter XML and import it into the toolkit with ds collect etl, after analyzer reconnaissance that checks the export for completeness, plus an optional legacy source-database scan. Use when starting an Informatica conversion assessment, when the user has a directory of PowerCenter exports to analyze, or asks how to get Informatica mappings into the toolkit.
---

# Collect: PowerCenter XML → toolkit ETL store

First step of the assessment. Everything here runs on the free path — no LLM, no agent
license — and the legacy datasource is never connected to unless the user has real access and
wants a scan.

## Step 0 — preflight

```bash
TOOLKIT_CHECK="<absolute path from the toolkit-core SessionStart hook>"
"$TOOLKIT_CHECK" || exit
```

toolkit-core's scripts are not on PATH (plugin `bin/` directories aren't permitted, and
`CLAUDE_PLUGIN_ROOT` isn't set for Bash) — its SessionStart hook prints their absolute
paths into the session at startup. Use that path; if the hook didn't run, the script is
`scripts/toolkit-check` in the installed toolkit-core plugin directory.

On failure surface the `hint:` line and stop (`/toolkit-core:setup`). If it prints a `note:`
about the project directory, run every `toolkit` command below from that directory (or export
`TOOLKIT_PROJECT_HOME`) — the toolkit doesn't search parent directories.

Do **not** use `--level connect` here: the legacy datasource only needs to exist, and it is
often a no-access stub whose connection probe would fail by design.

## Step 1 — copy the corpus into the project

Ask for the directory of PowerCenter XML exports. This plugin assumes it arrives already
exported — producing it is the Informatica team's job, not a step here.

Copy it into the toolkit project as `informatica-xml/`, **preserving the directory structure
exactly as exported**:

```bash
cp -R <export-dir>/ informatica-xml/
```

Everything downstream then works from one known location: no path to remember between skills,
and the assessment stays reproducible even if the original export directory moves or is
reorganized. PowerCenter XML is text — a real exported mapping runs about 25 KB, so even a
5,000-mapping export is a couple of hundred megabytes.

Preserving the structure matters because the directory holding each file becomes the folder
segment of its plan process id (`informatica/<folder>/<mapping>`), which is what keeps
same-named mappings from different repository folders distinct:

```
informatica-xml/
  SALES_DW/      m_dim_customer.xml  m_fact_orders.xml  wkf_nightly.xml
  FINANCE_DW/    ...
```

A flat export works too — pass `--folder <name>` at Step 5 if the repository folder matters.
Once copied, don't rename directories inside `informatica-xml/`: process ids are derived from
those names, so renaming after an import can renumber a plan that waves are already running
against.

Take a quick look before going further: mapping files present, workflow XML (`wkf_*`) included,
and dependencies (sources, targets, mapplets) either inline or as sibling files. What a usable
corpus contains, and what to ask the exporter for when something's missing, is in the plugin's
`references/corpus-guide.md` (two levels up from this skill's directory). Step 3's analyzer scan
is the real completeness check.

## Step 2 — size the corpus and pick a route

Count the mappings — one `MAPPING` element each, and several can share a file:

```bash
<plugin>/scripts/infa-corpus count            # defaults to ./informatica-xml
```

This plugin bundles small scripts in its `scripts/` directory (two levels up from this
skill's directory) that own the fiddly parsing — the mapping-name regex and the plan
snapshot's jq paths. They are not on PATH; invoke them by path from the plugin
directory. Prefer them over retyping the patterns: the regex has three easy-to-miss
details, and getting any of them wrong fails silently.


**Around 20 mappings or fewer, ask the user which route they want** — don't assume. The full
assessment exists to make a large migration tractable; on a small one it can be more ceremony
than it's worth:

| | Full assessment | Direct conversion |
|---|---|---|
| Steps | this skill → `:lineage` → `:plan` → `:wave` per group | this skill → `:wave` once |
| You get | dependency-ordered waves, dead/audit/interface detection, complexity and risk scores, cutover constraints between groups | the converted pipelines, nothing about ordering |
| Also needs | a legacy datasource (real or stub), and the corpus imported | nothing but the corpus |
| Worth it when | mappings feed each other, the mappings are unfamiliar, or someone needs a migration schedule | the mappings are few and independent enough to hold in your head |

Frame it as the tradeoff, not as a size rule: twelve mappings chained four deep still benefit
from a plan, while thirty independent one-hop loads may not. If they're unsure, the assessment
is the safer default — it's free, needs no LLM, and the plan can simply be ignored.

Say which route was chosen before continuing.

- **Direct conversion** — do Step 3 (the analyzer scan is a free completeness check worth
  having either way) and stop there. Steps 4–6 exist to feed lineage and the plan; `agent
  etl-extract` reads the XML directly and never touches the collect store or a datasource.
  Then go straight to `/informatica-etl-conversion:wave` and tell it there's no plan.
- **Full assessment** — continue through every step below.

## Step 3 — analyzer reconnaissance (optional, recommended)

```bash
mkdir -p analyzer-out
toolkit analyzer scan --type=INFORMATICA informatica-xml --output analyzer-out 2>&1 \
    | tee analyzer-out/scan-console.log
```

The `tee` matters: the two most useful findings are printed to the console and stored nowhere.

Surface to the user:

- **Mappings referenced in the workflows without a mapping file** — the export is incomplete.
  Ask whoever produced it for those mappings before assessing; the plan can only be as complete
  as the corpus, and the ones missing shrink the waves silently.
- **Orphaned mapping files not referenced by workflows** — mappings nothing schedules. Often
  genuinely dead code worth excluding from the migration, sometimes a sign the workflow XML was
  left out of the export. Which one it is, is a question for the people who own the mappings.
- Estate metrics (workflows/sessions/mappings/transforms/sources/targets) and the complexity
  band, plus `analyzer-out/dependency.txt` — the workflow → session → mapping tree, which is
  the only orchestration record in the whole workflow (`etl-extract` does not capture workflow
  names).

Caveat worth stating once: the analyzer attaches sources and targets per *file*, so a file
holding several mappings over-reports each one's tables. Trust the plan (Step 5 onward) for
per-mapping table lists.

## Step 4 — datasource for the legacy database

The legacy source's SQL dialect must be one of **databricks, mssql, oracle, snowflake,
teradata** — those are the dialects the collect store can parse. Anything else: stop and
explain that these mappings can't be collected today.

- **With database access** — configure a real connection with `/toolkit-core:connect`.
- **Without access** (common) — add a stub whose URL is never dialed. Show the user this and
  let them adapt the database name:

  ```hocon
  connections {
      legacy_dw {
          # Never connected to — the jdbc scheme only sets the SQL dialect for parsing.
          url = "jdbc:oracle:thin:@localhost:1521/LEGACY"
      }
  }

  ds {
      datasources {
          legacy_dw {
              connection = ${connections.legacy_dw}
          }
      }
  }
  ```

  Schemes by dialect: oracle `jdbc:oracle:thin:@localhost:1521/DB`, mssql
  `jdbc:sqlserver://localhost:1433;databaseName=DB;encrypt=false`, teradata
  `jdbc:teradata://localhost/DATABASE=DB`, snowflake `jdbc:snowflake://localhost`,
  databricks `jdbc:databricks://localhost`.

## Step 5 — import the corpus

```bash
toolkit ds collect etl legacy_dw --type=INFORMATICA -i informatica-xml --replace-all
```

- Never connects to the datasource; its configured type only picks the SQL dialect.
- `--replace-all` on the first import and whenever a corrected or extended export is
  copied in.
  Warn the user: process ids are `informatica/<folder>/<mapping>`, so renaming corpus
  directories between imports changes those ids and can renumber a later plan.
- `--folder <name>` when the export is flat and the repository folder matters.
- Structural source → target edges come from the XML itself, so lineage survives even when
  embedded SQL fails to parse.

Report what it prints: package count, SQL fragments imported, and the endpoint-type breakdown
(Oracle/SQL Server/ODBC/…). One file can hold several mappings, so packages usually outnumber
files.

## Step 6 — legacy source-database scan (only with access)

Skip entirely for stub datasources. With real read access to the *legacy source*:

```bash
toolkit ds scan legacy_dw
toolkit ds profile legacy_dw    # optional: row counts, feeds the plan's sizing
```

The scan lets the planner tell live tables from ones no longer present, and profile row counts
show up as table sizes in the plan. Note for Teradata: no dedicated scanner, so it falls back
to generic JDBC metadata — it works, with lower fidelity. The **target warehouse is not
scanned** in this phase.

Command reference for everything above: `docs/toolkit/data-source.adoc` (`ds collect etl`,
`ds scan`, datasource config and filters) and `docs/toolkit/analyzer.adoc`, both written into
the project by `toolkit init`. Prefer them over guessing at syntax; use `--help` for exact
flags.

Then hand off to `/informatica-etl-conversion:lineage` (full assessment) or
`/informatica-etl-conversion:wave` (direct conversion).
