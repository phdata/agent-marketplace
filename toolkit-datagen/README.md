# toolkit-datagen

Synthetic data with the [phData Toolkit](https://toolkit.phdata.io/docs) CLI's data generation
tool, for requests phrased the way people actually phrase them — "50k fake customers and their
orders", "seed my dev database", "mock data for a star-schema demo".

**The agent writes the spec; the toolkit writes the rows.** That boundary is the whole point. A
data spec costs the same number of tokens whether it yields 100 rows or 10 million, relationships
across tables are declared rather than hand-wired, a `--seed` reproduces a run exactly, and the
spec is a file the team can keep, review, and re-run.

```
DDL / ORM models / a description        an existing database
   │                                       │  /toolkit-datagen:from-source
   │                                       ▼  toolkit datagen scan <ds> --filter ... --spec ...
   │                                    a spec to correct: relationships, ratios, value sets
   ▼                                       │
datagen/<name>-spec.yaml  ◄────────────────┘
   │   /toolkit-datagen:generate
   ▼
toolkit datagen validate --scale 0.01   →  toolkit datagen show -o report.html
   │   catch bad providers, broken references, affinity mistakes in seconds
   ▼
toolkit datagen file  <spec> --output <dir> --mode create --seed N     → CSV files
toolkit datagen jdbc  <ds>   <spec>        --mode create --seed N      → tables
```

## Skills

| Skill | Purpose |
|---|---|
| `/toolkit-datagen:generate` | Any synthetic/fake/test-data request: author or take a spec, validate it small, generate to files or a database |
| `/toolkit-datagen:from-source` | Clone the shape of an existing database with `datagen scan` — same tables, columns and types, none of the rows |

Two skills rather than one per command, because the plugin triggers on what the user is trying
to do. The command-by-command detail lives in [references/](references/) and in what
`toolkit datagen info` prints at runtime.

## When this plugin should stay out of the way

Both skills say so explicitly, so the model doesn't over-route:

- **About 20 rows or fewer for a single table**, inline in a unit test or doc example.
- **Columns that have to read like real prose** — support tickets, product descriptions — where
  text quality beats volume. Even then: a spec for the structured columns, hand-written prose
  for the one column that needs it.

## References

- [references/spec-cheatsheet.md](references/spec-cheatsheet.md) — spec/table/column fields,
  providers and samplers, foreign keys and row ratios, affinity, transforms and MVEL utility
  functions, static sources, volume and seeds. Written against the code, with the two places
  the published docs contradict it called out.
- [references/examples/](references/examples/) — seven specs, each verified against the CLI:
  `single-table`, `parent-child`, `fact-with-dimensions` (a star schema, and why a fact must
  not declare an FK to every dimension), `optional-relations`, `self-reference`,
  `static-dimension`, `derived-columns`.
- `toolkit admin extract datagen` writes eight larger example specs into `tools/datagen/` in the
  project (star schema, snowflake schema, IoT, hospital ERP, network).

## Prerequisites

- **toolkit-core** (installed automatically as a dependency): the toolkit binary and a project.
  Skills preflight with `toolkit_check.py`.
- **A toolkit project directory.** `datagen info` and `datagen validate` refuse to run outside
  one; `file` and `show` do not care.
- **A datasource** only for the `jdbc` output and for `datagen scan` — `/toolkit-core:connect`
  configures one. Writing CSV files needs no database at all.
- **No LLM and no agent license.** Unlike `toolkit agent *`, the datagen commands need neither.
  The single exception is `datagen scan --match=llm|hybrid`, which uses an LLM to match columns
  to providers; the default `Score` matching does not.

## Scope

Data generation only. The adjacent toolkit workflows have their own plugins: dataspec-driven
pipeline generation is `toolkit-pipeline` (whose `build` skill emits a
`mockdata/datagen-spec.yaml` that `/toolkit-datagen:generate` will happily tune and run), and
Informatica conversion is `informatica-assessment` and `informatica-etl-conversion`.
