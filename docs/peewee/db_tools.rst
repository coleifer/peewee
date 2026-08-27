.. _db-tools:

Database Tooling
================

This section covers the playhouse modules for managing connections, database
URLs, schema migrations, introspection, code generation, and testing.

.. contents:: On this page
   :local:
   :depth: 1


.. _db-url:

Database URLs
-------------

.. module:: playhouse.db_url

The ``playhouse.db_url`` module lets you configure Peewee from a connection
string, which is common in twelve-factor applications where database
credentials live in environment variables.

.. code-block:: python

   import os
   from playhouse.db_url import connect

   db = connect(os.environ.get('DATABASE_URL', 'sqlite:///default.db'))

Pass additional keyword arguments in the query string:

.. code-block:: python

   db = connect('postgres://user:pass@host/db?max_connections=20')

URL format: ``scheme://user:password@host:port/dbname?option=value``

Common schemes:

+------------------------+------------------------------------------+
| Scheme                 | Database class                           |
+========================+==========================================+
| ``sqlite:///path``     | :class:`SqliteDatabase`                  |
+------------------------+------------------------------------------+
| ``postgres://``        | :class:`PostgresqlDatabase`              |
+------------------------+------------------------------------------+
| ``postgresext://``     | :class:`.PostgresqlExtDatabase`          |
+------------------------+------------------------------------------+
| ``mysql://``           | :class:`MySQLDatabase`                   |
+------------------------+------------------------------------------+

Connection pool implementations:

+-----------------------------+------------------------------------------+
| Scheme                      | Database class                           |
+=============================+==========================================+
| ``sqlite+pool:///path``     | :class:`.PooledSqliteDatabase`           |
+-----------------------------+------------------------------------------+
| ``postgres+pool://``        | :class:`.PooledPostgresqlDatabase`       |
+-----------------------------+------------------------------------------+
| ``postgresext+pool://``     | :class:`.PooledPostgresqlExtDatabase`    |
+-----------------------------+------------------------------------------+
| ``mysql+pool://``           | :class:`.PooledMySQLDatabase`            |
+-----------------------------+------------------------------------------+

Alternate drivers:

+------------------------------+------------------------------------------+
| Scheme                       | Database class                           |
+==============================+==========================================+
| ``psycopg3://``              | :class:`.Psycopg3Database`               |
+------------------------------+------------------------------------------+
| ``psycopg3+pool://``         | :class:`.PooledPsycopg3Database`         |
+------------------------------+------------------------------------------+
| ``cockroachdb://``           | :class:`.CockroachDatabase`              |
+------------------------------+------------------------------------------+
| ``cockroachdb+pool://``      | :class:`.PooledCockroachDatabase`        |
+------------------------------+------------------------------------------+
| ``cysqlite://``              | :class:`.CySqliteDatabase`               |
+------------------------------+------------------------------------------+
| ``cysqlite+pool://``         | :class:`.PooledCySqliteDatabase`         |
+------------------------------+------------------------------------------+
| ``apsw://``                  | :class:`.APSWDatabase`                   |
+------------------------------+------------------------------------------+
| ``mariadbconnector://``      | :class:`.MariaDBConnectorDatabase`       |
+------------------------------+------------------------------------------+
| ``mariadbconnector+pool://`` | :class:`.PooledMariaDBConnectorDatabase` |
+------------------------------+------------------------------------------+
| ``mysqlconnector://``        | :class:`.MySQLConnectorDatabase`         |
+------------------------------+------------------------------------------+
| ``mysqlconnector+pool://``   | :class:`.PooledMySQLConnectorDatabase`   |
+------------------------------+------------------------------------------+


.. function:: connect(url, unquote_password=False, unquote_user=False, **connect_params)

   :param url: the URL for the database, see examples.
   :param bool unquote_password: unquote special characters in the password.
   :param bool unquote_user: unquote special characters in the user.
   :param connect_params: additional parameters to pass to the Database.

   Parse ``url`` and return an appropriate :class:`Database` instance. A
   URL without a database name raises ``ValueError``.

   Examples:

   * ``sqlite:///my_app.db`` - SQLite file in the current directory.
   * ``sqlite:///:memory:`` - in-memory SQLite.
   * ``sqlite:////absolute/path/to/app.db`` - absolute path SQLite.
   * ``postgresql:///dbname`` - database running locally.
   * ``postgresql://user:password@host:5432/dbname``
   * ``mysql://user:password@host:3306/dbname``

.. function:: parse(url, unquote_password=False, unquote_user=False)

   :param url: the URL for the database, see :func:`connect` above for examples.
   :param bool unquote_password: unquote special characters in the password.
   :param bool unquote_user: unquote special characters in the user.

   Parse a URL and return a dictionary with ``database``, ``host``,
   ``port``, ``user``, and ``password`` keys plus any extra connect
   parameters from the query string.

   Useful if you need to construct a database class manually:

   .. code-block:: python

       params = parse('postgres://user:pass@host:5432/mydb')
       db = MyCustomDatabase(**params)

.. function:: register_database(db_class, *names)

   :param db_class: A subclass of :class:`Database`.
   :param names: A list of names to use as the scheme in the URL.

   Register a custom database class under one or more URL scheme names so
   that :func:`connect` can instantiate it:

   .. code-block:: python

       register_database(ClickHouseDatabase, 'clickhouse')
       db = connect('clickhouse:///my-db')


.. _pool:

Connection Pooling
------------------

.. module:: playhouse.pool

The ``playhouse.pool`` module contains a number of :class:`Database` classes
that provide transparent connection pooling for peewee databases. The pool
works by overriding the methods on the :class:`Database` class that open and
close connections to the backend, and works as a drop-in replacement.

