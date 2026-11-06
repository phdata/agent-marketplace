---
max_turns: 8
allowed_tools: [Read, Glob, Grep, Skill]
tags: [trigger, generate]
---

I already have this datagen spec saved as `datagen/orders-spec.yaml`. Run it into Snowflake.

```yaml
sourceType: snowflake
tables:
  - name: CUSTOMER
    database: SANDBOX
    schema: DEMO
    rows: 1000
    columns:
      - name: CUSTOMER_ID
        primaryKey: true
        provider: UUIDv7
        dataType: VARCHAR
        precision: 36
      - name: FULL_NAME
        provider: FullName
        dataType: VARCHAR
        precision: 100
  - name: ORDERS
    database: SANDBOX
    schema: DEMO
    rowGenerator:
      range: 1..5
    columns:
      - name: ORDER_ID
        primaryKey: true
        provider: UUIDv7
        dataType: VARCHAR
        precision: 36
      - name: CUSTOMER_ID
        foreignKey: SANDBOX.DEMO.CUSTOMER.CUSTOMER_ID
      - name: ORDERED_AT
        provider: RandomTimestamp
        dataType: TIMESTAMP_NTZ
```
