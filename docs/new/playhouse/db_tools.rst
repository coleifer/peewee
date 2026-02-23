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

The ``playhouse.db_url`` module lets you configure Peewee from a connection
string, which is common in twelve-factor applications where database
credentials live in environment variables.

.. code-block:: python

   import os
   from playhouse.db_url import connect

   db = connect(os.environ.get('DATABASE_URL', 'sqlite:///default.db'))

URL format: ``scheme://user:password@host:port/dbname?option=value``

Common schemes:

+------------------------+------------------------------------------+
| Scheme                 | Database class                           |
+========================+==========================================+
| ``sqlite:///path``     | :py:class:`SqliteDatabase`               |
+------------------------+------------------------------------------+
| ``sqliteext:///path``  | :py:class:`SqliteExtDatabase`            |
+------------------------+------------------------------------------+
| ``postgres://...``     | :py:class:`PostgresqlDatabase`           |
+------------------------+------------------------------------------+
| ``postgresext://...``  | :py:class:`PostgresqlExtDatabase`        |
+------------------------+------------------------------------------+
| ``mysql://...``        | :py:class:`MySQLDatabase`                |
+------------------------+------------------------------------------+
| ``cockroachdb://...``  | :py:class:`CockroachDatabase`            |
+------------------------+------------------------------------------+

Pass additional keyword arguments in the query string:

.. code-block:: python

   db = connect('postgres://user:pass@host/db?max_connections=20')

.. py:function:: connect(url, **connect_kwargs)

   Parse ``url`` and return an appropriate :py:class:`Database` instance.

.. py:function:: parse(url, unquote_password=False, unquote_user=False)

   Parse a URL and return a dictionary with ``database``, ``host``,
   ``port``, ``user``, and ``password`` keys plus any extra connect
   parameters from the query string.

   Useful if you need to construct a database class manually:

   .. code-block:: python

       params = parse('postgres://user:pass@host:5432/mydb')
       db = MyCustomDatabase(**params)

.. py:function:: register_database(db_class, *names)

   Register a custom database class under one or more URL scheme names so
   that :py:func:`connect` can instantiate it:

   .. code-block:: python

       register_database(FirebirdDatabase, 'firebird')
       db = connect('firebird://my-firebird-db')


.. _pool:

Connection Pooling
------------------

The ``playhouse.pool`` module provides pooled database classes that
recycle connections instead of opening a new one for every request.

In multi-threaded applications, each thread gets its own connection; the
pool maintains up to ``max_connections`` open connections at any time.
In single-threaded applications, a single connection is recycled.

The application only needs to ensure that connections are *closed* when work
is done — typically at the end of an HTTP request. Closing a pooled connection
returns it to the pool rather than actually disconnecting.

.. code-block:: python

   from playhouse.pool import PooledPostgresqlExtDatabase

   db = PooledPostgresqlExtDatabase(
       'my_app',
       user='postgres',
       max_connections=32,
       stale_timeout=300,   # Recycle connections older than 5 minutes.
   )

Available pooled classes:

- :py:class:`PooledPostgresqlDatabase`
- :py:class:`PooledPostgresqlExtDatabase`
- :py:class:`PooledMySQLDatabase`
- :py:class:`PooledSqliteDatabase`
- :py:class:`PooledSqliteExtDatabase`
- :py:class:`PooledCySqliteDatabase`

.. py:class:: PooledDatabase(database, max_connections=20, stale_timeout=None, timeout=None, **kwargs)

   Mixin class mixed into the specific backend subclasses above.

   :param int max_connections: Maximum number of concurrent connections.
       Pass ``None`` for no limit.
   :param int stale_timeout: Seconds after which an idle connection is
       considered stale and will be discarded next time it would be reused.
   :param int timeout: Seconds to block when all connections are in use.
       ``0`` blocks indefinitely; ``None`` (default) raises immediately.

   .. note::
       Stale connections are checked lazily — a connection is only actually
       closed when it would be reused.

   .. note::
       If the pool is exhausted and no ``timeout`` is configured, a
       ``ValueError`` is raised.

   .. py:method:: manual_close()

      Close the current connection permanently without returning it to the
      pool. Use this when a connection has entered a bad state.

   .. py:method:: close_idle()

      Close all pooled connections that are not currently in use.

   .. py:method:: close_stale(age=600)

      Close in-use connections that have exceeded ``age`` seconds.
      Use with caution.

   .. py:method:: close_all()

      Close all connections including those currently in use.
      Use with caution.


.. _migrate:

Schema Migrations
-----------------

The ``playhouse.migrate`` module provides a lightweight API for making
incremental schema changes to an existing database without writing raw SQL.

Supported operations:

- Add, rename, or drop columns.
- Make columns nullable or not nullable.
- Change a column's type.
- Rename a table.
- Add or drop indexes and constraints.
- Add or drop column default values.

.. code-block:: python

   from playhouse.migrate import SqliteMigrator, migrate

   migrator = SqliteMigrator(db)

   with db.atomic():
       migrate(
           migrator.add_column('tweet', 'is_published', BooleanField(default=True)),
           migrator.add_column('user', 'email', CharField(null=True)),
           migrator.drop_column('user', 'old_bio'),
       )

Wrap migrations in ``db.atomic()`` if you want them to be transactional
(they are not wrapped automatically).

Instantiate the right migrator class for your database:

.. code-block:: python

   from playhouse.migrate import (
       SqliteMigrator,
       PostgresqlMigrator,
       MySQLMigrator,
   )

   # SQLite:
   migrator = SqliteMigrator(db)

   # PostgreSQL:
   migrator = PostgresqlMigrator(db)

   # MySQL:
   migrator = MySQLMigrator(db)


Common Operations
^^^^^^^^^^^^^^^^^

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

   migrate(migrator.rename_column('story', 'pub_date', 'publish_date'))

**Drop a column:**

.. code-block:: python

   migrate(migrator.drop_column('story', 'old_field'))

**Nullable / not nullable:**

.. code-block:: python

   migrate(
       migrator.drop_not_null('story', 'pub_date'),        # Allow NULLs.
       migrator.add_not_null('story', 'modified_date'),    # Disallow NULLs.
   )

**Change type:**

.. code-block:: python

   migrate(migrator.alter_column_type('person', 'email', TextField()))

**Rename table:**

.. code-block:: python

   migrate(migrator.rename_table('story', 'stories'))

**Add / drop indexes:**

.. code-block:: python

   migrate(
       migrator.add_index('story', ('pub_date',), False),             # Simple.
       migrator.add_index('story', ('category_id', 'title'), True),   # Unique.
       migrator.drop_index('story', 'story_pub_date_status'),
   )

**Add / drop constraints:**

.. code-block:: python

   from peewee import Check

   migrate(
       migrator.add_constraint('product', 'price_positive', Check('price >= 0')),
       migrator.drop_constraint('product', 'price_positive'),
       migrator.add_unique('person', 'first_name', 'last_name'),
   )

.. note::
   SQLite has limited ``ALTER TABLE`` support. The following operations are
   **not** available on SQLite: ``add_constraint``, ``drop_constraint``,
   ``add_unique``.

**Column defaults:**

.. code-block:: python

   # Add a default value:
   migrate(migrator.add_column_default('entry', 'status', 'draft'))

   # Use a function (not supported in SQLite):
   migrate(migrator.add_column_default('entry', 'created_at', fn.NOW()))

   # SQLite-compatible function syntax:
   migrate(migrator.add_column_default('entry', 'created_at', 'now()'))

   # Remove a default:
   migrate(migrator.drop_column_default('entry', 'status'))

**PostgreSQL search path:**

.. code-block:: python

   migrator = PostgresqlMigrator(db)
   migrate(
       migrator.set_search_path('my_schema'),
       migrator.add_column('table', 'field', TextField(default='')),
   )


Migration API
^^^^^^^^^^^^^

.. py:function:: migrate(*operations)

   Execute one or more schema-altering operations atomically within the
   database driver. Pass ``migrate()`` the return values of
   ``migrator.xxx()`` methods:

   .. code-block:: python

       migrate(
           migrator.add_column('t', 'col', CharField(default='')),
           migrator.add_index('t', ('col',), False),
       )

.. py:class:: SchemaMigrator(database)

   Base class; do not instantiate directly. Use the backend-specific
   subclass instead.

   All methods return an operation object to be passed to
   :py:func:`migrate`.

   .. py:method:: add_column(table, column_name, field)
   .. py:method:: drop_column(table, column_name, cascade=True)
   .. py:method:: rename_column(table, old_name, new_name)
   .. py:method:: add_not_null(table, column)
   .. py:method:: drop_not_null(table, column)
   .. py:method:: add_column_default(table, column, default)
   .. py:method:: drop_column_default(table, column)
   .. py:method:: alter_column_type(table, column, field, cast=None)
   .. py:method:: rename_table(old_name, new_name)
   .. py:method:: add_index(table, columns, unique=False, using=None)
   .. py:method:: drop_index(table, index_name)
   .. py:method:: add_constraint(table, name, constraint)
   .. py:method:: drop_constraint(table, name)
   .. py:method:: add_unique(table, *column_names)

.. py:class:: PostgresqlMigrator(database)

   .. py:method:: set_search_path(schema_name)

      Set the Postgres search path for subsequent operations.