In multi-threaded or web applications, each thread gets its own connection. The
pool maintains up to ``max_connections`` open connections at any time. The
application only needs to ensure that connections are *closed* when work is
done (typically at the end of an HTTP request), so the connection can be
returned to the pool. Closing a pooled connection returns it to the pool rather
than actually disconnecting.

.. code-block:: python

   from playhouse.pool import PooledPostgresqlDatabase

   db = PooledPostgresqlDatabase(
       'my_app',
       user='postgres',
       max_connections=32,
       stale_timeout=300)

.. tip::
   Pooled database implementations may be safely used as drop-in replacements
   for their non-pooled counterparts.

.. include:: pool-snippet.rst

.. note::
   Applications using Peewee's :ref:`asyncio integration <pwasyncio>` do not need to
   use a special pooled database. Async databases use a connection pool by
   default.

.. class:: PooledDatabase(database, max_connections=20, stale_timeout=None, timeout=None, **kwargs)

   Common mixin class used for specific backend implementations.

   :param str database: The name of the database or database file.
   :param int max_connections: Maximum number of concurrent connections.
       Pass ``None`` for no limit.
   :param int stale_timeout: Seconds after which an idle connection is
       considered stale and will be discarded next time it would be reused.
   :param int timeout: Seconds to block when all connections are in use.
       ``0`` blocks indefinitely, ``None`` (default) raises immediately.

   Connections will not be closed exactly when they exceed their
   ``stale_timeout``. Instead, stale connections are only closed when a new
   connection is requested.

   If the pool is exhausted and no ``timeout`` is configured, a
   ``MaxConnectionsExceeded`` is raised.

   .. method:: manual_close()

      Close the current connection permanently without returning it to the
      pool. Use this when a connection has entered a bad state.

   .. method:: close_idle()

      Close all pooled connections that are not currently in use.

   .. method:: close_stale(age=600)

      :param int age: Age at which a connection should be considered stale.
      :returns: Number of connections closed.

      Close in-use connections that have exceeded ``age`` seconds.
      Use with caution.

   .. method:: close_all()

      Close all connections including those currently in use.
      Use with caution.

.. class:: PooledSqliteDatabase(database, max_connections=20, stale_timeout=None, timeout=None, **kwargs)

   Pool implementation for SQLite databases. Extends :class:`SqliteDatabase`.

.. class:: PooledPostgresqlDatabase(database, max_connections=20, stale_timeout=None, timeout=None, **kwargs)

   Pool implementation for Postgresql databases. Extends :class:`PostgresqlDatabase`.

.. class:: PooledMySQLDatabase(database, max_connections=20, stale_timeout=None, timeout=None, **kwargs)

   Pool implementation for MySQL / MariaDB databases. Extends :class:`MySQLDatabase`.

Additional implementations exist for:

* :class:`~playhouse.postgres_ext.PooledPostgresqlExtDatabase`
* :class:`~playhouse.postgres_ext.PooledPsycopg3Database`
* :class:`~playhouse.mysql_ext.PooledMySQLConnectorDatabase`
* :class:`~playhouse.mysql_ext.PooledMariaDBConnectorDatabase`
* :class:`~playhouse.cysqlite_ext.PooledCySqliteDatabase`
* :class:`~playhouse.cockroachdb.PooledCockroachDatabase`


.. _migrate:

Schema Migrations
-----------------

.. module:: playhouse.migrate

The ``playhouse.migrate`` module provides a lightweight API for making
incremental schema changes to an existing database without writing raw SQL.

The peewee migration philosophy is that tools relying on database
introspection, versioning, and auto-detection are often brittle and
complex. Migrations can be written as simple python scripts and executed from
the command-line. The :ref:`runner <migration-runner>` below adds bookkeeping
and can be used for migration generation and execution.

Supported schema-altering operations:

- Add, rename, or drop columns.
- Make columns nullable or not nullable.
- Change a column's type or server-side default.
- Rename or drop a table.
- Add or drop indexes and constraints.

.. seealso:: :ref:`schema`

.. code-block:: python

   from playhouse.migrate import SchemaMigrator, migrate

   migrator = SchemaMigrator.from_database(db)

   with db.atomic():
       migrate(
           migrator.add_column('tweet', 'is_published', BooleanField(default=True)),
           migrator.add_column('user', 'email', CharField(null=True)),
           migrator.drop_column('user', 'old_bio'),
       )

.. tip::
   Wrap migrations in :meth:`SchemaMigrator.migration_context` to ensure
   changes are not partially applied when transactional DDL is available
   (SQLite and Postgres). It also temporarily disables the SQLite
   foreign-keys pragma, so table rebuilds (required for some operations)
   do not destroy rows via ``ON DELETE CASCADE``.

Operations
^^^^^^^^^^

**Add columns:**

.. code-block:: python

   # Non-null fields must supply a default value.
   migrate(
       migrator.add_column('comment', 'pub_date', DateTimeField(null=True)),
       migrator.add_column('comment', 'body', TextField(default='')),
   )

**Add a foreign key** (the column name must include the ``_id`` suffix that
Peewee appends by default):

.. code-block:: python

   user_fk = ForeignKeyField(User, field=User.id, null=True)
   migrate(
       migrator.add_column('tweet', 'user_id', user_fk),
   )

**Rename a column:**

.. code-block:: python

   migrate(
       migrator.rename_column('story', 'pub_date', 'publish_date'),
       migrator.rename_column('story', 'mod_date', 'modified_date'),
   )

**Drop a column:**

.. code-block:: python

   migrate(migrator.drop_column('story', 'old_field'))

**Nullable / not nullable:**

.. code-block:: python

   migrate(
       migrator.drop_not_null('story', 'pub_date'),  # Allow NULLs.
       migrator.add_not_null('story', 'modified_date'),  # Disallow NULLs.
   )

