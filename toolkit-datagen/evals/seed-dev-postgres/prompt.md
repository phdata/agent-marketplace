---
max_turns: 8
allowed_tools: [Read, Glob, Grep, Skill]
tags: [trigger, generate]
---

Seed my dev Postgres with test data for these three tables:

```sql
CREATE TABLE store (store_id INT PRIMARY KEY, name VARCHAR(60), region VARCHAR(20));
CREATE TABLE product (product_id INT PRIMARY KEY, name VARCHAR(80), list_price NUMERIC(10,2));
CREATE TABLE sale (sale_id BIGINT PRIMARY KEY, store_id INT REFERENCES store(store_id),
                   product_id INT REFERENCES product(product_id), qty INT, sold_at TIMESTAMP);
```
