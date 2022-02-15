# Changelog

Tracking changes in peewee between versions.  For a complete view of all the
releases, visit GitHub:

https://github.com/coleifer/peewee/releases

## master

[View commits](https://github.com/coleifer/peewee/compare/3.14.9...master)

## 3.14.9

* Allow calling `table_exists()` with a model-class, refs
* Improve `is_connection_usable()` method of `MySQLDatabase` class.
* Better support for VIEWs with `playhouse.dataset.DataSet` and sqlite-web.
* Support INSERT / ON CONFLICT in `playhosue.kv` for newer Sqlite.
* Add `ArrayField.contained_by()` method, a corollary to `contains()` and
  the `contains_any()` methods.
* Support cyclical foreign-key relationships in reflection/introspection, and
  also for sqlite-web.
* Add magic methods for FTS5 field to optimize, rebuild and integrity check the
  full-text index.
* Add fallbacks in `setup.py` in the event distutils is not available.

[View commits](https://github.com/coleifer/peewee/compare/3.14.8...3.14.9)

## 3.14.8

Back-out all changes to automatically use RETURNING for `SqliteExtDatabase`,
`CSqliteExtDatabase` and `APSWDatabase`. The issue I found is that when a
RETURNING cursor is not fully-consumed, any parent SAVEPOINT (and possibly
transaction) would not be able to be released. Since this is a
backwards-incompatible change, I am going to back it out for now.

Returning clause can still be specified for Sqlite, however it just needs to be
done so manually rather than having it applied automatically.

[View commits](https://github.com/coleifer/peewee/compare/3.14.7...3.14.8)

## 3.14.7

Fix bug in APSW extension with Sqlite 3.35 and newer, due to handling of last
insert rowid with RETURNING. Refs #2479.

[View commits](https://github.com/coleifer/peewee/compare/3.14.6...3.14.7)

## 3.14.6

Fix pesky bug in new `last_insert_id()` on the `SqliteExtDatabase`.

[View commits](https://github.com/coleifer/peewee/compare/3.14.5...3.14.6)

## 3.14.5

This release contains a number of bug-fixes and small improvements.

* Only raise `DoesNotExist` when `lazy_load` is enabled on ForeignKeyField,
  fixes issue #2377.
* Add missing convenience method `ModelSelect.get_or_none()`
* Allow `ForeignKeyField` to specify a custom `BackrefAccessorClass`,
  references issue #2391.
* Ensure foreign-key-specific conversions are applied on INSERT and UPDATE,
  fixes #2408.
* Add handling of MySQL error 4031 (inactivity timeout) to the `ReconnectMixin`
  helper class. Fixes #2419.
* Support specification of conflict target for ON CONFLICT/DO NOTHING.
* Add `encoding` parameter to the DataSet `freeze()` and `thaw()` methods,
  fixes #2425.
* Fix bug which prevented `DeferredForeignKey` from being used as a model's
  primary key, fixes #2427.
* Ensure foreign key's related object cache is cleared when the foreign-key is
  set to `None`. Fixes #2428.
* Allow specification of `(schema, table)` to be used with CREATE TABLE AS...,
  fixes #2423.
* Allow reusing open connections with DataSet, refs #2441.
* Add `highlight()` and `snippet()` helpers to Sqlite `SearchField`, for use
  with full-text search extension.
* Preserve user-provided aliases in column names. Fixes #2453.
* Add support for Sqlite 3.37 strict tables.
* Ensure database is inherited when using `ThreadSafeDatabaseMetadata`, and
  also adds an implementation in `playhouse.shortcuts` along with basic unit
  tests.
* Better handling of Model's dirty fields when saving, fixes #2466.
* Add basic support for MariaDB connector driver in `playhouse.mysql_ext`, refs
  issue #2471.
* Begin a basic implementation for a psycopg3-compatible pg database, refs
  issue #2473.
* Add provisional support for RETURNING when using the appropriate versions of
  Sqlite or MariaDB.

[View commits](https://github.com/coleifer/peewee/compare/3.14.4...3.14.5)

## 3.14.4

This release contains an important fix for a regression introduced by commit
ebe3ad5, which affected the way model instances are converted to parameters for
use in expressions within a query. The bug could manifest when code uses model
instances as parameters in expressions against fields that are not
foreign-keys.

The issue is described in #2376.

[View commits](https://github.com/coleifer/peewee/compare/3.14.3...3.14.4)

## 3.14.3

This release contains a single fix for ensuring NULL values are inserted when
issuing a bulk-insert of heterogeneous dictionaries which may be missing
explicit NULL values. Fixes issue #2638.

[View commits](https://github.com/coleifer/peewee/compare/3.14.2...3.14.3)

## 3.14.2

This is a small release mainly to get some fixes out.

* Support for named `Check` and foreign-key constraints.
* Better foreign-key introspection for CockroachDB (and Postgres).
* Register UUID adapter for Postgres.
* Add `fn.array_agg()` to blacklist for automatic value coercion.

[View commits](https://github.com/coleifer/peewee/compare/3.14.1...3.14.2)

## 3.14.1

This release contains primarily bugfixes.

* Properly delegate to a foreign-key field's `db_value()` function when
  converting model instances. #2304.
* Strip quote marks and parentheses from column names returned by sqlite
  cursor when a function-call is projected without an alias. #2305.
* Fix `DataSet.create_index()` method, #2319.
* Fix column-to-model mapping in model-select from subquery with joins, #2320.
* Improvements to foreign-key lazy-loading thanks @conqp, #2328.
* Preserve and handle `CHECK()` constraints in Sqlite migrator, #2343.
* Add `stddev` aggregate function to collection of sqlite user-defined funcs.

[View commits](https://github.com/coleifer/peewee/compare/3.14.0...3.14.1)

## 3.14.0

This release has been a bit overdue and there are numerous small improvements
and bug-fixes. The bugfix that prompted this release is #2293, which is a
regression in the Django-inspired `.filter()` APIs that could cause some
filter expressions to be discarded from the generated SQL. Many thanks for the
excellent bug report, Jakub.

* Add an experimental helper, `shortcuts.resolve_multimodel_query()`, for
  resolving multiple models used in a compound select query.
* Add a `lateral()` method to select query for use with lateral joins, refs
  issue #2205.
* Added support for nested transactions (savepoints) in cockroach-db (requires
  20.1 or newer).
* Automatically escape wildcards passed to string-matching methods, refs #2224.
* Allow index-type to be specified on MySQL, refs #2242.
* Added a new API, `converter()` to be used for specifying a function to use to
  convert a row-value pulled off the cursor, refs #2248.
* Add `set()` and `clear()` method to the bitfield flag descriptor, refs #2257.
* Add support for `range` types with `IN` and other expressions.
* Support CTEs bound to compound select queries, refs #2289.

### Bug-fixes

* Fix to return related object id when accessing via the object-id descriptor,
  when the related object is not populated, refs #2162.
* Fix to ensure we do not insert a NULL value for a primary key.
* Fix to conditionally set the field/column on an added column in a migration,
  refs #2171.
* Apply field conversion logic to model-class values. Relocates the logic from
  issue #2131 and fixes #2185.
* Clone node before modifying it to be flat in an enclosed nodelist expr, fixes
  issue #2200.
* Fix an invalid item assignment in nodelist, refs #2220.
* Fix an incorrect truthiness check used with `save()` and `only=`, refs #2269.
* Fix regression in `filter()` where using both `*args` and `**kwargs` caused
  the expressions passed as `args` to be discarded. See #2293.

[View commits](https://github.com/coleifer/peewee/compare/3.13.3...3.14.0)

## 3.13.3

* Allow arbitrary keyword arguments to be passed to `DataSet` constructor,
  which are then passed to the instrospector.
* Allow scalar subqueries to be compared using numeric operands.
* Fix `bulk_create()` when model being inserted uses FK identifiers.
* Fix `bulk_update()` so that PK values are properly coerced to the right
  data-type (e.g. UUIDs to strings for Sqlite).
* Allow array indices to be used as dict keys, e.g. for the purposes of
  updating a single array index value.

[View commits](https://github.com/coleifer/peewee/compare/3.13.2...3.13.3)

## 3.13.2

* Allow aggregate functions to support an `ORDER BY` clause, via the addition
  of an `order_by()` method to the function (`fn`) instance. Refs #2094.
* Fix `prefetch()` bug, where related "backref" instances were marked as dirty,
  even though they had no changes. Fixes #2091.
* Support `LIMIT 0`. Previously a limit of 0 would be translated into
  effectively an unlimited query on MySQL. References #2084.
* Support indexing into arrays using expressions with Postgres array fields.
  References #2085.
* Ensure postgres introspection methods return the columns for multi-column
  indexes in the correct order. Fixes #2104.
* Add support for arrays of UUIDs to postgres introspection.
* Fix introspection of columns w/capitalized table names in postgres (#2110).
* Fix to ensure correct exception is raised in SqliteQueueDatabase when
  iterating over cursor/result-set.
* Fix bug comparing subquery against a scalar value. Fixes #2118.
* Fix issue resolving composite primary-keys that include foreign-keys when
  building the model-graph. Fixes #2115.
* Allow model-classes to be passed as arguments, e.g., to a table function.
  Refs #2131.
* Ensure postgres `JSONField.concat()` accepts expressions as arguments.

[View commits](https://github.com/coleifer/peewee/compare/3.13.1...3.13.2)

## 3.13.1

Fix a regression when specifying keyword arguments to the `atomic()` or
`transaction()` helper methods. Note: this only occurs if you were using Sqlite
and were explicitly setting the `lock_type=` parameter.

[View commits](https://github.com/coleifer/peewee/compare/3.13.0...3.13.1)

## 3.13.0

### CockroachDB support added

This will be a notable release as it adds support for
[CockroachDB](https://cockroachlabs.com/), a distributed, horizontally-scalable
SQL database.

* [CockroachDB usage overview](http://docs.peewee-orm.com/en/latest/peewee/database.html#using-crdb)
* [CockroachDB API documentation](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#crdb)

### Other features and fixes

* Allow `FOR UPDATE` clause to specify one or more tables (`FOR UPDATE OF...`).
* Support for Postgres `LATERAL` join.
* Properly wrap exceptions raised during explicit commit/rollback in the
  appropriate peewee-specific exception class.
* Capture original exception object and expose it as `exc.orig` on the
  wrapped exception.
* Properly introspect `SMALLINT` columns in Postgres schema reflection.
* More flexible handling of passing database-specific arguments to `atomic()`
  and `transaction()` context-manager/decorator.
* Fix non-deterministic join ordering issue when using the `filter()` API
  across several tables (#2063).

[View commits](https://github.com/coleifer/peewee/compare/3.12.0...3.13.0)

## 3.12.0

* Bulk insert (`insert_many()` and `insert_from()`) will now return the row
  count instead of the last insert ID. If you are using Postgres, peewee will
  continue to return a cursor that provides an iterator over the newly-inserted
  primary-key values by default. This behavior is being retained by default for
  compatibility. Postgres users can simply specify an empty `returning()` call
  to disable the cursor and retrieve the rowcount instead.
* Migration extension now supports altering a column's data-type, via the new
  `alter_column_type()` method.
* Added `Database.is_connection_usabe()` method, which attempts to look at the
  status of the underlying DB-API connection to determine whether the
  connection is usable.
* Common table expressions include a `materialized` parameter, which can be
  used to control Postgres' optimization fencing around CTEs.
* Added `BloomFilter.from_buffer()` method for populating a bloom-filter from
  the output of a previous call to the `to_buffer()` method.
* Fixed APSW extension's `commit()` and `rollback()` methods to no-op if the
  database is in auto-commit mode.
* Added `generate_always=` option to the `IdentityField` (defaults to False).

[View commits](https://github.com/coleifer/peewee/compare/3.11.2...3.12.0)

## 3.11.2

* Implement `hash` interface for `Alias` instances, allowing them to be used in
  multi-source queries.

[View commits](https://github.com/coleifer/peewee/compare/3.11.1...3.11.2)

## 3.11.1

* Fix bug in new `_pk` / `get_id()` implementation for models that explicitly
  have disabled a primary-key.

[View commits](https://github.com/coleifer/peewee/compare/3.11.0...3.11.1)

## 3.11.0

* Fixes #1991. This particular issue involves joining 3 models together in a
  chain, where the outer two models are empty. Previously peewee would make the
  middle model an empty model instance (since a link might be needed from the
  source model to the outermost model). But since both were empty, it is more
  correct to make the intervening model a NULL value on the foreign-key field
  rather than an empty instance.
* An unrelated fix came out of the work on #1991 where hashing a model whose
  primary-key happened to be a foreign-key could trigger the FK resolution
  query. This patch fixes the `Model._pk` and `get_id()` interfaces so they
  no longer introduce the possibility of accidentally resolving the FK.
* Allow `Field.contains()`, `startswith()` and `endswith()` to compare against
  another column-like object or expression.
* Workaround for MySQL prior to 8 and MariaDB handling of union queries inside
  of parenthesized expressions (like IN).
* Be more permissive in letting invalid values be stored in a field whose type
  is INTEGER or REAL, since Sqlite allows this.
* `TimestampField` resolution cleanup. Now values 0 *and* 1 will resolve to a
  timestamp resolution of 1 second. Values 2-6 specify the number of decimal
  places (hundredths to microsecond), or alternatively the resolution can still
  be provided as a power of 10, e.g. 10, 1000 (millisecond), 1e6 (microsecond).
* When self-referential foreign-keys are inherited, the foreign-key on the
  subclass will also be self-referential (rather than pointing to the parent
  model).
* Add TSV import/export option to the `dataset` extension.
* Add item interface to the `dataset.Table` class for doing primary-key lookup,
  assignment, or deletion.
* Extend the mysql `ReconnectMixin` helper to work with mysql-connector.
* Fix mapping of double-precision float in postgres schema reflection.
  Previously it mapped to single-precision, now it correctly uses a double.
* Fix issue where `PostgresqlExtDatabase` and `MySQLConnectorDatabase` did not
  respect the `autoconnect` setting.

[View commits](https://github.com/coleifer/peewee/compare/3.10.0...3.11.0)

## 3.10.0

* Add a helper to `playhouse.mysql_ext` for creating `Match` full-text search
  expressions.
* Added date-part properties to `TimestampField` for accessing the year, month,
  day, etc., within a SQL expression.
* Added `to_timestamp()` helper for `DateField` and `DateTimeField` that
  produces an expression returning a unix timestamp.
* Add `autoconnect` parameter to `Database` classes. This parameter defaults to
  `True` and is compatible with previous versions of Peewee, in which executing
  a query on a closed database would open a connection automatically. To make
  it easier to catch inconsistent use of the database connection, this behavior
  can now be disabled by specifying `autoconnect=False`, making an explicit
  call to `Database.connect()` needed before executing a query.
* Added database-agnostic interface for obtaining a random value.
* Allow `isolation_level` to be specified when initializing a Postgres db.
* Allow hybrid properties to be used on model aliases. Refs #1969.
* Support aggregates with FILTER predicates on the latest Sqlite.

#### Changes

* More aggressively slot row values into the appropriate field when building
  objects from the database cursor (rather than using whatever
  `cursor.description` tells us, which is buggy in older Sqlite).
* Be more permissive in what we accept in the `insert_many()` and `insert()`
  methods.
* When implicitly joining a model with multiple foreign-keys, choose the
  foreign-key whose name matches that of the related model. Previously, this
  would have raised a `ValueError` stating that multiple FKs existed.
* Improved date truncation logic for Sqlite and MySQL to make more compatible
  with Postgres' `date_trunc()` behavior. Previously, truncating a datetime to
  month resolution would return `'2019-08'` for example. As of 3.10.0, the
  Sqlite and MySQL `date_trunc` implementation returns a full datetime, e.g.
  `'2019-08-01 00:00:00'`.
* Apply slightly different logic for casting JSON values with Postgres.
  Previously, Peewee just wrapped the value in the psycopg2 `Json()` helper.
  In this version, Peewee now dumps the json to a string and applies an
  explicit cast to the underlying JSON data-type (e.g. json or jsonb).

#### Bug fixes

* Save hooks can now be called for models without a primary key.
* Fixed bug in the conversion of Python values to JSON when using Postgres.
* Fix for differentiating empty values from NULL values in `model_to_dict`.
* Fixed a bug referencing primary-key values that required some kind of
  conversion (e.g., a UUID). See #1979 for details.
* Add small jitter to the pool connection timestamp to avoid issues when
  multiple connections are checked-out at the same exact time.

[View commits](https://github.com/coleifer/peewee/compare/3.9.6...3.10.0)

## 3.9.6

* Support nesting the `Database` instance as a context-manager. The outermost
  block will handle opening and closing the connection along with wrapping
  everything in a transaction. Nested blocks will use savepoints.
* Add new `session_start()`, `session_commit()` and `session_rollback()`
  interfaces to the Database object to support using transactional controls in
  situations where a context-manager or decorator is awkward.
* Fix error that would arise when attempting to do an empty bulk-insert.
* Set `isolation_level=None` in SQLite connection constructor rather than
  afterwards using the setter.
* Add `create_table()` method to `Select` query to implement `CREATE TABLE AS`.
* Cleanup some declarations in the Sqlite C extension.
* Add new example showing how to implement Reddit's ranking algorithm in SQL.

[View commits](https://github.com/coleifer/peewee/compare/3.9.5...3.9.6)

## 3.9.5

* Added small helper for setting timezone when using Postgres.
* Improved SQL generation for `VALUES` clause.
* Support passing resolution to `TimestampField` as a power-of-10.
* Small improvements to `INSERT` queries when the primary-key is not an
  auto-incrementing integer, but is generated by the database server (eg uuid).
* Cleanups to virtual table implementation and python-to-sqlite value
  conversions.
* Fixed bug related to binding previously-unbound models to a database using a
  context manager, #1913.

[View commits](https://github.com/coleifer/peewee/compare/3.9.4...3.9.5)

## 3.9.4

* Add `Model.bulk_update()` method for bulk-updating fields across multiple
  model instances. [Docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#Model.bulk_update).
* Add `lazy_load` parameter to `ForeignKeyField`. When initialized with
  `lazy_load=False`, the foreign-key will not use an additional query to
  resolve the related model instance. Instead, if the related model instance is
  not available, the underlying FK column value is returned (behaving like the
  "_id" descriptor).
* Added `Model.truncate_table()` method.
* The `reflection` and `pwiz` extensions now attempt to be smarter about
  converting database table and column names into snake-case. To disable this,
  you can set `snake_case=False` when calling the `Introspector.introspect()`
  method or use the `-L` (legacy naming) option with the `pwiz` script.
* Bulk insert via ``insert_many()`` no longer require specification of the
  fields argument when the inserted rows are lists/tuples. In that case, the
  fields will be inferred to be all model fields except any auto-increment id.
* Add `DatabaseProxy`, which implements several of the `Database` class context
  managers. This allows you to reference some of the special features of the
  database object without directly needing to initialize the proxy first.
* Add support for window function frame exclusion and added built-in support
  for the GROUPS frame type.
* Add support for chaining window functions by extending a previously-declared
  window function.
* Playhouse Postgresql extension `TSVectorField.match()` method supports an
  additional argument `plain`, which can be used to control the parsing of the
  TS query.
* Added very minimal `JSONField` to the playhouse MySQL extension.

[View commits](https://github.com/coleifer/peewee/compare/3.9.3...3.9.4)

## 3.9.3

* Added cross-database support for `NULLS FIRST/LAST` when specifying the
  ordering for a query. Previously this was only supported for Postgres. Peewee
  will now generate an equivalent `CASE` statement for Sqlite and MySQL.
* Added [EXCLUDED](http://docs.peewee-orm.com/en/latest/peewee/api.html#EXCLUDED)
  helper for referring to the `EXCLUDED` namespace used with `INSERT...ON CONFLICT`
  queries, when referencing values in the conflicting row data.
* Added helper method to the model `Metadata` class for setting the table name
  at run-time. Setting the `Model._meta.table_name` directly may have appeared
  to work in some situations, but could lead to subtle bugs. The new API is
  `Model._meta.set_table_name()`.
* Enhanced helpers for working with Peewee interactively, [see doc](http://docs.peewee-orm.com/en/latest/peewee/interactive.html).
* Fix cache invalidation bug in `DataSet` that was originally reported on the
  sqlite-web project.
* New example script implementing a [hexastore](https://github.com/coleifer/peewee/blob/master/examples/hexastore.py).

[View commits](https://github.com/coleifer/peewee/compare/3.9.2...3.9.3)

## 3.9.1 and 3.9.2

Includes a bugfix for an `AttributeError` that occurs when using MySQL with the
`MySQLdb` client. The 3.9.2 release includes fixes for a test failure.

[View commits](https://github.com/coleifer/peewee/compare/3.9.0...3.9.2)

## 3.9.0

* Added new document describing how to [use peewee interactively](http://docs.peewee-orm.com/en/latest/peewee/interactive.html).
* Added convenience functions for generating model classes from a pre-existing
  database, printing model definitions and printing CREATE TABLE sql for a
  model. See the "use peewee interactively" section for details.
* Added a `__str__` implementation to all `Query` subclasses which converts the
  query to a string and interpolates the parameters.
* Improvements to `sqlite_ext.JSONField` regarding the serialization of data,
  as well as the addition of options to override the JSON serialization and
  de-serialization functions.
* Added `index_type` parameter to `Field`
* Added `DatabaseProxy`, which allows one to use database-specific decorators
  with an uninitialized `Proxy` object. See #1842 for discussion. Recommend
  that you update any usage of `Proxy` for deferring database initialization to
  use the new `DatabaseProxy` class instead.
* Added support for `INSERT ... ON CONFLICT` when the conflict target is a
  partial index (e.g., contains a `WHERE` clause). The `OnConflict` and
  `on_conflict()` APIs now take an additional `conflict_where` parameter to
  represent the `WHERE` clause of the partial index in question. See #1860.
* Enhanced the `playhouse.kv` extension to use efficient upsert for *all*
  database engines. Previously upsert was only supported for sqlite and mysql.
* Re-added the `orwhere()` query filtering method, which will append the given
  expressions using `OR` instead of `AND`. See #391 for old discussion.
* Added some new examples to the ``examples/`` directory
* Added `select_from()` API for wrapping a query and selecting one or more
  columns from the wrapped subquery. [Docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#SelectQuery.select_from).
* Added documentation on using [row values](http://docs.peewee-orm.com/en/latest/peewee/query_operators.html#row-values).
* Removed the (defunct) "speedups" C extension, which as of 3.8.2 only
  contained a barely-faster function for quoting entities.

**Bugfixes**

* Fix bug in SQL generation when there was a subquery that used a common table
  expressions.
* Enhanced `prefetch()` and fixed bug that could occur when mixing
  self-referential foreign-keys and model aliases.
* MariaDB 10.3.3 introduces backwards-incompatible changes to the SQL used for
  upsert. Peewee now introspects the MySQL server version at connection time to
  ensure proper handling of version-specific features. See #1834 for details.
* Fixed bug where `TimestampField` would treat zero values as `None` when
  reading from the database.

[View commits](https://github.com/coleifer/peewee/compare/3.8.2...3.9.0)

## 3.8.2

**Backwards-incompatible changes**

* The default row-type for `INSERT` queries executed with a non-default
  `RETURNING` clause has changed from `tuple` to `Model` instances. This makes
  `INSERT` behavior consistent with `UPDATE` and `DELETE` queries that specify
  a `RETURNING` clause. To revert back to the old behavior, just append a call
  to `.tuples()` to your `INSERT ... RETURNING` query.
* Removing support for the `table_alias` model `Meta` option. Previously, this
  attribute could be used to specify a "vanity" alias for a model class in the
  generated SQL. As a result of some changes to support more robust UPDATE and
  DELETE queries, supporting this feature will require some re-working. As of
  the 3.8.0 release, it was broken and resulted in incorrect SQL for UPDATE
  queries, so now it is removed.

**New features**

* Added `playhouse.shortcuts.ReconnectMixin`, which can be used to implement
  automatic reconnect under certain error conditions (notably the MySQL error
  2006 - server has gone away).

**Bugfixes**

* Fix SQL generation bug when using an inline window function in the `ORDER BY`
  clause of a query.
* Fix possible zero-division in user-defined implementation of BM25 ranking
  algorithm for SQLite full-text search.

[View commits](https://github.com/coleifer/peewee/compare/3.8.1...3.8.2)

## 3.8.1

**New features**

* Sqlite `SearchField` now supports the `match()` operator, allowing full-text
  search to be performed on a single column (as opposed to the whole table).

**Changes**

* Remove minimum passphrase restrictions in SQLCipher integration.

**Bugfixes**

* Support inheritance of `ManyToManyField` instances.
* Ensure operator overloads are invoked when generating filter expressions.
* Fix incorrect scoring in Sqlite BM25, BM25f and Lucene ranking algorithms.
* Support string field-names in data dictionary when performing an ON CONFLICT
  ... UPDATE query, which allows field-specific conversions to be applied.
  References #1815.

[View commits](https://github.com/coleifer/peewee/compare/3.8.0...3.8.1)

## 3.8.0

**New features**

* Postgres `BinaryJSONField` now supports `has_key()`, `concat()` and
  `remove()` methods (though remove may require pg10+).
* Add `python_value()` method to the SQL-function helper `fn`, to allow
  specifying a custom function for mapping database values to Python values.

**Changes**

* Better support for UPDATE ... FROM queries, and more generally, more robust
  support for UPDATE and RETURNING clauses. This means that the
  `QualifiedNames` helper is no longer needed for certain types of queries.
* The `SqlCipherDatabase` no longer accepts a `kdf_iter` parameter. To
  configure the various SQLCipher encryption settings, specify the setting
  values as `pragmas` when initializing the database.
* Introspection will now, by default, only strip "_id" from introspected column
  names if those columns are foreign-keys. See #1799 for discussion.
* Allow `UUIDField` and `BinaryUUIDField` to accept hexadecimal UUID strings as
  well as raw binary UUID bytestrings (in addition to `UUID` instances, which
  are already supported).
* Allow `ForeignKeyField` to be created without an index.
* Allow multiple calls to `cast()` to be chained (#1795).
* Add logic to ensure foreign-key constraint names that exceed 64 characters
  are truncated using the same logic as is currently in place for long indexes.
* `ManyToManyField` supports foreign-keys to fields other than primary-keys.
* When linked against SQLite 3.26 or newer, support `SQLITE_CONSTRAINT` to
  designate invalid queries against virtual tables.
* SQL-generation changes to aid in supporting using queries within expressions
  following the SELECT statement.

**Bugfixes**

* Fixed bug in `order_by_extend()`, thanks @nhatHero.
* Fixed bug where the `DataSet` CSV import/export did not support non-ASCII
  characters in Python 3.x.
* Fixed bug where `model_to_dict` would attempt to traverse explicitly disabled
  foreign-key backrefs (#1785).
* Fixed bug when attempting to migrate SQLite tables that have a field whose
  column-name begins with "primary_".
* Fixed bug with inheriting deferred foreign-keys.

[View commits](https://github.com/coleifer/peewee/compare/3.7.1...3.8.0)

## 3.7.1

**New features**

* Added `table_settings` model `Meta` option, which should be a list of strings
  specifying additional options for `CREATE TABLE`, which are placed *after*
  the closing parentheses.
* Allow specification of `on_update` and `on_delete` behavior for many-to-many
  relationships when using `ManyToManyField`.

**Bugfixes**

* Fixed incorrect SQL generation for Postgresql ON CONFLICT clause when the
  conflict_target is a named constraint (rather than an index expression). This
  introduces a new keyword-argument to the `on_conflict()` method:
  `conflict_constraint`, which is currently only supported by Postgresql. Refs
  issue #1737.
* Fixed incorrect SQL for sub-selects used on the right side of `IN`
  expressions. Previously the query would be assigned an alias, even though an
  alias was not needed.
* Fixed incorrect SQL generation for Model indexes which contain SQL functions
  as indexed columns.
* Fixed bug in the generation of special queries used to perform operations on
  SQLite FTS5 virtual tables.
* Allow `frozenset` to be correctly parameterized as a list of values.
* Allow multi-value INSERT queries to specify `columns` as a list of strings.
* Support `CROSS JOIN` for model select queries.

[View commits](https://github.com/coleifer/peewee/compare/3.7.0...3.7.1)

## 3.7.0

**Backwards-incompatible changes**

* Pool database `close_all()` method renamed to `close_idle()` to better
  reflect the actual behavior.
* Databases will now raise `InterfaceError` when `connect()` or `close()` are
  called on an uninitialized, deferred database object.

**New features**

* Add methods to the migrations extension to support adding and dropping table
  constraints.
* Add [Model.bulk_create()](http://docs.peewee-orm.com/en/latest/peewee/api.html#Model.bulk_create)
  method for bulk-inserting unsaved model instances.
* Add `close_stale()` method to the connection pool to support closing stale
  connections.
* The `FlaskDB` class in `playhouse.flask_utils` now accepts a `model_class`
  parameter, which can be used to specify a custom base-class for models.

**Bugfixes**

* Parentheses were not added to subqueries used in function calls with more
  than one argument.
* Fixed bug when attempting to serialize many-to-many fields which were created
  initially with a `DeferredThroughModel`, see #1708.
* Fixed bug when using the Postgres `ArrayField` with an array of `BlobField`.
* Allow `Proxy` databases to be used as a context-manager.
* Fixed bug where the APSW driver was referring to the SQLite version from the
  standard library `sqlite3` driver, rather than from `apsw`.
* Reflection library attempts to wrap server-side column defaults in quotation
  marks if the column data-type is text/varchar.
* Missing import in migrations library, which would cause errors when
  attempting to add indexes whose name exceeded 64 chars.
* When using the Postgres connection pool, ensure any open/pending transactions
  are rolled-back when the connection is recycled.
* Even *more* changes to the `setup.py` script. In this case I've added a
  helper function which will reliably determine if the SQLite3 extensions can
  be built. This follows the approach taken by the Python YAML package.

[View commits](https://github.com/coleifer/peewee/compare/3.6.4...3.7.0)

## 3.6.4

Take a whole new approach, following what `simplejson` does. Allow the
`build_ext` command class to fail, and retry without extensions in the event we
run into issues building extensions. References #1676.

[View commits](https://github.com/coleifer/peewee/compare/3.6.3...3.6.4)

## 3.6.3

Add check in `setup.py` to determine if a C compiler is available before
building C extensions. References #1676.

[View commits](https://github.com/coleifer/peewee/compare/3.6.2...3.6.3)

## 3.6.2

Use `ctypes.util.find_library` to determine if `libsqlite3` is installed.
Should fix problems people are encountering installing when SQLite3 is not
available.

[View commits](https://github.com/coleifer/peewee/compare/3.6.1...3.6.2)

## 3.6.1

Fixed issue with setup script.

[View commits](https://github.com/coleifer/peewee/compare/3.6.0...3.6.1)

## 3.6.0

* Support for Python 3.7, including bugfixes related to new StopIteration
  handling inside of generators.
* Support for specifying `ROWS` or `RANGE` window frame types. For more
  information, see the new [frame type documentation](http://docs.peewee-orm.com/en/latest/peewee/querying.html#frame-types-range-vs-rows).
* Add APIs for user-defined window functions if using [pysqlite3](https://github.com/coleifer/pysqlite3)
  and sqlite 3.25.0 or newer.
* `TimestampField` now uses 64-bit integer data-type for storage.
* Added support to `pwiz` and `playhouse.reflection` to enable generating
  models from VIEWs.
* Added lower-level database API for introspecting VIEWs.
* Revamped continuous integration setup for better coverage, including 3.7 and
  3.8-dev.
* Allow building C extensions even if Cython is not installed, by distributing
  pre-generated C source files.
* Switch to using `setuptools` for packaging.

[View commits](https://github.com/coleifer/peewee/compare/3.5.2...3.6.0)

## 3.5.2

* New guide to using [window functions in Peewee](http://docs.peewee-orm.com/en/latest/peewee/querying.html#window-functions).
* New and improved table name auto-generation. This feature is not backwards
  compatible, so it is **disabled by default**. To enable, set
  `legacy_table_names=False` in your model's `Meta` options. For more details,
  see [table names](http://docs.peewee-orm.com/en/latest/peewee/models.html#table_names)
  documentation.
* Allow passing single fields/columns to window function `order_by` and
  `partition_by` arguments.
* Support for `FILTER (WHERE...)` clauses with window functions and aggregates.
* Added `IdentityField` class suitable for use with Postgres 10's new identity
  column type. It can be used anywhere `AutoField` or `BigAutoField` was being
  used previously.
* Fixed bug creating indexes on tables that are in attached databases (SQLite).
* Fixed obscure bug when using `prefetch()` and `ModelAlias` to populate a
  back-reference related model.

[View commits](https://github.com/coleifer/peewee/compare/3.5.1...3.5.2)

## 3.5.1

**New features**

* New documentation for working with [relationships](http://docs.peewee-orm.com/en/latest/peewee/relationships.html)
  in Peewee.
* Improved tests and documentation for MySQL upsert functionality.
* Allow `database` parameter to be specified with `ModelSelect.get()` method.
  For discussion, see #1620.
* Add `QualifiedNames` helper to peewee module exports.
* Add `temporary=` meta option to support temporary tables.
* Allow a `Database` object to be passed to constructor of `DataSet` helper.

**Bug fixes**

* Fixed edge-case where attempting to alias a field to it's underlying
  column-name (when different), Peewee would not respect the alias and use the
  field name instead. See #1625 for details and discussion.
* Raise a `ValueError` when joining and aliasing the join to a foreign-key's
  `object_id_name` descriptor. Should prevent accidentally introducing O(n)
  queries or silently ignoring data from a joined-instance.
* Fixed bug for MySQL when creating a foreign-key to a model which used the
  `BigAutoField` for it's primary-key.
* Fixed bugs in the implementation of user-defined aggregates and extensions
  with the APSW SQLite driver.
* Fixed regression introduced in 3.5.0 which ignored custom Model `__repr__()`.
* Fixed regression from 2.x in which inserting from a query using a `SQL()` was
  no longer working. Refs #1645.

[View commits](https://github.com/coleifer/peewee/compare/3.5.0...3.5.1)

## 3.5.0

**Backwards-incompatible changes**

* Custom Model `repr` no longer use the convention of overriding `__unicode__`,
  and now use `__str__`.
* Redesigned the [sqlite json1 integration](http://docs.peewee-orm.com/en/latest/peewee/sqlite_ext.html#sqlite-json1).
  and changed some of the APIs and semantics of various `JSONField` methods.
  The documentation has been expanded to include more examples and the API has
  been simplified to make it easier to work with. These changes **do not** have
  any effect on the [Postgresql JSON fields](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pgjson).

**New features**

* Better default `repr` for model classes and fields.
* `ForeignKeyField()` accepts a new initialization parameter, `deferrable`, for
  specifying when constraints should be enforced.
* `BitField.flag()` can be called without a value parameter for the common
  use-case of using flags that are powers-of-2.
* `SqliteDatabase` pragmas can be specified as a `dict` (previously required a
  list of 2-tuples).
* SQLite `TableFunction` ([docs](http://docs.peewee-orm.com/en/latest/peewee/sqlite_ext.html#sqlite-vtfunc))
  will print Python exception tracebacks raised in the `initialize` and
  `iterate` callbacks, making debugging significantly easier.

**Bug fixes**

* Fixed bug in `migrator.add_column()` where, if the field being added declared
  a non-standard index type (e.g., binary json field with GIN index), this
  index type was not being respected.
* Fixed bug in `database.table_exists()` where the implementation did not match
  the documentation. Implementation has been updated to match the
  documentation.
* Fixed bug in SQLite `TableFunction` implementation which raised errors if the
  return value of the `iterate()` method was not a `tuple`.

[View commits](https://github.com/coleifer/peewee/compare/3.4.0...3.5.0)

## 3.4.0

**Backwards-incompatible changes**

* The `regexp()` operation is now case-sensitive for MySQL and Postgres. To
  perform case-insensitive regexp operations, use `iregexp()`.
* The SQLite `BareField()` field-type now supports all column constraints
  *except* specifying the data-type. Previously it silently ignored any column
  constraints.
* LIMIT and OFFSET parameters are now treated as parameterized values instead
  of literals.
* The `schema` parameter for SQLite database introspection methods is no longer
  ignored by default. The schema corresponds to the name given to an attached
  database.
* `ArrayField` now accepts a new parameter `field_kwargs`, which is used to
  pass information to the array field's `field_class` initializer.

**New features and other changes**

* SQLite backup interface supports specifying page-counts and a user-defined
  progress handler.
* GIL is released when doing backups or during SQLite busy timeouts (when using
  the peewee SQLite busy-handler).
* Add NATURAL join-type to the `JOIN` helper.
* Improved identifier quoting to allow specifying distinct open/close-quote
  characters. Enables adding support for MSSQL, for instance, which uses square
  brackets, e.g. `[table].[column]`.
* Unify timeout interfaces for SQLite databases (use seconds everywhere rather
  than mixing seconds and milliseconds, which was confusing).
* Added `attach()` and `detach()` methods to SQLite database, making it
  possible to attach additional databases (e.g. an in-memory cache db).

[View commits](https://github.com/coleifer/peewee/compare/3.3.4...3.4.0)

## 3.3.4

* Added a `BinaryUUIDField` class for efficiently storing UUIDs in 16-bytes.
* Fix dataset's `update_cache()` logic so that when updating a single table
  that was newly-added, we also ensure that all dependent tables are updated at
  the same time. Refs coleifer/sqlite-web#42.

[View commits](https://github.com/coleifer/peewee/compare/3.3.3...3.3.4)

## 3.3.3

* More efficient implementation of model dependency-graph generation. Improves
  performance of recursively deleting related objects by omitting unnecessary
  subqueries.
* Added `union()`, `union_all()`, `intersect()` and `except_()` to the
  `Model`-specific query implementations. This was an oversight that should
  have been patched in 3.3.2, but is fixed in 3.3.3.
* Major cleanup to test runner and standardized test skipping logic to
  integrate with standard-library `unittest` conventions.

[View commits](https://github.com/coleifer/peewee/compare/3.3.2...3.3.3)

## 3.3.2

* Add methods for `union()`, `union_all`, `intersect()` and `except_()`.
  Previously, these methods were only available as operator overloads.
* Removed some Python 2.6-specific support code, as 2.6 is no longer officially
  supported.
* Fixed model-graph resolution logic for deferred foreign-keys.
* Better support for UPDATE...FROM queries (Postgresql).

[View commits](https://github.com/coleifer/peewee/compare/3.3.1...3.3.2)

## 3.3.1

* Fixed long-standing bug in 3.x regarding using column aliases with queries
  that utilize the ModelCursorWrapper (typically queries with one or more
  joins).
* Fix typo in model metadata code, thanks @klen.
* Add examples of using recursive CTEs to docs.

[View commits](https://github.com/coleifer/peewee/compare/3.3.0...3.3.1)

## 3.3.0

* Added support for SQLite's new `ON CONFLICT` clause, which is modelled on the
  syntax used by Postgresql and will be available in SQLite 3.24.0 and onward.
* Added better support for using common table expressions and a cleaner way of
  implementing recursive CTEs, both of which are also tested with integration
  tests (as opposed to just checking the generated SQL).
* Modernized the CI environment to utilize the latest MariaDB features, so we
  can test window functions and CTEs with MySQL (when available).
* Reorganized and unified the feature-flags in the test suite.

[View commits](https://github.com/coleifer/peewee/compare/3.2.5...3.3.0)

## 3.2.5

* Added `ValuesList` for representing values lists. [Docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#ValuesList).
* `DateTimeField`, `DateField` and `TimeField` will parse formatted-strings
  before sending to the database. Previously this only occurred when reading
  values from the database.

[View commits](https://github.com/coleifer/peewee/compare/3.2.4...3.2.5)

## 3.2.4

* Smarter handling of model-graph when dealing with compound queries (union,
  intersect, etc). #1579.
* If the same column-name is selected multiple times, first value wins. #1579.
* If `ModelSelect.switch()` is called without any arguments, default to the
  query's model. Refs #1573.
* Fix issue where cloning a ModelSelect query did not result in the joins being
  cloned. #1576.

[View commits](https://github.com/coleifer/peewee/compare/3.2.3...3.2.4)

## 3.2.3

* `pwiz` tool will capture column defaults defined as part of the table schema.
* Fixed a misleading error message - #1563.
* Ensure `reuse_if_open` parameter has effect on pooled databases.
* Added support for on update/delete when migrating foreign-key.
* Fixed bug in SQL generation for subqueries in aliased functions #1572.

[View commits](https://github.com/coleifer/peewee/compare/3.2.2...3.2.3)

## 3.2.2

* Added support for passing `Model` classes to the `returning()` method when
  you intend to return all columns for the given model.
* Fixed a bug when using user-defined sequences, and the underlying sequence
  already exists.
* Added `drop_sequences` parameter to `drop_table()` method which allows you to
  conditionally drop any user-defined sequences when dropping the table.

[View commits](https://github.com/coleifer/peewee/compare/3.2.1...3.2.2)

## 3.2.1

**Notice:** the default mysql driver for Peewee has changed to [pymysql](https://github.com/PyMySQL/PyMySQL)
in version 3.2.1. In previous versions, if both *mysql-python* and *pymysql*
were installed, Peewee would use *mysql-python*. As of 3.2.1, if both libraries
are installed Peewee will use *pymysql*.

* Added new module `playhouse.mysql_ext` which includes
  `MySQLConnectorDatabase`, a database implementation that works with the
  [mysql-connector](https://dev.mysql.com/doc/connector-python/en/) driver.
* Added new field to `ColumnMetadata` class which captures a database column's
  default value. `ColumnMetadata` is returned by `Database.get_columns()`.
* Added [documentation on making Peewee async](http://docs.peewee-orm.com/en/latest/peewee/database.html#async-with-gevent).

[View commits](https://github.com/coleifer/peewee/compare/3.2.0...3.2.1)

## 3.2.0

The 3.2.0 release introduces a potentially backwards-incompatible change. The
only users affected will be those that have implemented custom `Field` types
with a user-defined `coerce` method. tl/dr: rename the coerce attribute to
adapt and you should be set.

#### Field.coerce renamed to Field.adapt

The `Field.coerce` method has been renamed to `Field.adapt`. The purpose of
this method is to convert a value from the application/database into the
appropriate Python data-type. For instance, `IntegerField.adapt` is simply the
`int` built-in function.

The motivation for this change is to support adding metadata to any AST node
instructing Peewee to not coerce the associated value. As an example, consider
this code:

```python

class Note(Model):
    id = AutoField()  # autoincrementing integer primary key.
    content = TextField()

# Query notes table and cast the "id" to a string and store as "id_text" attr.
query = Note.select(Note.id.cast('TEXT').alias('id_text'), Note.content)

a_note = query.get()
print((a_note.id_text, a_note.content))

# Prior to 3.2.0 the CAST is "un-done" because the value gets converted
# back to an integer, since the value is associated with the Note.id field:
(1, u'some note')  # 3.1.7, e.g. -- "id_text" is an integer!

# As of 3.2.0, CAST will automatically prevent the conversion of field values,
# which is an extension of a more general metadata API that can instruct Peewee
# not to convert certain values.
(u'1', u'some note')  # 3.2.0 -- "id_text" is a string as expected.
```

If you have implemented custom `Field` classes and are using `coerce` to
enforce a particular data-type, you can simply rename the attribute to `adapt`.

#### Other changes

Old versions of SQLite do not strip quotation marks from aliased column names
in compound queries (e.g. UNION). Fixed in 3.2.0.

[View commits](https://github.com/coleifer/peewee/compare/3.1.7...3.2.0)

## 3.1.7

For all the winblows lusers out there, added an option to skip compilation of
the SQLite C extensions during installation. Set env var `NO_SQLITE=1` and run
`setup.py install` and you should be able to build without requiring SQLite.

[View commits](https://github.com/coleifer/peewee/compare/3.1.6...3.1.7)

## 3.1.6

* Added `rekey()` method to SqlCipher database for changing encryption key and
  documentation for `set_passphrase()` method.
* Added `convert_values` parameter to `ArrayField` constructor, which will
  cause the array values to be processed using the underlying data-type's
  conversion logic.
* Fixed unreported bug using `TimestampField` with sub-second resolutions.
* Fixed bug where options were not being processed when calling `drop_table()`.
* Some fixes and improvements to `signals` extension.

[View commits](https://github.com/coleifer/peewee/compare/3.1.5...3.1.6)

## 3.1.5

Fixed Python 2/3 incompatibility with `itertools.izip_longest()`.

[View commits](https://github.com/coleifer/peewee/compare/3.1.4...3.1.5)

## 3.1.4

* Added `BigAutoField` to support 64-bit auto-incrementing primary keys.
* Use Peewee-compatible datetime serialization when exporting JSON from
  a `DataSet`. Previously the JSON export used ISO-8601 by default. See #1536.
* Added `Database.batch_commit` helper to wrap iterators in chunked
  transactions. See #1539 for discussion.

[View commits](https://github.com/coleifer/peewee/compare/3.1.3...3.1.4)

## 3.1.3

* Fixed issue where scope-specific settings were being updated in-place instead
  of copied. #1534.
* Fixed bug where setting a `ForeignKeyField` did not add it to the model's
  "dirty" fields list. #1530.
* Use pre-fetched data when using `prefetch()` with `ManyToManyField`. Thanks
  to @iBelieve for the patch. #1531.
* Use `JSON` data-type for SQLite `JSONField` instances.
* Add a `json_contains` function for use with SQLite `json1` extension.
* Various documentation updates and additions.

[View commits](https://github.com/coleifer/peewee/compare/3.1.2...3.1.3)

## 3.1.2

#### New behavior for INSERT queries with RETURNING clause

Investigating #1522, it occurred to me that INSERT queries with non-default
*RETURNING* clauses (postgres-only feature) should always return a cursor
object. Previously, if executing a single-row INSERT query, the last-inserted
row ID would be returned, regardless of what was specified by the RETURNING
clause.

This change only affects INSERT queries with non-default RETURNING clauses and
will cause a cursor to be returned, as opposed to the last-inserted row ID.

[View commits](https://github.com/coleifer/peewee/compare/3.1.1...3.1.2)

## 3.1.1

* Fixed bug when using `Model.alias()` when the model defined a particular
  database schema.
* Added `SchemaManager.create_foreign_key` API to simplify adding constraints
  when dealing with circular foreign-key relationships. Updated docs
  accordingly.
* Improved implementation of `Migrator.add_foreign_key_constraint` so that it
  can be used with Postgresql (in addition to MySQL).
* Added `PickleField` to the `playhouse.fields` module. [Docs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#PickleField).
* Fixed bug in implementation of `CompressedField` when using Python 3.
* Added `KeyValue` API in `playhouse.kv` module. [Docs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#key-value-store).
* More test cases for joining on sub-selects or common table expressions.

[View commits](https://github.com/coleifer/peewee/compare/3.1.0...3.1.1)

## 3.1.0

#### Backwards-incompatible changes

`Database.bind()` has been renamed to `Database.bind_ctx()`, to more closely
match the semantics of the corresponding model methods, `Model.bind()` and
`Model.bind_ctx()`. The new `Database.bind()` method is a one-time operation
that binds the given models to the database. See documentation:

* [Database.bind()](http://docs.peewee-orm.com/en/latest/peewee/api.html#Database.bind)
* [Database.bind_ctx()](http://docs.peewee-orm.com/en/latest/peewee/api.html#Database.bind_ctx)

#### Other changes

* Removed Python 2.6 support code from a few places.
* Fixed example analytics app code to ensure hstore extension is registered.
* Small efficiency improvement to bloom filter.
* Removed "attention!" from *README*.

[View commits](https://github.com/coleifer/peewee/compare/3.0.20...3.1.0)

## 3.0.20

* Include `schema` (if specified) when checking for table-existence.
* Correct placement of ORDER BY / LIMIT clauses in compound select queries.
* Fix bug in back-reference lookups when using `filter()` API.
* Fix bug in SQL generation for ON CONFLICT queries with Postgres, #1512.

[View commits](https://github.com/coleifer/peewee/compare/3.0.19...3.0.20)

## 3.0.19

* Support for more types of mappings in `insert_many()`, refs #1495.
* Lots of documentation improvements.
* Fix bug when calling `tuples()` on a `ModelRaw` query. This was reported
  originally as a bug with *sqlite-web* CSV export. See coleifer/sqlite-web#38.

[View commits](https://github.com/coleifer/peewee/compare/3.0.18...3.0.19)

## 3.0.18

* Improved error messages when attempting to use a database class for which the
  corresponding driver is not installed.
* Added tests showing the use of custom operator (a-la the docs).
* Fixed indentation issue in docs, #1493.
* Fixed issue with the SQLite date_part issue, #1494.

[View commits](https://github.com/coleifer/peewee/compare/3.0.17...3.0.18)

## 3.0.17

* Fix `schema` inheritance regression, #1485.
* Add helper method to postgres migrator for setting search_path, #1353.

[View commits](https://github.com/coleifer/peewee/compare/3.0.16...3.0.17)

## 3.0.16

* Improve model graph resolution when iterating results of a query. Refs #1482.
* Allow Model._meta.schema to be changed at run-time. #1483.

[View commits](https://github.com/coleifer/peewee/compare/3.0.15...3.0.16)

## 3.0.15

* Use same `schema` used for reflection in generated models.
* Preserve `pragmas` set on deferred Sqlite database if database is
  re-initialized without re-specifying pragmas.

[View commits](https://github.com/coleifer/peewee/compare/3.0.14...3.0.15)

## 3.0.14

* Fix bug creating model instances on Postgres when model does not have a
  primary key column.
* Extend postgresql reflection to support array types.

[View commits](https://github.com/coleifer/peewee/compare/3.0.13...3.0.14)

## 3.0.13

* Fix bug where simple field aliases were being ignored. Fixes #1473.
* More strict about column type inference for postgres + pwiz.

[View commits](https://github.com/coleifer/peewee/compare/3.0.12...3.0.13)

## 3.0.12

* Fix queries of the form INSERT ... VALUES (SELECT...) so that sub-select is
  wrapped in parentheses.
* Improve model-graph resolution when selecting from multiple tables that are
  joined by foreign-keys, and an intermediate table is omitted from selection.
* Docs update to reflect deletion of post_init signal.

[View commits](https://github.com/coleifer/peewee/compare/3.0.11...3.0.12)

## 3.0.11

* Add note to changelog about `cursor()` method.
* Add hash method to postgres indexedfield subclasses.
* Add TableFunction to sqlite_ext module namespace.
* Fix bug regarding NOT IN queries where the right-hand-side is an empty set.
* Fallback implementations of bm25f and lucene search ranking algorithms.
* Fixed DecimalField issue.
* Fixed issue with BlobField when database is a Proxy object.

[View commits](https://github.com/coleifer/peewee/compare/3.0.10...3.0.11)

## 3.0.10

* Fix `Database.drop_tables()` signature to support `cascade` argument - #1453.
* Fix querying documentation for custom functions - #1454.
* Added len() method to `ModelBase` for convenient counting.
* Fix bug related to unsaved relation population (thanks @conqp) - #1459.
* Fix count() on compound select - #1460.
* Support `coerce` keyword argument with `fn.XXX()` - #1463.
* Support updating existing model instance with dict_to_model-like API - #1456.
* Fix equality tests with ArrayField - #1461.

[View commits](https://github.com/coleifer/peewee/compare/3.0.9...3.0.10)

## 3.0.9

* Add deprecation notice if passing `autocommit` as keyword argument to the
  `Database` initializer. Refs #1452.
* Add `JSONPath` and "J" helpers to sqlite extension.

[View commits](https://github.com/coleifer/peewee/compare/3.0.8...3.0.9)

## 3.0.8

* Add support for passing `cascade=True` when dropping tables. Fixes #1449.
* Fix issues with backrefs and inherited foreign-keys. Fixes #1448.

[View commits](https://github.com/coleifer/peewee/compare/3.0.7...3.0.8)

## 3.0.7

* Add `select_extend()` method to extend existing SELECT-ion. [Doc](http://docs.peewee-orm.com/en/latest/peewee/api.html#Select.select_extend).
* Accept `set()` as iterable value type, fixes #1445
* Add test for model/field inheritance and fix bug relating to recursion error
  when inheriting foreign-key field. Fixes #1448.
* Fix regression where consecutive calls to `ModelSelect.select()` with no
  parameters resulted in an empty selection. Fixes #1438.

[View commits](https://github.com/coleifer/peewee/compare/3.0.6...3.0.7)

## 3.0.6

Add constraints for ON UPDATE/ON DELETE to foreign-key constraint - #1443.

[View commits](https://github.com/coleifer/peewee/compare/3.0.5...3.0.6)

## 3.0.5

Adds Model.index(), a short-hand method for declaring ModelIndex instances.

* [Model.index docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#Model.index)
* [Model.add_index docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#Model.add_index)
* [ModelIndex docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#ModelIndex)

[View commits](https://github.com/coleifer/peewee/compare/3.0.4...3.0.5)

## 3.0.4

Re-add a shim for `PrimaryKeyField` (renamed to `AutoField`) and log a
deprecation warning if you try to use it.

[View commits](https://github.com/coleifer/peewee/compare/3.0.3...3.0.4)

## 3.0.3

Includes fix for bug where column-name to field-name translation was not being
done when running select queries on models whose field name differed from the
underlying column name (#1437).

[View commits](https://github.com/coleifer/peewee/compare/3.0.2...3.0.3)

## 3.0.2

Ensures that the pysqlite headers are included in the source distribution so
that certain C extensions can be compiled.

[View commits](https://github.com/coleifer/peewee/compare/3.0.0...3.0.2)

## 3.0.0

* Complete rewrite of SQL AST and code-generation.
* Inclusion of new, low-level query builder APIs.
* List of [backwards-incompatible changes](http://docs.peewee-orm.com/en/latest/peewee/changes.html).

[View commits](https://github.com/coleifer/peewee/compare/2.10.2...3.0.0)

## 2.10.2

* Update travis-ci build scripts to use Postgres 9.6 and test against Python
  3.6.
* Added support for returning `namedtuple` objects when iterating over a
  cursor.
* Added support for specifying the "object id" attribute used when declaring a
  foreign key. By default, it is `foreign-key-name_id`, but it can now be
  customized.
* Fixed small bug in the calculation of search scores when using the SQLite C
  extension or the `sqlite_ext` module.
* Support literal column names with the `dataset` module.

[View commits](https://github.com/coleifer/peewee/compare/2.10.1...2.10.2)

## 2.10.1

Removed `AESEncryptedField`.

[View commits](https://github.com/coleifer/peewee/compare/2.10.0...2.10.1)

## 2.10.0

The main change in this release is the removal of the `AESEncryptedField`,
which was included as part of the `playhouse.fields` extension. It was brought
to my attention that there was some serious potential for security
vulnerabilities. Rather than give users a false sense of security, I've decided
the best course of action is to remove the field.

* Remove the `playhouse.fields.AESEncryptedField` over security concerns
described in ticket #1264.
* Correctly resolve explicit table dependencies when creating tables, refs
  #1076. Thanks @maaaks.
* Implement not equals comparison for `CompositeKey`.

[View commits](https://github.com/coleifer/peewee/compare/2.9.2...2.10.0)

## 2.9.2

* Fixed significant bug in the `savepoint` commit/rollback implementation. Many
  thanks to @Syeberman for raising the issue. See #1225 for details.
* Added support for postgresql `INTERVAL` columns. The new `IntervalField` in
  the `postgres_ext` module is suitable for storing `datetime.timedelta`.
* Fixed bug where missing `sqlite3` library was causing other, unrelated
  libraries to throw errors when attempting to import.
* Added a `case_sensitive` parameter to the SQLite `REGEXP` function
  implementation. The default is `False`, to preserve backwards-compatibility.
* Fixed bug that caused tables not to be created when using the `dataset`
  extension. See #1213 for details.
* Modified `drop_table` to raise an exception if the user attempts to drop
  tables with `CASCADE` when the database backend does not support it.
* Fixed Python3 issue in the `AESEncryptedField`.
* Modified the behavior of string-typed fields to treat the addition operator
  as concatenation. See #1241 for details.

[View commits](https://github.com/coleifer/peewee/compare/2.9.1...2.9.2)

## 2.9.1

* Fixed #1218, where the use of `playhouse.flask_utils` was requiring the
  `sqlite3` module to be installed.
* Fixed #1219 regarding the SQL generation for composite key sub-selects,
  joins, etc.

[View commits](https://github.com/coleifer/peewee/compare/2.9.0...2.9.1)

## 2.9.0

In this release there are two notable changes:

* The ``Model.create_or_get()`` method was removed. See the [documentation](http://docs.peewee-orm.com/en/latest/peewee/querying.html#create-or-get)
  for an example of the code one would write to replicate this functionality.
* The SQLite closure table extension gained support for many-to-many
  relationships thanks to a nice PR by @necoro. [Docs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#ClosureTable).

[View commits](https://github.com/coleifer/peewee/compare/2.8.8...2.9.0)

## 2.8.8

This release contains a single important bugfix for a regression in specifying
the type of lock to use when opening a SQLite transaction.

[View commits](https://github.com/coleifer/peewee/compare/2.8.7...2.8.8)

## 2.8.7

This release contains numerous cleanups.

### Bugs fixed

* #1087 - Fixed a misuse of the iteration protocol in the `sqliteq` extension.
* Ensure that driver exceptions are wrapped when calling `commit` and
  `rollback`.
* #1096 - Fix representation of recursive foreign key relations when using the
  `model_to_dict` helper.
* #1126 - Allow `pskel` to be installed into `bin` directory.
* #1105 - Added a `Tuple()` type to Peewee to enable expressing arbitrary
  tuple expressions in SQL.
* #1133 - Fixed bug in the conversion of objects to `Decimal` instances in the
  `DecimalField`.
* Fixed an issue renaming a unique foreign key in MySQL.
* Remove the join predicate from CROSS JOINs.
* #1148 - Ensure indexes are created when a column is added using a schema
  migration.
* #1165 - Fix bug where the primary key was being overwritten in queries using
  the closure-table extension.

### New stuff

* Added properties to the `SqliteExtDatabase` to expose common `PRAGMA`
  settings. For example, to set the cache size to 4MB, `db.cache_size = 1000`.
* Clarified documentation on calling `commit()` or `rollback()` from within the
  scope of an atomic block. [See docs](http://docs.peewee-orm.com/en/latest/peewee/transactions.html#transactions).
* Allow table creation dependencies to be specified using new `depends_on` meta
  option. Refs #1076.
* Allow specification of the lock type used in SQLite transactions. Previously
  this behavior was only present in `playhouse.sqlite_ext.SqliteExtDatabase`,
  but it now exists in `peewee.SqliteDatabase`.
* Added support for `CROSS JOIN` expressions in select queries.
* Docs on how to implement [optimistic locking](http://docs.peewee-orm.com/en/latest/peewee/hacks.html#optimistic-locking).
* Documented optional dependencies.
* Generic support for specifying select queries as locking the selected rows
  `FOR X`, e.g. `FOR UPDATE` or `FOR SHARE`.
* Support for specifying the frame-of-reference in window queries, e.g.
  specifying `UNBOUNDED PRECEDING`, etc. [See docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#Window).

### Backwards-incompatible changes

* As of 9e76c99, an `OperationalError` is raised if the user calls `connect()`
  on an already-open Database object. Previously, the existing connection would
  remain open and a new connection would overwrite it, making it impossible to
  close the previous connection. If you find this is causing breakage in your
  application, you can switch the `connect()` call to `get_conn()` which will
  only open a connection if necessary. The error **is** indicative of a real
  issue, though, so audit your code for places where you may be opening a
  connection without closing it (module-scope operations, e.g.).

[View commits](https://github.com/coleifer/peewee/compare/2.8.5...2.8.7)

## 2.8.6

This release was later removed due to containing a bug. See notes on 2.8.7.

## 2.8.5

This release contains two small bugfixes.

* #1081 - fixed the use of parentheses in compound queries on MySQL.
* Fixed some grossness in a helper function used by `prefetch` that was
  clearing out the `GROUP BY` and `HAVING` clauses of sub-queries.

[View commits](https://github.com/coleifer/peewee/compare/2.8.4...2.8.5)

## 2.8.4

This release contains bugfixes as well as a new playhouse extension module for
working with [SQLite in multi-threaded / concurrent environments](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#sqliteq).
The new module is called `playhouse.sqliteq` and it works by serializing
queries using a dedicated worker thread (or greenlet). The performance is quite
good, hopefully this proves useful to someone besides myself! You can learn
more by reading the [sqliteq documentation](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#sqliteq).

As a miscellaneous note, I did some major refactoring and cleanup in
`ExtQueryResultsWrapper` and it's corollary in the `speedups` module. The code
is much easier to read than before.

[View commits](https://github.com/coleifer/peewee/compare/2.8.3...2.8.4)

### Bugs fixed

* #1061 - @akrs patched a bug in `TimestampField` which affected the accuracy
  of sub-second timestamps (for resolution > 1).
* #1071, small python 3 fix.
* #1072, allow `DeferredRelation` to be used multiple times if there are
  multiple references to a given deferred model.
* #1073, fixed regression in the speedups module that caused SQL functions to
  always coerce return values, regardless of the `coerce` flag.
* #1083, another Python 3 issue - this time regarding the use of `exc.message`.

[View commits](https://github.com/coleifer/peewee/compare/2.8.3...2.8.4)

## 2.8.3

This release contains bugfixes and a small backwards-incompatible change to the
way foreign key `ObjectIdDescriptor` is named (issue #1050).

### Bugs fixed and general changes

* #1028 - allow the `ensure_join` method to accept `on` and `join_type`
  parameters. Thanks @paulbooth.
* #1032 - fix bug related to coercing model instances to database parameters
  when the model's primary key is a foreign key.
* #1035 - fix bug introduced in 2.8.2, where I had added some logic to try and
  restrict the base `Model` class from being treated as a "real" Model.
* #1039 - update documentation to clarify that lists *or tuples* are acceptable
  values when specifying SQLite `PRAGMA` statements.
* #1041 - PyPy user was unable to install Peewee. (Who in their right mind
  would *ever* use PyPy?!) Bug was fixed by removing the pre-generated C files
  from the distribution.
* #1043 - fix bug where the `speedups` C extension was not calling the correct
  model initialization method, resulting in model instances returned as results
  of a query having their `dirty` flag incorrectly set.
* #1048 - similar to #1043, add logic to ensure that fields with default values
  are considered dirty when instantiating the model.
* #1049 - update URL to [APSW](https://rogerbinns.github.io/apsw).
* Fixed unreported bug regarding `TimestampField` with zero values reporting
  the incorrect datetime.

### New stuff

* [djpeewee](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#djpeewee) extension
  module now works with Django 1.9.
* [TimestampField](http://docs.peewee-orm.com/en/latest/peewee/api.html#TimestampField)
  is now an officially documented field.
* #1050 - use the `db_column` of a `ForeignKeyField` for the name of the
  `ObjectIdDescriptor`, except when the `db_column` and field `name` are the
  same, in which case the ID descriptor will be named `<field_name>_id`.

[View commits](https://github.com/coleifer/peewee/compare/2.8.2...2.8.3)

## 2.8.2

This release contains mostly bug-fixes, clean-ups, and API enhancements.

### Bugs fixed and general cleanups

* #820 - fixed some bugs related to the Cython extension build process.
* #858 - allow blanks and perform type conversion when using the `db_url`
  extension
* #922 - ensure that `peewee.OperationalError` is raised consistently when
  using the `RetryOperationalError` mixin.
* #929 - ensure that `pwiz` will import the appropriate extensions when
  vendor-specific fields are used.
* #930 - ensure that `pwiz`-generated models containing `UnknownField`
  placeholders do not blow up when you instantiate them.
* #932 - correctly limit the length of automatically-generated index names.
* #933 - fixed bug where `BlobField` could not be used if it's parent model
  pointed to an uninitialized database `Proxy`.
* #935 - greater consistency with the conversion to Python data-types when
  performing aggregations, annotations, or calling `scalar()`.
* #939 - ensure the correct data-types are used when initializing a connection
  pool.
* #947 - fix bug where `Signal` subclasses were not returning rows affected on
  save.
* #951 - better warnings regarding C extension compilation, thanks @dhaase-de.
* #968 - fix bug where table names starting with numbers generated invalid
  table names when using `pwiz`.
* #971 - fix bug where parameter was not being used. Thanks @jberkel.
* #974 - fixed the way `SqliteExtDatabase` handles the automatic `rowid` (and
    `docid`) columns. Thanks for alerting me to the issue and providing a
    failing test case @jberkel.
* #976 - fix obscure bug relating to cloning foreign key fields twice.
* #981 - allow `set` instances to be used on the right-hand side of `IN` exprs.
* #983 - fix behavior where the default `id` primary key was inherited
  regardless. When users would inadvertently include it in their queries, it
  would use the table alias of it's parent class.
* #992 - add support for `db_column` in `djpeewee`
* #995 - fix the behavior of `truncate_date` with Postgresql. Thanks @Zverik.
* #1011 - correctly handle `bytes` wrapper used by `PasswordField` to `bytes`.
* #1012 - when selecting and joining on multiple models, do not create model
  instances when the foreign key is NULL.
* #1017 - do not coerce the return value of function calls to `COUNT` or `SUM`,
  since the python driver will already give us the right Python value.
* #1018 - use global state to resolve `DeferredRelations`, allowing for a nicer
  API. Thanks @brenguyen711.
* #1022 - attempt to avoid creating invalid Python when using `pwiz` with MySQL
  database columns containing spaces. Yes, fucking spaces.
* #1024 - fix bug in SQLite migrator which had a naive approach to fixing
  indexes.
* #1025 - explicitly check for `None` when determining if the database has been
  set on `ModelOptions`. Thanks @joeyespo.

### New stuff

* Added `TimestampField` for storing datetimes using integers. Greater than
  second delay is possible through exponentiation.
* Added `Database.drop_index()` method.
* Added a `max_depth` parameter to the `model_to_dict` function in
  the `playhouse.shortcuts` extension module.
* `SelectQuery.first()` function accepts a parameter `n` which
  applies a limit to the query and returns the first row. Previously the limit
  was not applied out of consideration for subsequent iterations, but I believe
  usage has shown that a limit is more desirable than reserving the option to
  iterate without a second query. The old behavior is preserved in the new
  `SelectQuery.peek()` method.
* `group_by()`, `order_by()`, `window()` now accept a keyward argument
  `extend`, which, when set to `True`, will append to the existing values
  rather than overwriting them.
* Query results support negative indexing.
* C sources are included now as part of the package. I *think* they should be
  able to compile for python 2 or 3, on linux or windows...but not positive.
* #895 - added the ability to query using the `<foreign_key>_id` attribute.
* #948 - added documentation about SQLite limits and how they affect
* #1009 - allow `DATABASE_URL` as a recognized parameter to the Flask config.
  `insert_many`.

[View commits](https://github.com/coleifer/peewee/compare/2.8.1...2.8.2)

## 2.8.1

This release is long overdue so apologies if you've been waiting on it and
running off master. There are numerous bugfixes contained in this release, so
I'll list those first this time.

### Bugs fixed

* #821 - issue warning if Cython is old
* #822 - better handling of MySQL connections
point for advanced use-cases.
* #313 - support equality/inequality with generic foreign key queries, and
ensure `get_or_create` works with GFKs.
* #834 - fixed Python3 incompatibilities in the `PasswordField`, thanks
@mosquito.
* #836 - fix handling of `last_insert_id()` when using `APSWDatabase`.
* #845 - add connection hooks to `APSWDatabase`.
* #852 - check SQLite library version to avoid calls to missing APIs.
* #857 - allow database definition to be deferred when using the connection
pool.
* #878 - formerly `.limit(0)` had no effect. Now adds `LIMIT 0`.
* #879 - implement a `__hash__` method for `Model`
* #886 - fix `count()` for compound select queries.
* #895 - allow writing to the `foreign_key_id` descriptor to set the foreign
key value.
* #893 - fix boolean logic bug in `model_to_dict()`.
* #904 - fix side-effect in `clean_prefetch_query`, thanks to @p.kamayev
* #907 - package includes `pskel` now.
* #852 - fix sqlite version check in BerkeleyDB backend.
* #919 - add runtime check for `sqlite3` library to match MySQL and Postgres.
Thanks @M157q

### New features

* Added a number of [SQLite user-defined functions and
aggregates](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#sqlite-udf).
* Use the DB-API2 `Binary` type for `BlobField`.
* Implemented the lucene scoring algorithm in the `sqlite_ext` Cython library.
* #825 - allow a custom base class for `ModelOptions`, providing an extension
* #830 - added `SmallIntegerField` type.
* #838 - allow using a custom descriptor class with `ManyToManyField`.
* #855 - merged change from @lez which included docs on using peewee with
Pyramid.
* #858 - allow arguments to be passed on query-string when using the `db_url`
module. Thanks @RealSalmon
* #862 - add support for `truncate table`, thanks @dev-zero for the sample
code.
* Allow the `related_name` model `Meta` option to be a callable that accepts
the foreign key field instance.


[View commits](https://github.com/coleifer/peewee/compare/2.8.0...2.8.1)

## 2.8.0

This release includes a couple new field types and greatly improved C extension support for both speedups and SQLite enhancements. Also includes some work, suggested by @foxx, to remove some places where `Proxy` was used in favor of more obvious APIs.

### New features

* [travis-ci builds](http://travis-ci.org/coleifer/peewee/builds/) now include MySQL and Python 3.5. Dropped support for Python 3.2 and 3.3. Builds also will run the C-extension code.
* C extension speedups now enabled by default, includes faster implementations for `dict` and `tuple` `QueryResultWrapper` classes, faster date formatting, and a faster field and model sorting.
* C implementations of SQLite functions is now enabled by default. SQLite extension is now compatible with APSW and can be used in standalone form directly from Python. See [SqliteExtDatabase](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#SqliteExtDatabase) for more details.
* SQLite C extension now supports `murmurhash2`.
* `UUIDField` is now supported for SQLite and MySQL, using `text` and `varchar` respectively, thanks @foxx!
* Added `BinaryField`, thanks again, @foxx!
* Added `PickledField` to `playhouse.fields`.
* `ManyToManyField` now accepts a list of primary keys when adding or removing values from the through relationship.
* Added support for SQLite [table-valued functions](http://sqlite.org/vtab.html#tabfunc2) using the [sqlite-vtfunc library](https://github.com/coleifer/sqlite-vtfunc).
* Significantly simplified the build process for compiling the C extensions.

### Backwards-incompatible changes

* Instead of using a `Proxy` for defining circular foreign key relationships, you now need to use [DeferredRelation](http://docs.peewee-orm.com/en/latest/peewee/api.html#DeferredRelation).
* Instead of using a `Proxy` for defining many-to-many through tables, you now need to use [DeferredThroughModel](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#DeferredThroughModel).
* SQLite Virtual Models must now use `Meta.extension_module` and `Meta.extension_options` to declare extension and any options. For more details, see [VirtualModel](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#VirtualModel).
* MySQL database will now issue `COMMIT` statements for `SELECT` queries. This was not necessary, but added due to an influx of confused users creating GitHub tickets. Hint: learn to user your damn database, it's not magic!

### Bugs fixed

Some of these may have been included in a previous release, but since I did not list them I'm listing them here.

* #766, fixed bug with PasswordField and Python3. Fuck Python 3.
* #768, fixed SortedFieldList and `remove_field()`. Thanks @klen!
* #771, clarified docs for APSW.
* #773, added docs for request hooks in Pyramid (who uses Pyramid, by the way?).
* #774, prefetch() only loads first ForeignKeyField for a given relation.
* #782, fixed typo in docs.
* #791, foreign keys were not correctly handling coercing to the appropriate python value.
* #792, cleaned up some CSV utils code.
* #798, cleaned up iteration protocol in QueryResultWrappers.
* #806, not really a bug, but MySQL users were clowning around and needed help.

[View commits](https://github.com/coleifer/peewee/compare/2.7.4...2.8.0)

## 2.7.4

This is another small release which adds code to automatically build the SQLite C extension if `libsqlite` is available. The release also includes:

* Support for `UUIDField` with SQLite.
* Support for registering additional database classes with the `db_url` module via `register_database`.
* `prefetch()` supports fetching multiple foreign-keys to the same model class.
* Added method to validate FTS5 search queries.

[View commits](https://github.com/coleifer/peewee/compare/2.7.3...2.7.4)

## 2.7.3

Small release which includes some changes to the BM25 sorting algorithm and the addition of a [`JSONField`](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#JSONField) for use with the new [JSON1 extension](http://sqlite.org/json1.html).

## 2.7.2

People were having trouble building the sqlite extension. I figure enough people are having trouble that I made it a separate command: `python setup.py build_sqlite_ext`.

## 2.7.1

Jacked up the setup.py

## 2.7.0

New APIs, features, and performance improvements.

### Notable changes and new features

* [`PasswordField`](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#PasswordField) that uses the `bcrypt` module.
* Added new Model [`Meta.only_save_dirty`](http://docs.peewee-orm.com/en/latest/peewee/models.html#model-options-and-table-metadata) flag to, by default, only save fields that have been modified.
* Added support for [`upsert()`](http://docs.peewee-orm.com/en/latest/peewee/api.html#InsertQuery.upsert) on MySQL (in addition to SQLite).
* Implemented SQLite ranking functions (``rank`` and ``bm25``) in Cython, and changed both the Cython and Python APIs to accept weight values for every column in the search index. This more closely aligns with the APIs provided by FTS5. In fact, made the APIs for FTS4 and FTS5 result ranking compatible.
* Major changes to the :ref:`sqlite_ext` module. Function callbacks implemented in Python were implemented in Cython (e.g. date manipulation and regex processing) and will be used if Cython is available when Peewee is installed.
* Support for the experimental new [FTS5](http://sqlite.org/fts5.html) SQLite search extension.
* Added :py:class:`SearchField` for use with the SQLite FTS extensions.
* Added :py:class:`RowIDField` for working with the special ``rowid`` column in SQLite.
* Added a model class validation hook to allow model subclasses to perform any validation after class construction. This is currently used to ensure that ``FTS5Model`` subclasses do not violate any rules required by the FTS5 virtual table.

### Bugs fixed

* **#751**, fixed some very broken behavior in the MySQL migrator code. Added more tests.
* **#718**, added a `RetryOperationalError` mixin that will try automatically reconnecting after a failed query. There was a bug in the previous error handler implementation that made this impossible, which is also fixed.

#### Small bugs

* #713, fix column name regular expression in SQLite migrator.
* #724, fixed `NULL` handling with the Postgresql `JSONField`.
* #725, added `__module__` attribute to `DoesNotExist` classes.
* #727, removed the `commit_select` logic for MySQL databases.
* #730, added documentation for `Meta.order_by` API.
* #745, added `cast()` method for casting JSON field values.
* #748, added docs and method override to indicate that SQLite does not support adding foreign key constraints after table creation.
* Check whether pysqlite or libsqlite were compiled with BerkeleyDB support when using the :py:class:`BerkeleyDatabase`.
* Clean up the options passed to SQLite virtual tables on creation.

### Small features

* #700, use sensible default if field's declared data-type is not present in the field type map.
* #707, allow model to be specified explicitly in `prefetch()`.
* #734, automatic testing against python 3.5.
* #753, added support for `upsert()` ith MySQL via the `REPLACE INTO ...` statement.
* #757, `pwiz`, the schema intropsection tool, will now generate multi-column index declarations.
* #756, `pwiz` will capture passwords using the `getpass()` function rather than via the command-line.
* Removed `Database.sql_error_handler()`, replaced with the `RetryOperationalError` mixin class.
* Documentation for `Meta.order_by` and `Meta.primary_key`.
* Better documentation around column and table constraints.
* Improved performance for some methods that are called frequently.
* Added `coerce` parameter to `BareField` and added documentation.

[View commits](https://github.com/coleifer/peewee/compare/2.6.4...2.7.0)


## 2.6.4

Updating so some of the new APIs are available on pypi.

### Bugs fixed

* #646, fixed a bug with the Cython speedups not being included in package.
* #654, documented how to create models with no primary key.
* #659, allow bare `INSERT` statements.
* #674, regarding foreign key / one-to-one relationships.
* #676, allow `ArrayField` to accept tuples in addition to lists.
* #679, fix regarding unsaved relations.
* #682, refactored QueryResultWrapper to allow multiple independent iterations over the same underlying result cache.
* #692, fix bug with multiple joins to same table + eager loading.
* #695, fix bug when connection fails while using an execution context.
* #698, use correct column names with non-standard django foreign keys.
* #706, return `datetime.time` instead of `timedelta` for MySQL time fields.
* #712, fixed SQLite migrator regular expressions. Thanks @sroebert.

### New features

* #647, #649, #650, added support for `RETURNING` clauses. Update, Insert and Delete queries can now be called with `RETURNING` to retrieve the rows that were affected. [See docs](http://docs.peewee-orm.com/en/latest/peewee/querying.html#returning-clause).
* #685, added web request hook docs.
* #691, allowed arbitrary model attributes and methods to be serialized by `model_to_dict()`. [Docs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#model_to_dict).
* #696, allow `model_to_dict()` to introspect query for which fields to serialize.
* Added backend-agnostic [truncate_date()](http://docs.peewee-orm.com/en/latest/peewee/api.html#Database.truncate_date) implementation.
* Added a `FixedCharField` which uses column type `CHAR`.
* Added support for arbitrary `PRAGMA` statements to be run on new SQLite connections. [Docs](http://docs.peewee-orm.com/en/latest/peewee/databases.html#sqlite-pragma).
* Removed `berkeley_build.sh` script. See instructions [on my blog instead](http://charlesleifer.com/blog/building-the-python-sqlite-driver-for-use-with-berkeleydb/).

[View commits](https://github.com/coleifer/peewee/compare/2.6.2...2.6.4)

## 2.6.2

Just a regular old release.

### Bugs fixed

* #641, fixed bug with exception wrapping and Python 2.6
* #634, fixed bug where correct query result wrapper was not being used for certain composite queries.
* #625, cleaned up some example code.
* #614, fixed bug with `aggregate_rows()` when there are multiple joins to the same table.

### New features

* Added [create_or_get()](http://docs.peewee-orm.com/en/latest/peewee/querying.html#create-or-get) as a companion to `get_or_create()`.
* Added support for `ON CONFLICT` clauses for `UPDATE` and `INSERT` queries. [Docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#UpdateQuery.on_conflict).
* Added a [JSONKeyStore](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#JSONKeyStore) to `playhouse.kv`.
* Added Cythonized version of `strip_parens()`, with plans to perhaps move more performance-critical code to Cython in the future.
* Added docs on specifying [vendor-specific database parameters](http://docs.peewee-orm.com/en/latest/peewee/database.html#vendor-specific-parameters).
* Added docs on specifying [field default values](http://docs.peewee-orm.com/en/latest/peewee/models.html#default-field-values) (both client and server-side).
* Added docs on [foreign key field back-references](http://docs.peewee-orm.com/en/latest/peewee/models.html#foreignkeyfield).
* Added docs for [models without a primary key](http://docs.peewee-orm.com/en/latest/peewee/models.html#models-without-a-primary-key).
* Cleaned up docs on `prefetch()` and `aggregate_rows()`.

[View commits](https://github.com/coleifer/peewee/compare/2.6.1...2.6.2)

## 2.6.1

This release contains a number of small fixes and enhancements.

### Bugs fixed

* #606, support self-referential joins with `prefetch` and `aggregate_rows()` methods.
* #588, accomodate changes in SQLite's `PRAGMA index_list()` return value.
* #607, fixed bug where `pwiz` was not passing table names to introspector.
* #591, fixed bug with handling of named cursors in older psycopg2 version.
* Removed some cruft from the `APSWDatabase` implementation.

### New features

* Added [CompressedField](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#CompressedField) and [AESEncryptedField](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#AESEncryptedField)
* #609, #610, added Django-style foreign key ID lookup. [Docs](http://docs.peewee-orm.com/en/latest/peewee/models.html#foreignkeyfield).
* Added support for [Hybrid Attributes](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#hybrid-attributes) (cool idea courtesy of SQLAlchemy).
* Added ``upsert`` keyword argument to the `Model.save()` function (SQLite only).
* #587, added support for ``ON CONFLICT`` SQLite clause for `INSERT` and `UPDATE` queries. [Docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#UpdateQuery.on_conflict)
* #601, added hook for programmatically defining table names. [Model options docs](http://docs.peewee-orm.com/en/latest/peewee/models.html#model-options-and-table-metadata)
* #581, #611, support connection pools with `playhouse.db_url.connect()`. [Docs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#connect).
* Added [Contributing section](http://docs.peewee-orm.com/en/latest/peewee/contributing.html) section to docs.

[View commits](https://github.com/coleifer/peewee/compare/2.6.0...2.6.1)

## 2.6.0

This is a tiny update, mainly consisting of a new-and-improved implementation of ``get_or_create()`` ([docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#Model.get_or_create)).

### Backwards-incompatible changes

* ``get_or_create()`` now returns a 2-tuple consisting of the model instance and a boolean indicating whether the instance was created. The function now behaves just like the Django equivalent.

### New features

* #574, better support for setting the character encoding on Postgresql database connections. Thanks @klen!
* Improved implementation of [get_or_create()](http://docs.peewee-orm.com/en/latest/peewee/api.html#Model.get_or_create).

[View commits](https://github.com/coleifer/peewee/compare/2.5.1...2.6.0)

## 2.5.1

This is a relatively small release with a few important bugfixes.

### Bugs fixed

* #566, fixed a bug regarding parentheses around compound `SELECT` queries (i.e. `UNION`, `INTERSECT`, etc).
* Fixed unreported bug where table aliases were not generated correctly for compound `SELECT` queries.
* #559, add option to preserve original column order with `pwiz`. Thanks @elgow!
* Fixed unreported bug where selecting all columns from a `ModelAlias` does not use the appropriate `FieldAlias` objects.

### New features

* #561, added an option for bulk insert queries to return the list of auto-generated primary keys. See [docs for InsertQuery.return_id_list](http://docs.peewee-orm.com/en/latest/peewee/api.html#InsertQuery.return_id_list).
* #569, added `parse` function to the `playhouse.db_url` module. Thanks @stt!
* Added [hacks](http://docs.peewee-orm.com/en/latest/peewee/hacks.html) section to the docs. Please contribute your hacks!

### Backwards-incompatible changes

* Calls to `Node.in_()` and `Node.not_in()` do not take `*args` anymore and instead take a single argument.

[View commits](https://github.com/coleifer/peewee/compare/2.5.0...2.5.1)

## 2.5.0

There are a couple new features so I thought I'd bump to 2.5.x. One change Postgres users may be happy to see is the use of `INSERT ... RETURNING` to perform inserts. This should definitely speed up inserts for Postgres, since an extra query is no longer needed to get the new auto-generated primary key.

I also added a [new context manager/decorator](http://docs.peewee-orm.com/en/latest/peewee/database.html#using-multiple-databases) that allows you to use a different database for the duration of the wrapped block.

### Bugs fixed

* #534, CSV utils was erroneously stripping the primary key from CSV data.
* #537, fix upserts when using `insert_many`.
* #541, respect `autorollback` with `PostgresqlExtDatabase`. Thanks @davidmcclure.
* #551, fix for QueryResultWrapper's implementation of the iterator protocol.
* #554, allow SQLite journal_mode to be set at run-time.
* Fixed case-sensitivity issue with `DataSet`.

### New features

* Added support for [CAST expressions](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#cast).
* Added a hook for [extending Node](http://docs.peewee-orm.com/en/latest/peewee/api.html#Node.extend) with custom methods.
* `JOIN_<type>` became `JOIN.<type>`, e.g. `.join(JOIN.LEFT_OUTER)`.
* `OP_<code>` became `OP.<code>`.
* #556, allowed using `+` and `-` prefixes to indicate ascending/descending ordering.
* #550, added [Database.initialize_connection()](http://docs.peewee-orm.com/en/latest/peewee/database.html#additional-connection-initialization) hook.
* #549, bind selected columns to a particular model. Thanks @jhorman, nice PR!
* #531, support for swapping databases at run-time via [Using](http://docs.peewee-orm.com/en/latest/peewee/database.html#using-multiple-databases).
* #530, support for SQLCipher and Python3.
* New `RowIDField` for `sqlite_ext` playhouse module. This field can be used to interact with SQLite `rowid` fields.
* Added `LateralJoin` helper to the `postgres_ext` playhouse module.
* New [example blog app](https://github.com/coleifer/peewee/tree/master/examples/blog).

[View commits](https://github.com/coleifer/peewee/compare/2.4.7...2.5.0)

## 2.4.7

### Bugs fixed

* #504, Docs updates.
* #506, Fixed regression in `aggregate_rows()`
* #510, Fixes bug in pwiz overwriting columns.
* #514, Correctly cast foreign keys in `prefetch()`.
* #515, Simplifies queries issued when doing recursive deletes.
* #516, Fix cloning of Field objects.
* #519, Aggregate rows now correctly preserves ordering of joined instances.
* Unreported, fixed bug to not leave expired connections sitting around in the pool.

### New features

* Added support for Postgresql's ``jsonb`` type with [BinaryJSONField](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#BinaryJSONField).
* Add some basic [Flask helpers](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#flask-utils).
* Add support for `UNION ALL` queries in #512
* Add `SqlCipherExtDatabase`, which combines the sqlcipher database with the sqlite extensions.
* Add option to print metadata when generating code with ``pwiz``.

[View commits](https://github.com/coleifer/peewee/compare/2.4.6...2.4.7)

## 2.4.6

This is a relatively small release with mostly bug fixes and updates to the documentation. The one new feature I'd like to highlight is the ``ManyToManyField`` ([docs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#ManyToManyField)).

### Bugs fixed

* #503, fixes behavior of `aggregate_rows()` when used with a `CompositeKey`.
* #498, fixes value coercion for field aliases.
* #492, fixes bug with pwiz and composite primary keys.
* #486, correctly handle schemas with reflection module.

### New features

* Peewee has a new [ManyToManyField](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#ManyToManyField) available in the ``playhouse.shortcuts`` module.
* Peewee now has proper support for *NOT IN* queries through the ``Node.not_in()`` method.
* Models now support iteration. This is equivalent to ``Model.select()``.

[View commits](https://github.com/coleifer/peewee/compare/2.4.5...2.4.6)

## 2.4.5

I'm excited about this release, as in addition to a number of new features and bugfixes, it also is a step towards cleaner code. I refactored the tests into a number of modules, using a standard set of base test-cases and helpers. I also introduced the `mock` library into the test suite and plan to use it for cleaner tests going forward. There's a lot of work to do to continue cleaning up the tests, but I'm feeling good about the changes. Curiously, the test suite runs faster now.

### Bugs fixed

* #471, #482 and #484, all of which had to do with how joins were handled by the `aggregate_rows()` query result wrapper.
* #472 removed some needless special-casing in `Model.save()`.
* #466 fixed case-sensitive issues with the SQLite migrator.
* #474 fixed a handful of bugs that cropped up migrating foreign keys with SQLite.
* #475 fixed the behavior of the SQLite migrator regarding auto-generated indexes.
* #479 fixed a bug in the code that stripped extra parentheses in the SQL generator.
* Fixed a handful of bugs in the APSW extension.

### New features

* Added connection abstraction called `ExecutionContext` ([see docs](http://docs.peewee-orm.com/en/latest/peewee/database.html#advanced-connection-management)).
* Made all context managers work as decorators (`atomic`, `transaction`, `savepoint`, `execution_context`).
* Added explicit methods for `IS NULL` and `IS NOT NULL` queries. The latter was actually necessary since the behavior is different from `NOT IS NULL (...)`.
* Allow disabling backref validation (#465)
* Made quite a few improvements to the documentation, particularly sections on transactions.
* Added caching to the [DataSet](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#dataset) extension, which should improve performance.
* Made the SQLite migrator smarter with regards to preserving indexes when a table copy is necessary.

[View commits](https://github.com/coleifer/peewee/compare/2.4.4...2.4.5)

## 2.4.4

Biggest news: peewee has a new logo!

![](https://media.charlesleifer.com/blog/photos/peewee-logo-bold.png)

* Small documentation updates here and there.

### Backwards-incompatible changes

* The argument signature for the `SqliteExtDatabase.aggregate()` decorator changed so that the aggregate name is the first parameter, and the number of parameters is the second parameter. If no values are specified, peewee will choose the name of the class and an un-specified number of arguments (`-1`).
* The logic for saving a model with a composite key changed slightly. Previously, if a model had a composite primary key and you called `save()`, only the dirty fields would be saved.

### Bugs fixed

* #462
* #465, add hook for disabling backref validation.
* #466, fix case-sensitive table names with migration module.
* #469, save only dirty fields.

### New features

* Lots of enhancements and cleanup to the `playhouse.apsw_ext` module.
* The `playhouse.reflection` module now supports introspecting indexes.
* Added a model option for disabling backref validation.
* Added support for the SQLite [closure table extension](http://charlesleifer.com/blog/querying-tree-structures-in-sqlite-using-python-and-the-transitive-closure-extension/).
* Added support for *virtual fields*, which act on dynamically-created virtual table fields.
* Added a new example: a virtual table implementation that exposes Redis as a relational database table.
* Added a module `playhouse.sqlite_aggregates` that contains a handful of aggregates you may find useful when developing with SQLite.


[View commits](https://github.com/coleifer/peewee/compare/2.4.3...2.4.4)

## 2.4.3

This release contains numerous improvements, particularly around the built-in database introspection utilities. Peewee should now also be compatible with PyPy.

### Bugs fixed

* #466, table names are case sensitive in the SQLite migrations module.
* #465, added option to disable backref validation.
* #462, use the schema name consistently with postgres reflection.

### New features

* New model *Meta* option to disable backref validation. [See validate_backrefs](http://docs.peewee-orm.com/en/latest/peewee/models.html#model-options-and-table-metadata).
* Added documentation on ordering by calculated values.
* Added basic PyPy compatibility.
* Added logic to close cursors after they have been exhausted.
* Structured and consolidated database metadata introspection, including improvements for introspecting indexes.
* Added support to [prefetch](http://docs.peewee-orm.com/en/latest/peewee/api.html?highlight=prefetch#prefetch) for traversing *up* the query tree.
* Added introspection option to skip invalid models while introspecting.
* Added option to limit the tables introspected.
* Added closed connection detection to the MySQL connection pool.
* Enhancements to passing options to creating virtual tables with SQLite.
* Added factory method for generating Closure tables for use with the `transitive_closure` SQLite extension.
* Added support for loading SQLite extensions.
* Numerous test-suite enhancements and new test-cases.

[View commits](https://github.com/coleifer/peewee/compare/2.4.2...2.4.3)

## 2.4.2

This release contains a number of improvements to the `reflection` and `migrate` extension modules. I also added an encrypted *diary* app to the [examples](https://github.com/coleifer/peewee/tree/master/examples) directory.

### Bugs fixed

* #449, typo in the db_url extension, thanks to @malea for the fix.
* #457 and #458, fixed documentation deficiences.

### New features

* Added support for [importing data](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#importing-data) when using the [DataSet extension](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#dataset).
* Added an encrypted diary app to the examples.
* Better index reconstruction when altering columns on SQLite databases with the [migrate](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#migrate) module.
* Support for multi-column primary keys in the [reflection](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#reflection) module.
* Close cursors more aggressively when executing SELECT queries.

[View commits](https://github.com/coleifer/peewee/compare/2.4.1...2.4.2)

## 2.4.1

This release contains a few small bugfixes.

### Bugs fixed

* #448, add hook to the connection pool for detecting closed connections.
* #229, fix join attribute detection.
* #447, fixed documentation typo.

[View commits](https://github.com/coleifer/peewee/compare/2.4.0...2.4.1)

## 2.4.0

This release contains a number of enhancements to the `playhouse` collection of extensions.

### Backwards-incompatible changes

As of 2.4.0, most of the introspection logic was moved out of the ``pwiz`` module and into ``playhouse.reflection``.

### New features

* Created a new [reflection](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#reflection) extension for introspecting databases. The *reflection* module additionally can generate actual peewee Model classes dynamically.
* Created a [dataset](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#dataset) library (based on the [SQLAlchemy project](https://dataset.readthedocs.io/) of the same name). For more info check out the blog post [announcing playhouse.dataset](http://charlesleifer.com/blog/saturday-morning-hacks-dataset-for-peewee/).
* Added a [db_url](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#database-url) module which creates `Database` objects from a connection string.
* Added [csv dump](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#dumping-csv) functionality to the [CSV utils](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#csv-utils) extension.
* Added an [atomic](http://docs.peewee-orm.com/en/latest/peewee/transactions.html#nesting-transactions) context manager to support nested transactions.
* Added support for HStore, JSON and TSVector to the `reflection` module.
* More documentation updates.

### Bugs fixed

* Fixed #440, which fixes a bug where `Model.dirty_fields` did not return an empty set for some subclasses of `QueryResultWrapper`.

[View commits](https://github.com/coleifer/peewee/compare/2.3.3...2.4.0)

## 2.3.3

This release contains a lot of improvements to the documentation and a mixed bag of other new features and bugfixes.

### Backwards-incompatible changes

As of 2.3.3, all peewee `Database` instances have a default of `True` for the `threadlocals` parameter. This means that a connection is opened for each thread. It seemed to me that by sharing connections across threads caused a lot of confusion to users who weren't aware of (or familiar with) the `threadlocals` parameter. For single-threaded apps the behavior will not be affected, but for multi-threaded applications, if you wish to share your connection across threads you must now specify `threadlocals=False`. For more information, see the [documentation](http://docs.peewee-orm.com/en/latest/peewee/api.html#Database).

I also renamed the `Model.get_id()` and `Model.set_id()` convenience methods so as not to conflict with Flask-Login. These methods should have probably been private anyways, and the new methods are named `_get_pk_value()` and `_set_pk_value()`.

### New features

* Basic support for [Postgresql full-text search](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pg-fts).
* Helper functions for converting models to dictionaries and unpacking dictionaries into model instances. See [docs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#model_to_dict).

### Bugs fixed

* Fixed #428, documentation formatting error.
* Fixed #429, which fixes the way default values are initialized for bulk inserts.
* Fixed #432, making the HStore extension optional when using `PostgresqlExtDatabase`.
* Fixed #435, allowing peewee to be used with Flask-Login.
* Fixed #436, allowing the SQLite date_part and date_trunc functions to correctly handle NULL values.
* Fixed #438, in which the ordering of clauses in a Join expression were causing unpredictable behavior when selecting related instances.
* Updated the `berkeley_build.sh` script, which was incompatible with the newest version of `bsddb3`.

[View commits](https://github.com/coleifer/peewee/compare/2.3.2...2.3.3)

## 2.3.2

This release contains mostly bugfixes.

### Changes in 2.3.2

* Fixed #421, allowing division operations to work correctly in py3k.
* Added support for custom json.dumps command, thanks to @alexlatchford.
* Fixed some foreign key generation bugs with pwiz in #426.
* Fixed a parentheses bug with UNION queries, #422.
* Added support for returning partial JSON data-structures from postgresql.

[View commits](https://github.com/coleifer/peewee/compare/2.3.1...2.3.2)

## 2.3.1

This release contains a fix for a bug introducted in 2.3.0. Table names are included, unquoted, in update queries now, which is causing some problems when the table name is a keyword.

### Changes in 2.3.1

* [Quote table name / alias](https://github.com/coleifer/peewee/issues/414)

[View commits](https://github.com/coleifer/peewee/compare/2.3.0...2.3.1)

## 2.3.0

This release contains a number of bugfixes, enhancements and a rewrite of much of the documentation.

### Changes in 2.3.0

* [New and improved documentation](http://docs.peewee-orm.com/)
* Added [aggregate_rows()](http://docs.peewee-orm.com/en/latest/peewee/querying.html#list-users-and-all-their-tweets) method for mitigating N+1 queries.
* Query compiler performance improvements and rewrite of table alias internals (51d82fcd and d8d55df04).
* Added context-managers and decorators for [counting queries](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#count_queries) and [asserting query counts](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#assert_query_count).
* Allow `UPDATE` queries to contain subqueries for values ([example](http://docs.peewee-orm.com/en/latest/peewee/querying.html#atomic-updates)).
* Support for `INSERT INTO / SELECT FROM` queries ([docs](http://docs.peewee-orm.com/en/latest/peewee/api.html?highlight=insert_from#Model.insert_from)).
* Allow `SqliteDatabase` to set the database's journal mode.
* Added method for concatenation ([docs]()).
* Moved ``UUIDField`` out of the playhouse and into peewee
* Added [pskel](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#pskel) script.
* Documentation for [BerkeleyDB](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#berkeleydb).

### Bugs fixed

* #340, allow inner query values to be used in outer query joins.
* #380, fixed foreign key handling in SQLite migrations.
* #389, mark foreign keys as dirty on assignment.
* #391, added an ``orwhere()`` method.
* #392, fixed ``order_by`` meta option inheritance bug.
* #394, fixed UUID and conversion of foreign key values (thanks @alexlatchford).
* #395, allow selecting all columns using ``SQL('*')``.
* #396, fixed query compiler bug that was adding unnecessary parentheses around expressions.
* #405, fixed behavior of ``count()`` when query has a limit or offset.

[View commits](https://github.com/coleifer/peewee/compare/2.2.5...2.3.0)

## 2.2.5

This is a small release and contains a handful of fixes.

### Changes in 2.2.5

* Added a `Window` object for creating reusable window definitions.
* Added support for `DISTINCT ON (...)`.
* Added a BerkeleyDB-backed sqlite `Database` and build script.
* Fixed how the `UUIDField` handles `None` values (thanks @alexlatchford).
* Fixed various things in the example app.
* Added 3.4 to the travis build (thanks @frewsxcv).

[View commits](https://github.com/coleifer/peewee/compare/2.2.4...2.2.5)

## 2.2.4

This release contains a complete rewrite of `pwiz` as well as some improvements to the SQLite extension, including support for the BM25 ranking algorithm for full-text searches. I also merged support for sqlcipher, an encrypted SQLite database with many thanks to @thedod!

### Changes in 2.2.4

* Rewrite of `pwiz`, schema introspection utility.
* `Model.save()` returns a value indicating the number of modified rows.
* Fixed bug with `PostgresqlDatabase.last_insert_id()` leaving a transaction open in autocommit mode (#353).
* Added BM25 ranking algorithm for full-text searches with SQLite.

[View commits](https://github.com/coleifer/peewee/compare/2.2.3...2.2.4)

## 2.2.3

This release contains a new migrations module in addition to a number of small features and bug fixes.

### Changes in 2.2.3

* New migrations module.
* Added a return value to `Model.save()` indicating number of rows affected.
* Added a `date_trunc()` method that works for Sqlite.
* Added a `Model.sqlall()` class-method to return all the SQL to generate the model / indices.

### Bugs fixed

* #342, allow functions to not coerce parameters automatically.
* #338, fixed unaliased columns when using Array and Json fields with postgres, thanks @mtwesley.
* #331, corrected issue with the way unicode arrays were adapted with psycopg2.
* #328, pwiz / mysql bug.
* #326, fixed calculation of the alias_map when using subqueries.
* #324, bug with `prefetch()` not selecting the correct primary key.


[View commits](https://github.com/coleifer/peewee/compare/2.2.2...2.2.3)


## 2.2.1

I've been looking forward to this release, as it contains a couple new features
that I've been wanting to add for some time now. Hope you find them useful.

### Changes in 2.2.1

* Window queries using ``OVER`` syntax.
* Compound query operations ``UNION``, ``INTERSECT``, ``EXCEPT`` as well as symmetric difference.

### Bugs fixed

* #300, pwiz was not correctly interpreting some foreign key constraints in SQLite.
* #298, drop table with cascade API was missing.
* #294, typo.

[View commits](https://github.com/coleifer/peewee/compare/2.2.0...2.2.1)

## 2.2.0

This release contains a large refactoring of the way SQL was generated for both
the standard query classes (`Select`, `Insert`, `Update`, `Delete`) as well as
for the DDL methods (`create_table`, `create_index`, etc). Instead of joining
strings of SQL and manually quoting things, I've created `Clause` objects
containing multiple `Node` objects to represent all parts of the query.

I also changed the way peewee determins the SQL to represent a field. Now a
field implements ``__ddl__`` and ``__ddl_column__`` methods. The former creates
the entire field definition, e.g.:

    "quoted_column_name" <result of call to __ddl_column__> [NOT NULL/PRIMARY KEY/DEFAULT NEXTVAL(...)/CONSTRAINTS...]

The latter method is responsible just for the column type definition. This might
return ``VARCHAR(255)`` or simply ``TEXT``. I've also added support for
arbitrary constraints on each field, so you might have:

    price = DecimalField(decimal_places=2, constraints=[Check('price > 0')])

### Changes in 2.2.0

* Refactored query generation for both SQL queries and DDL queries.
* Support for arbitrary column constraints.
* `autorollback` option to the `Database` class that will roll back the
  transaction before raising an exception.
* Added `JSONField` type to the `postgresql_ext` module.
* Track fields that are explicitly set, allowing faster saves (thanks @soasme).
* Allow the `FROM` clause to be an arbitrary `Node` object (#290).
* `schema` is a new `Model.Mketa` option and is used throughout the code.
* Allow indexing operation on HStore fields (thanks @zdxerr, #293).

### Bugs fixed

* #277 (where calls not chainable with update query)
* #278, use `wraps()`, thanks @lucasmarshall
* #284, call `prepared()` after `create()`, thanks @soasme.
* #286, cursor description issue with pwiz + postgres

[View commits](https://github.com/coleifer/peewee/compare/2.1.7...2.2.0)


## 2.1.7

### Changes in 2.1.7

* Support for savepoints (Sqlite, Postgresql and MySQL) using an API similar to that of transactions.
* Common set of exceptions to wrap DB-API 2 driver-specific exception classes, e.g. ``peewee.IntegrityError``.
* When pwiz cannot determine the underlying column type, display it in a comment in the generated code.
* Support for circular foreign-keys.
* Moved ``Proxy`` into peewee (previously in ``playhouse.proxy``).
* Renamed ``R()`` to ``SQL()``.
* General code cleanup, some new comments and docstrings.

### Bugs fixed

* Fixed a small bug in the way errors were handled in transaction context manager.
* #257
* #265, nest multiple calls to functions decorated with `@database.commit_on_success`.
* #266
* #267

Commits: https://github.com/coleifer/peewee/compare/2.1.6...2.1.7
Released 2013-12-25

## 2.1.6

Changes included in 2.1.6:

* [Lightweight Django integration](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#django-integration).
* Added a [csv loader](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#csv-loader) to playhouse.
* Register unicode converters per-connection instead of globally when using `pscyopg2`.
* Fix for how the related object cache is invalidated (#243).

Commits: https://github.com/coleifer/peewee/compare/2.1.5...2.1.6
Released 2013-11-19

## 2.1.5

### Summary of new features

* Rewrote the ``playhouse.postgres_ext.ServerSideCursor`` helper to work with a single query.  [Docs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#server-side-cursors).
* Added error handler hook to the database class, allowing your code to choose how to handle errors executing SQL.  [Docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#Database.sql_error_handler).
* Allow arbitrary attributes to be stored in ``Model.Meta`` a5e13bb26d6196dbd24ff228f99ff63d9c046f79.
* Support for composite primary keys (!!).  [How-to](http://docs.peewee-orm.com/en/latest/peewee/cookbook.html#composite-primary-keys) and [API docs](http://docs.peewee-orm.com/en/latest/peewee/api.html#CompositeKey).
* Added helper for generating ``CASE`` expressions.  [Docs](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#case).
* Allow the table alias to be specified as a model ``Meta`` option.
* Added ability to specify ``NOWAIT`` when issuing ``SELECT FOR UPDATE`` queries.

### Bug fixes

* #147, SQLite auto-increment behavior.
* #222
* #223, missing call to ``execute()`` in docs.
* #224, python 3 compatibility fix.
* #227, was using wrong column type for boolean with MySQL.

Commits: https://github.com/coleifer/peewee/compare/2.1.4...2.1.5
Released 2013-10-19

## 2.1.4

* Small refactor of some components used to represent expressions (mostly better names).
* Support for [Array fields](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#ArrayField) in postgresql.
* Added notes on [Proxy](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#proxy)
* Support for [Server side cursors](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#server-side-cursors) with postgresql.
* Code cleanups for more consistency.

Commits: https://github.com/coleifer/peewee/compare/2.1.3...2.1.4
Released 2013-08-05

## 2.1.3

* Added the ``sqlite_ext`` module, including support for virtual tables, full-text search, user-defined functions, collations and aggregates, as well as more granular locking.
* Manually convert data-types when doing simple aggregations - fixes issue #208
* Profiled code and dramatically increased performance of benchmarks.
* Added a proxy object for lazy database initialization - fixes issue #210

Commits: https://github.com/coleifer/peewee/compare/2.1.2...2.1.3
Released 2013-06-28

-------------------------------------

## 2.0.0

Major rewrite, see notes here: http://docs.peewee-orm.com/en/latest/peewee/upgrading.html#upgrading