**Change type:**

.. code-block:: python

   # Change a VARCHAR(...) to a TEXT field.
   migrate(migrator.alter_column_type('person', 'email', TextField()))

**Rename table:**

.. code-block:: python

   migrate(migrator.rename_table('story', 'stories'))

**Drop table:**

.. code-block:: python

   migrate(migrator.drop_table('story', safe=True))

**Add / drop indexes:**

.. code-block:: python

   # Specify table, column(s), and unique/non-unique.
   migrate(
       # Create an index on the `pub_date` column.
       migrator.add_index('story', ('pub_date',), False),

       # Create a unique index on the category and title fields.
       migrator.add_index('story', ('category_id', 'title'), True),

       # Drop the pub-date + status index.
       migrator.drop_index('story', 'story_pub_date_status'),
   )

   # Only index published stories (sqlite and postgres).
   story = Table('story')
   migrate(migrator.add_index('story', ('pub_date',), False,
                              where=(story.c.status == 'published')))

   # Unique index treating NULLs as equal (postgres 15+).
   migrate(migrator.add_index('story', ('external_id',), True,
                              nulls_distinct=False))

**Add / drop constraints:**

.. code-block:: python

   from peewee import Check

   # Add a CHECK() constraint to enforce the price cannot be negative.
   migrate(migrator.add_constraint(
       'products',
       'price_check',
       Check('price >= 0')))

   # Remove the price check constraint.
   migrate(migrator.drop_constraint('products', 'price_check'))

   # Add a UNIQUE constraint on the first and last names.
   migrate(migrator.add_unique('person', 'first_name', 'last_name'))

**Column defaults:**

.. code-block:: python

   # Add a default value:
   migrate(migrator.add_column_default('entry', 'status', 'draft'))

   # Use a function expression (not supported in SQLite):
   migrate(migrator.add_column_default('entry', 'created_at', fn.NOW()))

   # SQLite-compatible function syntax:
   migrate(migrator.add_column_default(
       'entry',
       'created_at',
       "(datetime('now'))"))

   # Remove a default:
   migrate(migrator.drop_column_default('entry', 'status'))

**Raw SQL:**

.. code-block:: python

   # Interleave data fixes with schema changes in a single plan.
   migrate(
       migrator.add_column('entry', 'score', IntegerField(null=True)),
       migrator.sql('UPDATE entry SET score = %s', (0,)),
       migrator.add_not_null('entry', 'score'),
   )

``params`` are bound by the database driver, so the placeholder is the
driver's own: ``%s`` for postgres and mysql, ``?`` for sqlite.

.. note::
   Pass the schema to the migrator when the tables are not in the default
   schema.

   .. code-block:: python

      migrator = PostgresqlMigrator(db, schema='my_schema')
      migrate(
          migrator.add_column('table', 'field', TextField(default='')),
      )

Migration API
^^^^^^^^^^^^^

.. function:: migrate(*operations)

   Execute one or more schema-altering operations.

   Usage:

   .. code-block:: python

       migrate(
           migrator.add_column('t', 'col', CharField(default='')),
           migrator.add_index('t', ('col',), False),
       )

