# Changelog

Tracking changes in peewee between versions.  For a complete view of all the
releases, visit GitHub:

https://github.com/coleifer/peewee/releases

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
