# Changelog

Tracking changes in peewee between versions.  For a complete view of all the
releases, visit GitHub:

https://github.com/coleifer/peewee/releases

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

![](http://media.charlesleifer.com/blog/photos/peewee-logo-bold.png)

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
* Created a [dataset](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#dataset) library (based on the [SQLAlchemy project](http://dataset.readthedocs.org/) of the same name). For more info check out the blog post [announcing playhouse.dataset](http://charlesleifer.com/blog/saturday-morning-hacks-dataset-for-peewee/).
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
