# Data spec cheatsheet

Everything needed to write a correct `toolkit datagen` spec. Condensed from
`docs/toolkit/data-generation.adoc`, which `toolkit init` writes into the project and which
remains the full reference. Where this file and the docs disagree, this file follows the code —
the contradictions are called out at the bottom.

## Shape

```yaml
sourceType: snowflake        # the <source> in a jdbc:<source> URL: snowflake, sqlserver,
                             # postgresql, mysql, oracle, sqlite, databricks, ...
tables:
  - name: CUSTOMER           # no periods in name/database/schema
    database: SANDBOX        # optional, if the source has them
    schema: DEMO             # optional
    rows: 500                # fixed count — mutually exclusive with rowGenerator
    columns:
      - name: CUSTOMER_ID
        provider: NumberSequence
```

**Row counts when neither `rows` nor `rowGenerator` is given:** a table with no references to
other tables gets `rows: 10000`; a table that references another table gets
`rowGenerator: {range: 1}`. Both defaults are easy to inherit by accident — set them explicitly.

## Column spec

| Field | Notes |
|---|---|
| `name` | Required. |
| `provider` | A data provider name. `Address.city` form picks one field of a composite provider. |
| `config` | Provider config, plus a `sampler` block. Provider-specific — look it up, don't guess. |
| `transform` | An MVEL expression. May be combined with `provider`. |
| `foreignKey` | A reference to another column. **Must not** be combined with `provider` or `transform`. |
| `primaryKey` | Implies `unique: true` and `nullable: false` regardless of what the spec says. |
| `unique` | All generated values guaranteed distinct. |
| `nullable` | Default `false`. A non-nullable column never gets a null, whatever `density` says. |
| `density` | 0.0–1.0, the fraction of rows populated on a **nullable** column. Default `1.0`. |
| `dataType` `precision` `scale` `jdbcType` | Source data types. Needed for DDL generation (see below). |
| `identity` | An auto-increment DDL fact, normally only set by `datagen scan`. |

**Every column must define at least one of `provider`, `foreignKey`, or `transform`.** That is
the single most common validation failure.

A `jdbc` run against an existing table overwrites `dataType`, `nullable`, `precision`, `scale`,
and `jdbcType` in the spec from the real table metadata.

## Providers

Never guess a provider name — there are ~100 of them and a wrong name fails the run:

```bash
toolkit datagen info provider              # all of them, by category, with one-line descriptions
toolkit datagen info provider Currency     # category, description, config options, defaults
toolkit datagen info sampler
toolkit datagen info sink
```

`datagen info` must run **from the toolkit project directory**. For sample values and a
per-provider column-spec example, `docs/toolkit/generated/data-provider.adoc` in the project
(written by `toolkit init`) is richer than `info`.

The ones that come up constantly:

| Need | Provider | Config |
|---|---|---|
| Surrogate key | `NumberSequence` | `start`, `step`, `repeat` |
| Opaque key | `UUIDv4`, `UUIDv7` (time-ordered) | — |
| A fixed set of values | `Enum` | `values` as a list (sampler picks frequencies) or as a map of `value: probability` summing to 1.0 |
| Values from a file | `FileData` | `file` (relative to the project), `truncationMode` |
| Money | `Currency` | `min` (0), `max` (1000000), `scale` (2) |
| Any number | `RandomNumber` | `min`, `max`, `step`, `maxWholeDigits`, `maxDecimalDigits` |
| Dates / timestamps | `RandomDate`, `RandomTimestamp` | `min`, `max` |
| A date series | `DateSequence`, `TimestampSequence` | `start`, `step`, `unit` (days/weeks/months/years), `repeat` |
| Real values from a CSV | `StaticSource` | `staticSource` (see below) |
| People, contact, address | `FullName`, `FirstName`, `LastName`, `Email`, `Phone`, `StreetAddress`, `City`, `State`, `ZipCode` | — |

**Composite providers** generate one coordinated map per row, so several columns agree with each
other — `Address` (fields `street`, `city`, `zip`, `state`, `stateAbbr`), `User` (`firstName`,
`lastName`, `username`, `company`, `email`, `jobTitle`, ...), `Timestamp` (~28 fields including
`year`, `quarter`, `monthName`, `dayOfWeek`, `epochSeconds`). Two ways to use one:

```yaml
- name: CITY
  provider: Address.city          # field form
- name: STATE
  provider: Address               # or read the map in a transform
  transform:
    function: self.state
```

Without a field or transform the column gets the whole map (fine only where the target has a
complex type), and `toJson(self)` serializes it.

## Relationships

```yaml
- name: CUSTOMER_ID
  foreignKey: SANDBOX.DEMO.CUSTOMER.CUSTOMER_ID   # qualified exactly like the parent table
```

- An FK column carries **no** `provider`, `transform`, or `dataType` — it inherits `dataType`,
  `precision`, `scale`, and `jdbcType` from the column it references.
- The referenced table and column must exist in the same spec, or the run fails with
  "invalid foreign key reference".