.. py:class:: SqliteMigrator(database)

   SQLite-specific subclass. Does not support ``add_constraint``,
   ``drop_constraint``, or ``add_unique``.

.. py:class:: MySQLMigrator(database)

   MySQL-specific subclass.


.. _reflection:

Reflection
----------

The ``playhouse.reflection`` module introspects an existing database and
generates Peewee model classes from its schema. It is used internally by
:ref:`pwiz` and :ref:`dataset`.

.. code-block:: python

   from playhouse.reflection import generate_models

   db = PostgresqlDatabase('my_app')
   models = generate_models(db)   # Returns {table_name: ModelClass}

   # Inject into the current namespace:
   globals().update(models)

   # Query generated models immediately:
   for user in User.select():
       print(user.name)

.. py:function:: generate_models(database, schema=None, **options)

   :param database: A :py:class:`Database` instance.
   :param str schema: Optional schema to introspect (PostgreSQL).
   :param options: Forwarded to :py:meth:`Introspector.generate_models`.
   :returns: ``dict`` mapping table names to model classes.

.. py:function:: print_model(model)

   Print a human-readable summary of a model's fields and indexes to
   stdout. Useful for interactive exploration:

   .. code-block:: pycon

       >>> print_model(User)
       user
         id AUTO PK
         email TEXT
         name TEXT

       index(es)
         email UNIQUE

.. py:function:: print_table_sql(model)

   Print the ``CREATE TABLE`` SQL for a model class (without indexes or
   constraints):

   .. code-block:: pycon

       >>> print_table_sql(Tweet)
       CREATE TABLE IF NOT EXISTS "tweet" (
         "id" INTEGER NOT NULL PRIMARY KEY,
         "user_id" INTEGER NOT NULL,
         "content" TEXT NOT NULL,
         FOREIGN KEY ("user_id") REFERENCES "user" ("id")
       )

.. py:class:: Introspector(metadata, schema=None)

   .. py:classmethod:: from_database(database, schema=None)

      Create an :py:class:`Introspector` from an open database connection.

      .. code-block:: python

          introspector = Introspector.from_database(db)
          models = introspector.generate_models()
          User  = models['user']
          Tweet = models['tweet']

   .. py:method:: generate_models(skip_invalid=False, table_names=None, literal_column_names=False, bare_fields=False, include_views=False)

      :param bool skip_invalid: Skip tables whose names are not valid Python
          identifiers.
      :param list table_names: Only generate models for the given tables.
      :param bool literal_column_names: Use the exact database column names
          as field names (rather than converting to Python naming conventions).
      :param bool bare_fields: Do not attempt to detect field types; use
          :py:class:`BareField` for all columns.
      :param bool include_views: Also generate models for views.


.. _pwiz:

pwiz — Model Generator
-----------------------

``pwiz`` is a command-line tool that introspects a database and prints
ready-to-use Peewee model code. If you have an existing database, running
``pwiz`` saves significant time generating the initial model definitions.

.. code-block:: shell

   # Introspect a PostgreSQL database and write models to a file:
   python -m pwiz -e postgresql -u postgres my_db > models.py

   # Introspect a SQLite database:
   python -m pwiz -e sqlite path/to/my.db

   # Introspect a MySQL database (prompts for password):
   python -m pwiz -e mysql -u root -P my_db

   # Introspect only specific tables:
   python -m pwiz -e postgresql my_db -t user,tweet,follow

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

Valid ``-e`` values: ``sqlite``, ``mysql``, ``postgresql``.

.. warning::
   If a password is required, it will appear in plaintext in the generated
   file. Review the output before committing it to source control.

Example output for a SQLite database with ``user`` and ``tweet`` tables:

.. code-block:: python

   from peewee import *

   database = SqliteDatabase('example.db', **{})

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
       content   = TextField()
       timestamp = DateTimeField()
       user      = ForeignKeyField(column_name='user_id', field='id', model=User)
       class Meta:
           table_name = 'tweet'

Note that ``pwiz`` detects foreign keys, unique constraints, and preserves
explicit table names.


.. _test-utils:

Test Utilities
--------------

``playhouse.test_utils`` provides helpers for asserting query counts in your
test suite.

.. py:class:: count_queries(only_select=False)

   Context manager that counts the number of SQL queries executed within
   its block.

   :param bool only_select: If ``True``, count only ``SELECT`` queries.

   .. code-block:: python

       with count_queries() as counter:
           user = User.get(User.username == 'alice')
           tweets = list(user.tweets)   # Triggers a second query.

       assert counter.count == 2

   .. py:attribute:: count

      Number of queries executed.

   .. py:method:: get_queries()

      Return a list of ``(sql, params)`` 2-tuples for each query executed.

.. py:function:: assert_query_count(expected, only_select=False)

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