.. class:: SchemaMigrator(database, schema=None)

   :param database: a :class:`Database` instance.
   :param str schema: schema containing the tables to be migrated.

   The :class:`SchemaMigrator` is responsible for generating schema-altering
   statements.

   .. classmethod:: from_database(database, schema=None)

      :param Database database: database instance to generate migrations for.
      :param str schema: schema containing the tables to be migrated.
      :return: :class:`SchemaMigrator` instance appropriate to provided database.

      Factory method that returns the appropriate :class:`SchemaMigrator`
      subclass for the given database.

   .. method:: migrate(*operations)

      Execute one or more schema-altering operations. Equivalent to the
      module-level :py:func:`migrate` helper.

   .. method:: migration_context(atomic=True)

      Context manager wrapping a migration run in the appropriate
      per-dialect safety: a transaction when the database supports
      transactional DDL (and ``atomic`` is true), and on sqlite the
      ``foreign_keys`` pragma is additionally disabled for the duration,
      as table-rewrites would otherwise fire ``ON DELETE CASCADE``.

   .. method:: add_column(table, column_name, field, allow_not_null=False)

      :param str table: Name of the table to add column to.
      :param str column_name: Name of the new column.
      :param Field field: A :class:`Field` instance.
      :param bool allow_not_null: Emit the column definition as-is, skipping
          the add-nullable-then-backfill sequence described below.

      Add a new column to the provided table. The ``field`` provided will be used
      to generate the appropriate column definition.

      If the field is not nullable it must specify a default value, unless
      ``allow_not_null`` is set.

      .. note::
         For non-null columns, the following occurs:

         1. column is added as allowing NULLs
         2. ``UPDATE`` query is executed to populate the default value
         3. column is changed to NOT NULL

         With ``allow_not_null=True`` the column is added ``NOT NULL`` in a
         single statement and no default is required. Existing rows are the
         caller's responsibility: postgres and sqlite refuse to add the
         column, while MySQL backfills its implicit default.

   .. method:: drop_column(table, column_name, cascade=True)

      :param str table: Name of the table to drop column from.
      :param str column_name: Name of the column to drop.
      :param bool cascade: Whether the column should be dropped with `CASCADE`.

   .. method:: rename_column(table, old_name, new_name)

      :param str table: Name of the table containing column to rename.
      :param str old_name: Current name of the column.
      :param str new_name: New name for the column.

   .. method:: add_not_null(table, column)

      :param str table: Name of table containing column.
      :param str column: Name of the column to make not nullable.

   .. method:: drop_not_null(table, column)

      :param str table: Name of table containing column.
      :param str column: Name of the column to make nullable.

   .. method:: add_column_default(table, column, default)

      :param str table: Name of table containing column.
      :param str column: Name of the column to add default to.
      :param default: New default value for column. See notes below.

      Peewee attempts to properly quote the default if it appears to be a
      string literal. Otherwise the default will be treated literally.
      Postgres and MySQL support specifying the default as a peewee
      expression, e.g. ``fn.NOW()``, but Sqlite users will need to use
      ``"(datetime('now'))"`` instead.

   .. method:: drop_column_default(table, column)

      :param str table: Name of table containing column.
      :param str column: Name of the column to remove default from.

   .. method:: alter_column_type(table, column, field, cast=None)

      :param str table: Name of the table.
      :param str column: Name of the column to modify.
      :param Field field: :class:`Field` instance representing new
          data type.
      :param cast: (postgres-only) specify a cast expression if the
          data-types are incompatible, e.g. ``column_name::int``. Can be
          provided as either a string or a :class:`Cast` instance.

      Alter the data-type of a column. This method should be used with care,
      as using incompatible types may not be well-supported by your database.

   .. method:: rename_table(old_name, new_name)

      :param str old_name: Current name of the table.
      :param str new_name: New name for the table.

   .. method:: drop_table(table, safe=False, cascade=False, schema=None)

      :param str table: Name of the table to drop.
      :param bool safe: Use ``IF EXISTS``.
      :param bool cascade: Append ``CASCADE`` (not supported by sqlite).
      :param str schema: Schema to drop the table from, overriding the
          migrator's own schema.

   .. method:: add_index(table, columns, unique=False, using=None, where=None, nulls_distinct=None)

      :param str table: Name of table on which to create the index.
      :param list columns: List of columns which should be indexed.
      :param bool unique: Whether the new index should specify a unique constraint.
      :param str using: Index type (where supported), e.g. GiST or GIN.
      :param where: Expression for a partial index (sqlite and postgres).
      :param bool nulls_distinct: For unique indexes, whether NULL values
          are treated as distinct (postgres 15+).

   .. method:: drop_index(table, index_name)

      :param str table: Name of the table containing the index to be dropped.
      :param str index_name: Name of the index to be dropped.

   .. method:: sql(sql, params=None)

      Raw SQL as an operation, letting data fixes interleave with schema
      changes in a single ``migrate()`` call.

   .. method:: add_constraint(table, name, constraint)

      :param str table: Table to add constraint to.
      :param str name: Name used to identify the constraint.
      :param constraint: either a :func:`Check` constraint or for
          adding an arbitrary constraint use :class:`SQL`.

   .. method:: drop_constraint(table, name)

      :param str table: Table to drop constraint from.
      :param str name: Name of constraint to drop.

   .. method:: add_unique(table, *column_names)

      :param str table: Table to add constraint to.
      :param str column_names: One or more columns for UNIQUE constraint.

.. class:: PostgresqlMigrator(database, schema=None)

   .. method:: set_search_path(schema_name)

      Set the Postgres search path for subsequent operations. The search path
      belongs to the connection and is lost when it is closed, so prefer the
      migrator's ``schema`` parameter.

.. class:: SqliteMigrator(database)

   SQLite supports or emulates most schema-altering operations, but the code
   path is dependent on the library version.

   SQLite 3.53.0 added ``ALTER TABLE`` support for table constraints, so
   ``add_constraint`` and ``drop_constraint`` work on 3.53 and newer.
   Older versions raise ``NotImplementedError``. ``add_unique`` is not
   supported on any version, as sqlite's ``ADD CONSTRAINT`` does not
   extend to UNIQUE constraints.

   SQLite is the one backend that does not accept a ``schema``, as the
   table-rebuild path rewrites unqualified DDL read out of ``sqlite_master``.
   ``drop_table()`` still takes one, for attached databases.

.. class:: MySQLMigrator(database, schema=None)

   MySQL-specific subclass. A schema is a database in MySQL, so ``schema`` is
   the database to migrate. Note that ``rename_table()`` keeps the table in
   that database, where a plain ``RENAME TABLE a.t TO u`` would move it to the
   connection's own.


.. _migration-runner:

Migration Runner
----------------

.. module:: playhouse.migrations

The ``playhouse.migrations`` module is a migration runner built using the
:ref:`migration tooling <migrate>`. The runner records which scripts have been
applied and runs pending migrations in order. The CLI is installed as
``pwmigrate`` (or use ``python -m playhouse.migrations``).

The following commands are available:

* ``initial``: create an initial migration containing a snapshot of the
  application models.
* ``create``: create a bare skeleton migration file.
* ``generate``: generate a migration based on changes detected between the
  database schema and model definitions.
* ``diff``: display differences between the database schema and model
  definitions.
* ``up``: apply any pending migrations.
* ``down``: roll back one or more applied migrations.
* ``fake``: record pending migrations as applied without running them.
* ``status``: show which migrations have been applied and which are pending.

The following sections show basic usage for common scenarios.

New application
^^^^^^^^^^^^^^^

Given a models module:

.. code-block:: python

   # models.py, imported as `app.models` in examples.
   from peewee import *

   database = SqliteDatabase('app.db')

   class User(database.Model):
       username = CharField(unique=True)
       email = CharField()

Store the project defaults in a ``.pwmigrate`` file in the project root
(see :ref:`pwmigrate-config-file`), so commands need no arguments:

.. code-block:: ini

   # .pwmigrate
   database = app.models.database
   models = app.models
   # directory = migrations/
   # table = schema_migration

Then generate the initial migration. ``initial`` reads the models and creates a
migration suitable for running on an empty database:

.. code-block:: console

   $ pwmigrate initial
   migrations/0001_initial.py

Equivalent to above, passing the database URL and models module explicitly:

.. code-block:: console

   $ pwmigrate sqlite:///app.db initial app.models
   migrations/0001_initial.py

The generated file is a python script. The model being created is recorded here
as a frozen copy so that future changes to the application code do not affect
the migration.

.. code-block:: python

   # Generated from a schema diff on 2026-08-02 21:28.
   from peewee import *

   def up(migrator, db):
       class User(Model):
           username = CharField(unique=True)
           email = CharField()
           class Meta:
               database = db
               table_name = 'user'
       db.create_tables([User])


   def down(migrator, db):
       migrator.migrate(migrator.drop_table('user'))

Apply it using ``up``:

.. code-block:: console

   $ pwmigrate up
   applied: 0001_initial

Applying a migration runs its script and records the name in a
``schema_migration`` table in the database.

Existing database
^^^^^^^^^^^^^^^^^

To get started with an existing database schema, generate an ``initial``
migration that captures the current state. Then ``fake`` the initial migration.
We fake it instead of actually running it, since the schema already exists.
The ``fake`` command will record the initial migration as having been run:

.. code-block:: console

   $ pwmigrate app.models.database initial app.models
   migrations/0001_initial.py

   $ pwmigrate app.models.database fake  # Fake it against real database.
   faked: 0001_initial

Now the migrations and schema are in agreement. Creating an initial migration
is always a good idea, as it allows you to re-create your entire schema on a
fresh database using ``pwmigrate``.

We can apply the above initial migration to stand up a test SQLite database,
for example:

.. code-block:: console

   $ pwmigrate sqlite:///testing.db up
   applied: 0001_initial

.. tip::
   If model class definitions do not exist yet, they can be generated
   with :ref:`pwiz <pwiz>`:

   .. code-block:: console

      $ pwiz -e postgresql -u postgres my_db > app/models.py

Making changes
^^^^^^^^^^^^^^

In this example we'll add a field to our model class:

.. code-block:: python

   class User(database.Model):
       username = CharField(unique=True)
       email = CharField()
       karma = IntegerField(default=0)  # This field is new.

Then we can run two commands to verify the change was picked up and generate a
migration:

1. ``diff`` shows any changes that were identified.
2. ``generate`` writes the new migration.

Both commands read the database and models module from the ``.pwmigrate``
file set up earlier (see :ref:`pwmigrate-config-file`).

.. code-block:: console

   # Prints a list of differences between code and database schema.
   $ pwmigrate diff
   add column user.karma

   # Generates a migration.
   $ pwmigrate generate add_karma
   migrations/0002_add_karma.py

The generated ``up()`` adds the column:

.. code-block:: python

   def up(migrator, db):
       migrator.migrate(migrator.add_column('user', 'karma', IntegerField(default=0)))


   def down(migrator, db):
       migrator.migrate(migrator.drop_column('user', 'karma'))

Peewee's migration will populate ``default=`` for basic value types (``str``,
``int``, ``float``, ``bool``), for ``decimal.Decimal`` values, and for the
common callables ``datetime.datetime.now`` and ``utcnow``,
``datetime.date.today``, ``time.time``, ``time.time_ns``, ``uuid.uuid4``,
``dict`` and ``list``, adding any needed import. An ``enum`` member renders
as its value. Anything else will be marked with a TODO comment at the top
of the migration script.

The differ matches columns by name, so a renamed field diffs as an add
plus a drop. When the data must survive, replace the generated pair with
a ``rename_column()`` operation.

Run the migration:

.. code-block:: console

   $ pwmigrate up
   applied: 0002_add_karma
   $ pwmigrate status
   [x] 0001_initial  2026-08-04 09:49:33
   [x] 0002_add_karma  2026-08-04 09:49:33

Deployments run ``pwmigrate <db> up``, or call ``run(db)`` from the
application's startup code. :ref:`schema-diff` describes what
generation covers.

Migration files
^^^^^^^^^^^^^^^

Peewee migrations are python files with a numeric prefix, defining
``up(migrator, db)`` and, optionally, ``down(migrator, db)``. The
``migrator`` is a :ref:`SchemaMigrator <migrate>` bound to the connected
database and ``db`` is the :class:`Database`, so inline models can
subclass ``db.Model``.

For anything the differ cannot write, such as a data migration, scaffold
the next numbered file with ``create`` and fill in the body:

.. code-block:: console

   $ pwmigrate create create_notes
   migrations/0003_create_notes.py

.. code-block:: python

   # migrations/0003_create_notes.py
   from peewee import *

   def up(migrator, db):
       class User(db.Model):  # Stub for the FK target.
           pass

       class Note(db.Model):  # Copy model definition to decouple from app code.
           user = ForeignKeyField(User)
           content = TextField()

       db.create_tables([Note])

   def down(migrator, db):
       migrator.migrate(migrator.drop_table('note'))

Data migrations are plain python between (or instead of) schema
operations.

Generated files have the same shape. Treat one as a starting point, not
a finished migration. Anything the differ cannot express is flagged with
a TODO comment:

.. code-block:: python

   # Generated from a schema diff on 2026-08-03 16:17.
   from peewee import *

   # TODO: user.email: dropped column cannot be restored by down()

   def up(migrator, db):
       class User(Model):
           class Meta:
               database = db
               table_name = 'user'

       class Note(Model):
           user = ForeignKeyField(User)
           content = TextField()
           class Meta:
               database = db
               table_name = 'note'
       db.create_tables([Note])

       migrator.migrate(migrator.add_column('user', 'karma', IntegerField(default=0)))
       migrator.migrate(migrator.add_index('tweet', ('user_id', 'flags')))
       migrator.migrate(migrator.drop_column('user', 'email'))


   def down(migrator, db):
       migrator.migrate(migrator.drop_index('tweet', 'tweet_user_id_flags'))
       migrator.migrate(migrator.drop_column('user', 'karma'))
       migrator.migrate(migrator.drop_table('note'))

