.. _schema:

Schema Management
=================

This document covers creating and dropping tables, managing indexes and
constraints after the fact, and evolving a schema over time.

Creating Tables
---------------

Create tables for a list of models with :meth:`Database.create_tables`:

.. code-block:: python

   db.create_tables([User, Tweet, Favorite])

By default Peewee uses ``CREATE TABLE IF NOT EXISTS``, making it safe to call
on application startup. To disable this, pass ``safe=False``.

.. code-block:: python

   db.create_tables([User, Tweet, Favorite], safe=False)

To create a single table:

.. code-block:: python

   Tweet.create_table()

:meth:`Database.create_tables` respects foreign key dependencies: if ``Tweet``
references ``User``, ``User``'s table is created first regardless of the order
in which they appear in the list.

Indexes declared in ``Meta.indexes`` and via :meth:`Model.add_index` are
created along with the table.

.. note::
   ``create_tables`` creates missing tables but does **not** apply schema
   changes to existing ones. For that, see :ref:`migrations`.

Dropping Tables
---------------

.. code-block:: python

   db.drop_tables([User, Tweet, Favorite])

By default Peewee uses ``DROP TABLE IF EXISTS``, making it safe to call
multiple times. To disable this, pass ``safe=False``.

.. code-block:: python

   db.drop_tables([User, Tweet, Favorite], safe=False)

Pass ``cascade=True`` on Postgresql to drop dependent objects and let the
database handle dependency resolution:

.. code-block:: python

   db.drop_tables([User, Tweet, Favorite], cascade=True)

To drop a single table:

.. code-block:: python

   User.drop_table()

SchemaManager
-------------

:class:`SchemaManager` provides finer-grained control over DDL operations.
Each model exposes an instance at ``Model._schema``.

Creating and dropping indexes independently:

.. code-block:: python

   # Create just the indexes for a model (table already exists).
   User._schema.create_indexes()

   # Drop a specific index.
   User._schema.drop_index(User.username)

Adding a foreign key constraint after table creation (useful when circular
foreign keys are involved - see :ref:`circular-fks` in the models document):

.. code-block:: python

   # The table exists but the constraint was deferred.
   User._schema.create_foreign_key(User.favorite_tweet)

.. note::
   SQLite does not support adding foreign key constraints to existing tables.
   On SQLite, ``create_foreign_key`` will result in an
   :class:`OperationalError`.

Truncating a table:

.. code-block:: python

   User._schema.truncate_table()  # No cascade.
   User._schema.truncate_table(cascade=True)  # Postgresql only.

.. seealso::
   :class:`SchemaManager` API reference.

.. _migrations:

Schema Migrations
-----------------

Peewee ships two layers of migration tooling in playhouse: the
:ref:`migrate <migrate>` module, which provides a Python interface for making
schema changes, and the :ref:`migrations runner <migration-runner>`, which
runs versioned migration scripts. For schema changes in an existing
deployment (adding columns, dropping columns, renaming tables, modifying
indexes), use one of the following approaches.

Migration runner
^^^^^^^^^^^^^^^^

The :ref:`runner <migration-runner>` applies plain-python migration
scripts in numeric order, recording each by name in a history table.
The CLI is installed as ``pwmigrate``:

.. code-block:: console

   # Identifies differences between application code and schema, then
   # generates a migration file.
   $ pwmigrate app.settings.db create -m app.models "add karma"
   migrations/0002_add_karma.py

   # Equivalent to above, but using a database URL instead of the
   # dotted-path:
   $ pwmigrate postgresql:///my_db create -m app.models "add karma"

   $ pwmigrate app.settings.db up
   applied: 0002_add_karma

Scripts define ``up(migrator, db)`` and, optionally, ``down(migrator,
db)``. With ``-m / --models``, migrations are generated from a
:ref:`schema diff <schema-diff>` against your model definitions. If ``-m`` is
not specified, a bare migration template will be written.