- Mark the parent key `primaryKey: true`. `foreignKey` references **one** column: there is no
  composite foreign key, so a table whose natural key is several columns needs a single
  surrogate key to be referenced by. (Composite *primary* keys do work — two or more
  `primaryKey` columns make the combination unique, as `PRIMARY KEY (a, b)` would.)
- An **unqualified** `foreignKey` (a bare column name) means the same table — a self-reference,
  `manager_id -> employee_id`. Two consequences: the first row references itself, because no
  earlier row exists, and every later row draws from the **last 100 rows generated**, so
  parents stay numerically near their children. This 100-row window applies only to
  self-references; cross-table FKs come from the row group and are not windowed.

Ratios belong on the child, not in independent row counts. Only root tables get `rows`:

```yaml
- name: ORDERS
  rowGenerator:
    range: 1..5          # 1 to 5 orders per customer row
```

| `rowGenerator` field | Meaning |
|---|---|
| `range` | `2` (fixed), `1..9` (inclusive), `1..9 step 2` (1, 3, 5, 7 or 9). Rows **per input row**. |
| `max` | Hard ceiling on total rows for the table, whatever the range says. Default: max long. |
| `affinity` | `any` (default), `all`, or a qualified table name — see below. |
| `fill` | `true` reuses the previous row's value for a reference that wasn't generated. Default `false`. |
| `staticSource` | Path to a CSV; one row per CSV row. |
| `sampler` | Sampler settings for picking within the range. |

### A fact table with several dimensions

**Do not give a fact table a `foreignKey` to every dimension.** When a table references more
than one parent, the parent rows are **zipped by position**: on each pass the fact sees the 1st
store with the 1st product, the 2nd with the 2nd, and so on. Declaring an FK to each dimension
therefore correlates them perfectly. Measured, over 25 stores and 200 products: a 1,000-row fact
came out with 25 distinct `(store, product)` pairs, every one of them `store_id == product_id`,
and 175 products that never appeared at all. It joins, and it is useless for grouping by two
dimensions at once. Raising `range` only multiplies the duplicates, and equal-sized parents
change nothing.

The shape that works: **one `foreignKey`, to the dimension that defines the fact's grain**
("N sales per store"), and every other dimension key drawn from that dimension's key domain.

```yaml
- name: FACT_SALES
  rowGenerator:
    range: 40                 # 40 sales per store
  columns:
    - name: STORE_KEY         # the grain parent: a real foreign key
      foreignKey: SANDBOX.RETAIL.DIM_STORE.STORE_KEY
    - name: PRODUCT_KEY       # independent dimension: drawn from its key domain
      provider: RandomNumber
      config:
        min: 1
        max: 200              # == DIM_PRODUCT.rows
        maxDecimalDigits: 0
        sampler:
          type: uniform       # `normal` (the default) barely touches the end keys
```

The same spec then yields ~900 distinct `(store, product)` pairs per 1,000 rows. This stays
referentially correct only because the dimension's key is `NumberSequence` with `start: 1,
step: 1`, so its keys are exactly `1..rows` and the draw can never be an orphan — keep `max` and
the dimension's `rows` in step. Use `affinity: all` instead when you genuinely want every
reference non-null and are content with the correlation (it also caps the fact at the smallest
parent); `fill: true` does **not** rescue an exhausted parent — generation fails with "a
non-nullable column spec had a reference to a table and there was no row generated for that
table".

A dimension attribute that must agree with another column has to be a `transform` over it, never
a second provider: `Timestamp.monthName` next to a `DateSequence` column reports November for
the 1st of January, because it draws its own unrelated timestamp. See
`examples/fact-with-dimensions.yaml`.

**Affinity** decides what happens to a child row when one of the tables it references produced
no row on this pass (that table hit its `max`, drew `0` from a `0..N` range, or simply has fewer
rows than its siblings):

- `any` — generate the row if *any* reference was generated. Missing ones arrive as `null`, so
  **the FK column must be `nullable: true`** or generation fails. This is the default, and it is
  what models an optional relationship.
- `all` — generate only when *every* reference was generated.
- `<qualified.table>` — generate only when that one table produced a row.

## Transforms

```yaml
- name: LINE_TOTAL
  transform:
    function: price * quantity
    references:
      price: UNIT_PRICE                          # bare name = this table
      quantity: QUANTITY
      placed: SANDBOX.DEMO.ORDERS.ORDERED_AT     # qualified = another table