Command line
^^^^^^^^^^^^

Example usage:

.. code-block:: shell

   # Generate the first migration from the models, assuming an empty db:
   pwmigrate app.settings.db initial app.models

   # Fake the initial migration (if models pre-date peewee migrations).
   pwmigrate app.settings.db fake

   # Or, run the initial migration if starting from a clean db.
   pwmigrate app.settings.db up

   # List migrations and when each was applied:
   pwmigrate app.settings.db status

   # Write a skeleton migration, or generate it from the model diff:
   pwmigrate app.settings.db create "add karma"
   pwmigrate app.settings.db generate "add karma" app.models

   # Apply pending migrations, all or up through a target:
   pwmigrate app.settings.db up
   pwmigrate app.settings.db up 0002_add_karma

   # Revert the most recent migration, or back through a target:
   pwmigrate app.settings.db down
   pwmigrate app.settings.db down 0002_add_karma

   # Print schema drift against the models:
   pwmigrate app.settings.db diff app.models

   # Record all pending migrations as applied without running them:
   pwmigrate app.settings.db fake

The database is given as:

* dotted path to a :class:`Database` instance
* :ref:`db_url <db-url>` string
* a path to a sqlite database file

Models are given as a dotted module path. Every model defined in the
module is used (field-less base classes are skipped and reported).
Models imported into the module from elsewhere are ignored, so a package
that only re-exports its models needs the explicit-list form,
``app.models:MODELS``.

.. _pwmigrate-config-file:

pwmigrate config file
^^^^^^^^^^^^^^^^^^^^^

Keep a ``.pwmigrate`` file at the project root, committed with the
application code. It supplies per-project defaults as ``key = value``
lines:

.. code-block:: ini

   database = app.settings.db
   models = app.models
   # directory = migrations/
   # table = schema_migration

This allows us to run migration commands without explicitly specifying the
paths each time:

.. code-block:: console

   $ pwmigrate diff
   $ pwmigrate generate "add some fields"
   $ pwmigrate status
   $ pwmigrate up

Recognized keys:

* ``database`` - database spec (dotted path, url, or sqlite filename)
* ``directory`` - migrations directory
* ``models`` - models module, read by ``diff``, ``initial`` and ``generate``
* ``table`` - history table name

The file is read from the working directory only. A different config
file is named with ``-c``. Unrecognized keys warn on stderr. Arguments
passed on the command line override any settings in the config file.

Commands
^^^^^^^^

+--------------+------------------------------------------------------------+
| Command      | Meaning                                                    |
+==============+============================================================+
| ``status``   | List migrations and applied timestamps.                    |
+--------------+------------------------------------------------------------+
| ``up``       | Apply pending migrations in order, stopping after          |
|              | ``target`` when given.                                     |
+--------------+------------------------------------------------------------+
| ``down``     | Revert the most recent migration, or everything back       |
|              | through ``target``, newest first.                          |
+--------------+------------------------------------------------------------+
| ``initial``  | Generate the first migration from the models, assuming an  |
|              | empty database.                                            |
+--------------+------------------------------------------------------------+
| ``create``   | Write a skeleton migration file.                           |
+--------------+------------------------------------------------------------+
| ``generate`` | Generate a migration from the schema diff.                 |
+--------------+------------------------------------------------------------+
| ``fake``     | Record pending migrations as applied without running them, |
|              | stopping after ``target`` when given.                      |
+--------------+------------------------------------------------------------+
| ``diff``     | Print schema differences against a models module.          |
+--------------+------------------------------------------------------------+

Command-line options:

+--------+---------------------------------------------------+--------------------+
| Option | Meaning                                           | Example            |
+========+===================================================+====================+
| ``-d`` | Migrations directory (default ``migrations``)     | ``-d db/schema``   |
+--------+---------------------------------------------------+--------------------+
| ``-t`` | History table name (default ``schema_migration``) |                    |
+--------+---------------------------------------------------+--------------------+
| ``-v`` | Echo SQL as it executes                           |                    |
+--------+---------------------------------------------------+--------------------+
| ``-c`` | Config file supplying defaults                    | ``-c pw.conf``     |
+--------+---------------------------------------------------+--------------------+

``status`` exits 0 when the database is current and 1 when migrations
are pending, so it can gate a deploy. Validation and database errors
exit 2.

Behavior:

* Files apply in numeric order (the prefix is parsed as an integer, so
  ``2_x.py`` runs before ``10_y.py``). Applied names are recorded in a
  history table (default ``schema_migration``), exposed as a model at
  ``runner.History``. The history is a set, so migrations merged in from
  a branch are applied even when their numbers are not the highest.
* On Postgres and SQLite, each migration and its history row are wrapped
  in a single transaction, so a failure rolls back cleanly. MySQL DDL
  commits implicitly, so the history row is written only after every operation
  succeeds. Set ``atomic = False`` at module level to opt a migration out of
  transaction wrapping (e.g. for ``CREATE INDEX CONCURRENTLY``).
* On SQLite, ``foreign_keys`` pragma is turned off for the duration of each
  migration and restored afterwards to prevent ``ON DELETE CASCADE`` being
  triggered during table rebuilds (required for some operations).
* A migration that does not define ``down()`` cannot be reverted (there
  is no requirement to write one).

Python interface
^^^^^^^^^^^^^^^^

All migration-runner operations are available programmatically:

