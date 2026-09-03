# Working with a PowerCenter export corpus

This plugin starts from a directory of PowerCenter XML that someone has already exported —
typically the Informatica team, via Repository Manager or `pmrep objectexport`. Producing the
export is out of scope here; assessing what arrived is the job.

## What a usable corpus contains

- **Mapping XML** — the conversion unit. One `MAPPING` element per mapping; several may share
  a file.
- **Their dependencies** — sources, targets, mapplets, and reusable transformations, either
  inline in each mapping file or as sibling files from the same export. Without them,
  extraction sees ports whose definitions are missing, and column derivations come out
  incomplete.
- **Workflow XML** (`wkf_*`) — not converted, but it carries the workflow → session → mapping
  tree that the analyzer reports and that is the only orchestration record available later.
  Also how sessions' `Target Table Name` overrides are discovered.

## Layout, and why it matters

```
informatica-xml/
  SALES_DW/
    m_dim_customer.xml
    m_fact_orders.xml
    wkf_nightly_sales.xml
  FINANCE_DW/
    m_dim_account.xml
```

The export is copied into the toolkit project as `informatica-xml/` at collect time, structure
intact, and every later step works from there — so there is no corpus path to carry between
skills, and the assessment survives the original export directory moving or being reorganized.

Structure is preserved because the directory holding each file becomes the folder segment of
its plan process id (`informatica/<folder>/<mapping>`). One directory per repository folder is
therefore the layout to keep — it is what makes two folders' same-named mappings distinct, and
what `/informatica-etl-conversion:wave` uses to disambiguate a mapping matched in several files.

A flat directory still works. If the export is flat and the repository folder matters, pass it
explicitly at collect time with `--folder <name>`.

**Do not rename or reorganize directories inside `informatica-xml/` after an import.** Process
ids are derived from those names, so a rename changes every id and can renumber a plan that
waves are already being executed against. A corrected or extended export is copied over the
corpus and re-imported with `--replace-all` instead.

## Checking what arrived

The analyzer scan in `/informatica-etl-conversion:collect` is the completeness check. Two of
its console findings decide whether the corpus is worth planning from:

- **Mappings referenced in the workflows without a mapping file** — the export is incomplete.
  Go back to whoever produced it and ask for those mappings before assessing; the plan can only
  be as complete as the corpus, and missing mappings silently shrink the waves.
- **Orphaned mapping files not referenced by workflows** — mappings nothing schedules. Often
  genuinely dead code worth excluding from the migration, sometimes a sign the workflow XML was
  left out of the export. Which one it is, is a question for the estate's owners.

Also worth confirming with whoever exported: whether it covers the **whole** scope or one
folder of a larger repository, and whether it came from the production repository or a
development one that has drifted.

## Format notes

- `DOCTYPE` declarations pointing at `powrmart.dtd` are normal and handled (external entity
  resolution is disabled; the DTD is never fetched).
- Both `NAME="x"` and `NAME ="x"` attribute spacing appear in real exports; the toolkit and
  this plugin's file matching handle both.
- Case varies (`.xml` and `.XML`); scanning is case-insensitive.
- A file that fails to parse is warned about and skipped, not fatal — the warning appears only
  on the console, which is why the skills tee their command output.
- Non-XML files in the directory are ignored, so an export shipped alongside logs or READMEs
  needs no cleaning.

## Not covered here

SSIS `.dtsx` packages and SQL Server stored procedures can also be assessed and converted by
the toolkit CLI, but this plugin's skills are written for Informatica PowerCenter only. See
`toolkit ds collect etl --help` and `toolkit agent etl-extract --help` for those paths.
