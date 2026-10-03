# data_store

* `database.db` - live SQLite database (not committed to git).
* `backups/` - snapshots: weekly automatic, manual, and one before every migration or restore.
* `schema_reference.sql` - generated, read-only view of the current schema.

The schema is created and upgraded by `data_management/migrations` (automatically on app start).
Do not edit tables by hand.