.. code-block:: python

   from playhouse.migrations import Runner

   runner = Runner(db, directory='migrations')
   runner.create('add karma')  # Write a skeleton file.
   runner.status()             # [Migration(idx, name, path, applied), ...]
   runner.up()                 # Apply everything pending, in order.
   runner.up('0004_x')         # Apply pending up through 0004_x.
   runner.down()               # Revert the most recent applied migration.
   runner.down('0004_x')       # Revert back through 0004_x, inclusive.
   runner.fake()               # Record all as applied without running.

``run(db)`` is shorthand for ``Runner(db, 'migrations').up()``.

Generate a migration from a diff:

.. code-block:: python

   from playhouse.migrations import Runner, template
   from playhouse.schema_diff import diff_models

   runner = Runner(db)
   diff = diff_models(db, [User, Tweet, Note])
   if diff:
       runner.create('add karma', body=template(diff))

.. class:: Runner(database, directory='migrations', table_name='schema_migration')

   .. method:: up(target=None)

      Apply all pending migrations in order, stopping after ``target`` if
      given. Returns the applied names.

   .. method:: down(target=None)

      Revert the most recent applied migration, or, given a target, every
      applied migration back through the target (newest first). Returns
      the reverted names.

   .. method:: status()

      Return ``Migration`` namedtuples ``(idx, name, path, applied)``
      merging migration files with history rows, in numeric order.
      ``applied`` is None when pending, ``path`` is None when the file
      is missing.

   .. method:: fake(target=None)

      Record pending migrations as applied without running them, stopping
      after ``target`` if given. Returns the recorded names.

   .. method:: create(name, body=None)

      Write a numbered migration file (a skeleton, unless ``body`` is
      given) and return its path.

   .. attribute:: History

      The history-table model, for manual bookkeeping repair.

.. function:: run(database, directory='migrations', **kwargs)

   Apply pending migrations. Shorthand for ``Runner(database, directory).up()``.

.. function:: template(diff)

   Render a :class:`playhouse.schema_diff.SchemaDiff` as a migration-file
   body. See :ref:`schema-diff`.


.. _schema-diff:

Schema Diff
-----------

.. module:: playhouse.schema_diff

The ``playhouse.schema_diff`` module compares model definitions against
the live database schema and reports basic differences:

* tables to create
* columns added or removed
* indexes added or removed

Columns are compared by name alone (no types, nullability or constraints), so a
rename appears as an addition plus a removal. Partial and expression indexes
are compared by name only. Tables in the database that no model covers are
ignored. Virtual models (sqlite FTS, etc.) are skipped.

.. code-block:: pycon

   >>> from playhouse.schema_diff import diff_models
   >>> diff = diff_models(db, [User, Tweet, Note])
   >>> bool(diff)
   True
   >>> print(diff)
   create table note
   add column user.karma
   drop column user.email
   add index tweet (user_id, flags)

.. function:: diff_models(database, models)

   Compare the live schema against the given models. Returns a
   :class:`SchemaDiff` which is falsy when everything matches.

.. class:: SchemaDiff

   A named tuple of five lists, each mapping directly onto a
   :class:`~playhouse.migrate.SchemaMigrator` call:

   * ``create_tables``: model classes whose tables do not exist, in
     foreign-key dependency order.
   * ``add_columns``: the model :class:`Field` instances missing from the
     database.
   * ``drop_columns``: ``(table, column_name)`` for database columns no
     model declares.
   * ``add_indexes`` / ``drop_indexes``: :class:`IndexDiff` entries.

.. class:: IndexDiff

   Named tuple ``(table, name, columns, unique)``. ``columns is None``
   marks a partial or expression index, detected by name but not
   described. Plain additions carry ``columns``/``unique`` and no name
   (the name is chosen at creation). Removals always carry the name to
   drop.

.. _reflection:

Reflection
----------

.. module:: playhouse.reflection

The ``playhouse.reflection`` module introspects an existing database and
generates Peewee model classes from its schema. It is used internally by
:ref:`pwiz` and :ref:`dataset`.

.. code-block:: python

   from playhouse.reflection import generate_models

   db = PostgresqlDatabase('my_app')
   models = generate_models(db)   # Returns {table_name: ModelClass}

   # list(models.keys())
   # ['account', 'customer', 'order', 'orderitem', 'product']

   # Get a reference to a generated model.
   Customer = models['customer']

   # Or inject into the current namespace:
   # globals().update(models)

   # Query generated models:
   for customer in Customer.select():
       print(customer.name, customer.email)

.. function:: generate_models(database, schema=None, **options)

   :param Database database: database instance to introspect.
   :param str schema: optional schema to introspect.
   :param options: arbitrary options, see :meth:`Introspector.generate_models` for details.
   :returns: a ``dict`` mapping table names to model classes.

.. function:: print_model(model)

   Print a human-readable summary of a model's fields and indexes to
   stdout. Useful for interactive exploration:

   .. code-block:: pycon

      >>> print_model(Tweet)
      tweet
        id AUTO PK
        user INT FK: User.id
        content TEXT
        timestamp DATETIME

      index(es)
        user_id
        timestamp

.. function:: print_table_sql(model)

   Print the ``CREATE TABLE`` SQL for a model class (without indexes):

   .. code-block:: pycon

      >>> print_table_sql(Tweet)
      CREATE TABLE IF NOT EXISTS "tweet" (
        "id" INTEGER NOT NULL PRIMARY KEY,
        "user_id" INTEGER NOT NULL,
        "content" TEXT NOT NULL,
        "timestamp" DATETIME NOT NULL,
        FOREIGN KEY ("user_id") REFERENCES "user" ("id")
      )

