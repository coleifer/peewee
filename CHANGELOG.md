# Changelog

Tracking changes in peewee between versions.  For a complete view of all the
releases, visit GitHub:

https://github.com/coleifer/peewee/releases

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
