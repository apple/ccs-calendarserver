Steps for Modifying the Schema
==============================

1. Before changing current.sql, take note of the VERSION number in the schema
2. Copy current.sql into old/postgres-dialect/vNNN.sql (where NNN is the VERSION number prior to your changes)
3. Copy current-oracle-dialect.sql into old/oracle-dialect/vNNN.sql (where NNN is the VERSION number prior to your changes)
4. Make your changes to current.sql, bumping up the VERSION number
5. Use the sql_tables.py to generate the oracle version and save as current-oracle-dialect.sql
6. Write upgrade scripts within upgrades/postgres-dialect and upgrades/oracle-dialect
