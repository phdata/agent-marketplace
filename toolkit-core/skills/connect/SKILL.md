---
name: connect
description: Add or verify a JDBC connection and datasource in toolkit.conf for any supported type — Snowflake, SQL Server, Oracle, Postgres, MySQL, Hive, Databricks, Athena, SQLite — including JDBC driver installation for non-bundled types and verification via a scoped ds scan. Use when configuring data sources, fixing connection errors, or when toolkit-check reports no datasource.
---

# Connect a datasource

Goal: a named connection + datasource in the project's `toolkit.conf` that a scoped
`toolkit ds scan` can use successfully.

## Step 0 — preflight

Run `toolkit-check --level project`. On failure, surface the `hint:` line and stop — the user
needs `/toolkit-core:setup` first. On success it prints the `toolkit.conf` path; that's the file
to edit. `toolkit-check --list-datasources` shows what's already configured.

## Step 1 — gather

Ask for whatever isn't already known:

1. **Type**: snowflake, sqlserver, oracle, postgres, mysql, hive, databricks, athena, sqlite.
2. **Endpoint**: host/account, port, database (type-specific — the example file shows exactly
   what's needed).
3. **Auth method**: keypair/password/OAuth/IAM, depending on type.
4. **Scope**: which databases/schemas this work actually touches. Always set a
   `filters { patterns = [ "DB.SCHEMA.*" ] }` block — unscoped scans against shared warehouses
   are slow and noisy, and every downstream toolkit command reuses the filter.

## Step 2 — write the config

Read the matching example, `examples/<type>.conf`, in this skill's directory. It is a complete,
copy-pastable `connections` + `ds.datasources` pair with the exact JDBC URL template, required
`properties`, and the driver jar name for non-bundled types.

Merge it into the project's `toolkit.conf` (top-level `connections` and `ds` blocks), renaming
the placeholder datasource to whatever the user wants to call it. The shape:

```hocon
connections {
  my_source {
    url = "jdbc:..."                    // exact template in the example file
    username = ${MY_SOURCE_USER}        // env-var substitution — never inline secrets
    password = ${MY_SOURCE_PASSWORD}
    properties { ... }                  // driver-specific extras (role, warehouse, httpPath, ...)
  }
}

ds {
  datasources {
    my_source {
      connection = ${connections.my_source}
      filters { patterns = [ "MY_DB.MY_SCHEMA.*" ] }
    }
  }
}
```

**Secrets rule (non-negotiable): credentials go in as `${ENV_VAR}` references, never literal
values.** HOCON resolves them from the environment at runtime. Tell the user which variables to
export (the example file lists them) and remind them every future `toolkit` invocation needs
those variables set. If a value is missing, toolkit fails at config load with
`Could not resolve substitution to a value: ${VAR}` — that error means "export the variable",
nothing more.

## Step 3 — driver (non-bundled types only)

Snowflake and SQLite drivers ship with the toolkit. For every other type, the vendor JDBC jar
must be in the project's `lib/` directory (create it if needed). The example file's header names
the jar (e.g. `mssql-jdbc-13.2.0.jre11.jar`, `postgresql-42.7.x.jar`,
`athena-jdbc-3.x-with-dependencies.jar`). Download links are on each vendor's site; the user may
also already have one — check `ls lib/` first.

## Step 4 — verify

1. `toolkit-check --level datasource --datasource <name>` — config parses and the datasource is
   visible.
2. `toolkit ds scan <name>` — first real connection. The datasource-level `filters` block keeps
   this scoped; for an even narrower probe add `--filter "MY_DB.MY_SCHEMA.*"`.
3. On success, offer `toolkit ds show <name>:scan:latest --format html -o` to open the scanned
   metadata report.

Triage for failures:

| Symptom | Cause | Fix |
|---|---|---|
| `Could not resolve substitution to a value` | env var not exported | export it in this shell |
| `No suitable driver` / driver class not found | jar missing | put vendor jar in project `lib/` |
| auth/login error from the database | wrong credentials, role, or auth method | check env values, try the connection from another client |
| timeout / unknown host | network, VPN, firewall, wrong host | verify host/port, VPN posture |

`toolkit-check --level connect --datasource <name>` re-runs the connectivity probe any time.