```

Every column the expression reads must be declared in `references`. Referencing another table's
column makes the two tables generate together as one group.

Variables available without declaring them: `self` (this column's provider value, or null when
there is no provider), `rowIndex`, `groupSize` (always 1 under a fixed `rows`), `groupIndex`.

Expressions are [MVEL](http://mvel.documentnode.com/): the usual arithmetic, comparison and
boolean operators, `?:` ternaries, `contains`, and method calls on values
(`self.toUpperCase()`). Utility functions:

| Group | Functions |
|---|---|
| Date math | `addDays`, `addMillis`, `daysBetween`, `hoursBetween`, `secondsBetween`, `millisBetween` |
| Random | `randomInt(from, until)`, `randomDouble()`, `randomDouble(from, until)`, `timestampBetween`, `dateBetween` |
| Build / parse | `now()`, `currentDate()`, `timestamp(s)`, `date(s)`, `toDate(ts)` |
| Extract | `year`, `month`, `day`, `hour`, `minute`, `second`, `dayOfWeek`, `dayName` |
| Set | `setYear`, `setMonth`, `setDay`, `setHour`, `setMinute`, `setSecond` |
| Other | `toJson(v)`, `coalesce(a, b, ...)` |

Three things that bite:

1. **Quote an expression containing `": "`.** A ternary like
   `shipped == null ? null : daysBetween(...)` is read by YAML as a nested mapping and fails to
   parse. Quote it.
2. **Don't put `density` on a transform column that another transform reads.** Density skips the
   expression, which leaves the column out of the row entirely, and the reader then fails with
   `Failed to find column reference`. Return `null` from the function instead:
   `randomDouble() <= 0.85 ? addDays(...) : null`.
3. **A parent cannot aggregate its children.** Children are generated after their parent, so a
   child can read its parent's columns and never the reverse. An order total lives on the line
   rows or in the query that reads them.

Iterate on an expression without a full run: `toolkit datagen mvel <spec>` opens a shell with
the spec and the utility functions loaded.

## Static sources

Real values for a dimension — region names, currency codes, a product catalog — joined to
randomly generated facts. CSV only.

```yaml
rowGenerator:
  staticSource: store-dimension.csv    # table level: one row per CSV row
columns:
  - name: STORE_CODE
    provider: StaticSource             # takes the CSV column of the same name, same case
  - name: DISTRICT
    provider: StaticSource
    config:
      staticSource: store-districts.csv   # column level wins over the table level
```

The path resolves from the directory the command runs in. Columns without
`provider: StaticSource` are still generated randomly, so a static dimension can carry generated
surrogate keys and dates.

## Samplers

A sampler shapes the distribution of values a provider draws within its range. Default `normal`
everywhere. Set it in a column's `config.sampler`, or in `rowGenerator.sampler` for how many
child rows get generated:

```yaml
config:
  sampler:
    type: gaussian
    seed: 0
    factor: 1.2      # gaussian only: higher = tighter clustering around the mode
    skew: 0.5        # gaussian only: positive biases toward max, negative toward min
```

| Type | Shape | Reach for it when |
|---|---|---|
| `normal` | Bell curve (gaussian with factor 1.0, skew 0.0) | The default. Values cluster mid-range. |
| `gaussian` | Bell curve you can tighten and skew | Skewed amounts — most orders small, a few large: `skew: -0.6`. |
| `uniform` | Flat | Every value equally likely: ids, categories, dice. |
| `positiveLinear` | Rises toward max | Recency-weighted dates, growing volumes. Slow over very large ranges. |
| `negativeLinear` | Falls toward max | Long-tail counts, decaying activity. Slow over very large ranges. |

A sampler needs enough values relative to its range to show its shape — 100 draws over 1,000
possible values looks like noise; 1,000 draws over 100 values looks like the curve.

## Volume, seeds, and output

- `--seed <n>` makes a run reproducible. Always pass it and report it.
- `--scale <f>` multiplies every table's `rows` — including the 10,000 default — and does **not**
  touch `rowGenerator.range`. Child tables scale anyway, because they generate per parent row.
  Prefer it over editing the spec: `--scale 0.01` for a quick check, `--scale 100` for volume.
- `--threads` (writer threads per table) and `--batch-size` (default 200,000) for large runs.
- `file` writes `<qualified.table>-<batch>.csv` per table, header included, nulls as empty
  fields, values quoted only when needed. `--format` accepts `CSV` only today.

**DDL generation** (`jdbc`, on by default, `--no-ddl` to disable) needs both: type info for the
spec's `sourceType`, and a `dataType` on every column except foreign keys. Without them, modes
`create` and `replace` fail.

Permissions: `scan` needs data-source scan rights plus `SELECT` on each matched table; `jdbc`
needs `SELECT` and `INSERT`, plus DDL rights unless `--no-ddl`, plus `ALTER` on SQL Server for
tables with `IDENTITY` columns.

## More examples

- `examples/` next to this file: one table, parent-child ratios, a star-schema fact with
  several dimensions, optional relationships, self-reference, static dimension, derived
  columns. All seven are verified against the CLI.
- `toolkit admin extract datagen` writes eight larger specs into `tools/datagen/` in the
  project — a star schema, a snowflake schema, an IoT stream, a hospital ERP, a network model.

## Where the docs are wrong

Both verified against the code; follow this file.

1. **Self-referencing foreign keys.** The Column Spec section says they are not allowed and must
   reference a different table. The Self Reference section documents them, and the generator
   implements them (`TableSpec.hasSelfReference`). They work.
2. **The `file` command's default mode.** The prose says `create`, "so existing data will never
   be overwritten". The CLI default is `REPLACE`, which **deletes the output directory**. Always
   pass `--mode` explicitly.