.. class:: Introspector(metadata, schema=None)

   Metadata can be extracted from a database by instantiating an :class:`Introspector`.
   Rather than instantiating this class directly, it is recommended to use the
   factory method :meth:`~Introspector.from_database`.

   .. classmethod:: from_database(database, schema=None)

      :param database: a :class:`Database` instance.
      :param str schema: an optional schema (supported by some databases).

      Creates an :class:`Introspector` instance suitable for use with the
      given database.

      .. code-block:: python

         db = SqliteDatabase('my_app.db')
         introspector = Introspector.from_database(db)
         models = introspector.generate_models()

         # User and Tweet (assumed to exist in the database) are
         # peewee Model classes generated from the database schema.
         User  = models['user']
         Tweet = models['tweet']

   .. method:: generate_models(skip_invalid=False, table_names=None, literal_column_names=False, bare_fields=False, include_views=False)

      :param bool skip_invalid: Skip tables whose names are not valid Python
          identifiers.
      :param list table_names: Only generate models for the given tables.
      :param bool literal_column_names: Use the exact database column names
          as field names (rather than converting to Python naming conventions).
      :param bool bare_fields: Do not attempt to detect field types, use
          :class:`BareField` for all columns (**SQLite only**).
      :param bool include_views: Also generate models for views.
      :return: A dictionary mapping table-names to model classes.

      Introspect the database, reading in the tables, columns, and foreign
      key constraints, then generate a dictionary mapping each database table
      to a dynamically-generated :class:`Model` class.


.. _pwiz:

pwiz - Model Generator
-----------------------

.. module:: pwiz

``pwiz`` is a command-line tool that introspects a database and prints
ready-to-use Peewee model code. If you have an existing database, running
``pwiz`` saves significant time generating the initial model definitions.

.. code-block:: shell

   # Introspect a Postgresql database and write models to a file:
   pwiz -e postgresql -u postgres my_db > models.py

   # Introspect a SQLite database:
   pwiz -e sqlite path/to/my.db

   # Introspect a MySQL database (prompts for password):
   pwiz -e mysql -u root -P my_db

   # Introspect only specific tables:
   pwiz -e postgresql my_db -t user,tweet,follow


Command-line options:

+--------+-------------------------------------------+-------------------------+
| Option | Meaning                                   | Example                 |
+========+===========================================+=========================+
| ``-e`` | Database backend                          | ``-e mysql``            |
+--------+-------------------------------------------+-------------------------+
| ``-H`` | Host                                      | ``-H 10.0.0.1``         |
+--------+-------------------------------------------+-------------------------+
| ``-p`` | Port                                      | ``-p 5432``             |
+--------+-------------------------------------------+-------------------------+
| ``-u`` | Username                                  | ``-u postgres``         |
+--------+-------------------------------------------+-------------------------+
| ``-P`` | Password (prompts interactively)          |                         |
+--------+-------------------------------------------+-------------------------+
| ``-s`` | Schema                                    | ``-s public``           |
+--------+-------------------------------------------+-------------------------+
| ``-t`` | Comma-separated list of tables to include | ``-t user,tweet``       |
+--------+-------------------------------------------+-------------------------+
| ``-v`` | Include views                             |                         |
+--------+-------------------------------------------+-------------------------+
| ``-i`` | Embed database info as a comment          |                         |
+--------+-------------------------------------------+-------------------------+
| ``-o`` | Preserve original column order            |                         |
+--------+-------------------------------------------+-------------------------+
| ``-I`` | Ignore fields whose type is unknown       |                         |
+--------+-------------------------------------------+-------------------------+
| ``-L`` | Use legacy table and column naming        |                         |
+--------+-------------------------------------------+-------------------------+

Valid ``-e`` values: ``sqlite``, ``mysql``, ``postgresql``, ``cockroachdb``.

.. warning::
   If a password is required to access your database, you will be prompted to
   enter it using a secure prompt.

   **The password will be included in the output**. Specifically, at the top
   of the file a :class:`Database` will be defined along with any required
   parameters - including the password.

Example output for a SQLite database with ``user`` and ``tweet`` tables:

.. code-block:: python

   from peewee import *

   database = SqliteDatabase('example.db')

   class UnknownField(object):
       def __init__(self, *_, **__): pass

   class BaseModel(Model):
       class Meta:
           database = database

   class User(BaseModel):
       username = TextField(unique=True)

       class Meta:
           table_name = 'user'

   class Tweet(BaseModel):
       content = TextField()
       timestamp = DateTimeField()
       user = ForeignKeyField(column_name='user_id', field='id', model=User)

       class Meta:
           table_name = 'tweet'

``pwiz`` detects foreign keys and unique constraints, and preserves explicit
table names.

.. note::
    The ``UnknownField`` is a placeholder that is used in the event your schema
    contains a column declaration that Peewee doesn't know how to map to a
    field class.

.. _test-utils:

Test Utilities
--------------

.. module:: playhouse.test_utils

``playhouse.test_utils`` provides helpers for testing peewee projects.

.. class:: count_queries(only_select=False)

   Context manager that counts the number of SQL queries executed within
   its block.

   :param bool only_select: If ``True``, count only ``SELECT`` queries.

   .. code-block:: python

      with count_queries() as counter:
          user = User.get(User.username == 'alice')
          tweets = list(user.tweets)   # Triggers a second query.

      assert counter.count == 2

   .. attribute:: count

      Number of queries executed.

   .. method:: get_queries()

      Return the executed queries as a list of ``logging.LogRecord`` objects.
      Each record's ``msg`` attribute is the ``(sql, params)`` tuple.

.. function:: assert_query_count(expected, only_select=False)

   Decorator or context manager that raises ``AssertionError`` if the number
   of queries executed does not match ``expected``.

   As a decorator:

   .. code-block:: python

       class TestAPI(unittest.TestCase):
           @assert_query_count(1)
           def test_get_user(self):
               user = User.get_by_id(1)

   As a context manager:

   .. code-block:: python

       with assert_query_count(3):
           result = my_function_that_should_make_exactly_three_queries()