.. seealso::
   :ref:`migration-runner` for the runner, CLI and generation reference.

Migrate module
^^^^^^^^^^^^^^

The :ref:`playhouse.migrate <migrate>` module provides a set of helper
functions for common schema changes, applied through a :class:`~playhouse.migrate.SchemaMigrator`:

.. code-block:: python

   from playhouse.migrate import *

   db = SqliteDatabase(...)

   migrator = SchemaMigrator.from_database(db)

   first_name = TextField(default='')
   last_name  = TextField(default='')

   with db.atomic():
       migrate(
           migrator.add_column('person', 'first_name', first_name),
           migrator.add_column('person', 'last_name',  last_name),
           migrator.drop_column('person', 'name'),
       )

Supported operations:

- Add, rename, or drop columns.
- Make columns nullable or not nullable.
- Change a column's type.
- Rename a table.
- Add or drop indexes and constraints.
- Add or drop column default values.

.. seealso::
   :ref:`migrate` for in-depth examples and API reference.

Raw SQL migrations
^^^^^^^^^^^^^^^^^^^

For changes the migrate module does not cover, execute ALTER TABLE statements
directly:

.. code-block:: python

   with db.atomic():
       db.execute_sql('ALTER TABLE tweet ADD COLUMN view_count INTEGER DEFAULT 0')

SQLite limitations
^^^^^^^^^^^^^^^^^^

SQLite has limited ALTER TABLE support depending on which version is installed.
Some functionality can be emulated using a detailed fallback path which moves
the existing table, recreates a new table, then copies into the newly-created
table.

Version-specific or limited functionality:

* ``DROP COLUMN`` (3.35.0, fallback for older).
* ``RENAME COLUMN`` (3.25.0, fallback for older).
* ``ALTER COLUMN ... SET/DROP NOT NULL`` (3.53.0, fallback for older).
* ``ALTER COLUMN ... DEFAULT ...`` (uses fallback)
* ``ALTER COLUMN ... TYPE ...`` (uses fallback)
* ``ADD/DROP CONSTRAINT`` (3.53.0, limited to certain operations).

For more complex SQLite schema changes, the standard workaround is to:

1. Create a new table with the desired schema.
2. Copy data with ``INSERT INTO new_table SELECT ... FROM old_table``.
3. Drop the old table.
4. Rename the new table.

The playhouse :ref:`migrate <migrate>` module transparently handles the above
workaround for older SQLite versions.

Introspecting an Existing Schema
----------------------------------

:meth:`Database.get_tables` returns the names of all tables in the database:

.. code-block:: python

   db.get_tables()
   # ['user', 'tweet', 'favorite']

:meth:`Database.get_columns` returns column metadata for a table as a list of
:class:`ColumnMetadata` instances:

.. code-block:: python

   for col in db.get_columns('tweet'):
       print(col.name, col.data_type, col.null)

:meth:`Database.get_indexes` returns index metadata as a list of
:class:`IndexMetadata` instances:

.. code-block:: python

   for idx in db.get_indexes('user'):
       print(idx.name, idx.columns, idx.unique)

:meth:`Database.get_foreign_keys` returns foreign key metadata as a list of
:class:`ForeignKeyMetadata` instances:

.. code-block:: python

   for fk in db.get_foreign_keys('tweet'):
       print(fk.column, '->', fk.dest_table, fk.dest_column)

:meth:`Database.get_views` returns a list of views in the database as a list of
:class:`ViewMetadata` instances:

.. code-block:: python

   for view in db.get_views():
       print(view.name, view.sql)


Generating models from an existing database
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :ref:`pwiz` command-line tool introspects an existing database and emits
Python model definitions:

.. code-block:: shell

   pwiz -e postgresql my_database > models.py
   pwiz -e sqlite my_app.db > models.py

The generated models can be used directly or as a starting point for further
customization.
