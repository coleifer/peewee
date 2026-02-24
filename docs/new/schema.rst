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
   A common pattern in web applications is to call ``db.create_tables(MODELS, safe=True)``
   once at startup. This ensures all tables exist without failing on an already-
   initialized database. It does **not** apply schema changes - for that, see
   :ref:`migrations`.

Dropping Tables
---------------

.. code-block:: python

   db.drop_tables([User, Tweet, Favorite])   # Dependents first.

By default Peewee uses ``DROP TABLE IF EXISTS``, making it safe to call
multiple times. To disable this, pass ``safe=False``.

.. code-block:: python

   db.drop_tables([User, Tweet, Favorite], safe=False)

Pass ``cascade=True`` (PostgreSQL and MySQL) to let the database handle
dependency ordering:

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

   User._schema.truncate_table()       # No cascade.
   User._schema.truncate_table(cascade=True)   # PostgreSQL only.

.. seealso::
   :class:`SchemaManager` API reference.

.. _migrations:

Schema Migrations
-----------------

Peewee does not include a built-in migration system. For schema changes in an
existing deployment - adding columns, dropping columns, renaming tables,
modifying indexes - use one of the following approaches.

Playhouse migrate module
^^^^^^^^^^^^^^^^^^^^^^^^^

The :ref:`migrate <migrate>` module in playhouse provides a set of helper
functions for common schema changes, applied through a :class:`Migrator`:

.. code-block:: python

   from playhouse.migrate import *

   # For SQLite:
   migrator = SqliteMigrator(db)

   # For PostgreSQL:
   # migrator = PostgresqlMigrator(db)

   first_name = TextField(default='')
   last_name  = TextField(default='')

   with db.atomic():
       migrate(
           migrator.add_column('person', 'first_name', first_name),
           migrator.add_column('person', 'last_name',  last_name),
           migrator.drop_column('person', 'name'),
       )

Add new field(s) to an existing model:

.. code-block:: python

    # Create your field instances. For non-null fields you must specify a
    # default value.
    pubdate_field = DateTimeField(null=True)
    comment_field = TextField(default='')

    # Run the migration, specifying the database table, field name and field.
    migrate(
        migrator.add_column('comment_tbl', 'pub_date', pubdate_field),
        migrator.add_column('comment_tbl', 'comment', comment_field),
    )

.. note::
    Peewee appends ``_id`` to the column name for a given :class:`ForeignKeyField`
    by default. When adding a foreign-key, you will want to ensure you give it
    the proper column name. For example, to add a ``user`` foreign-key to a
    ``Tweet`` model:

    .. code-block:: python

        # Our desired model will look like this:
        class Tweet(BaseModel):
            user = ForeignKeyField(User)  # Add this field.
            # ... other fields ...

        # Migration code:
        user = ForeignKeyField(User, field=User.id, null=True)
        migrate(
            # Note that the column name given is "user_id".
            migrator.add_column(Tweet._meta.table_name, 'user_id', user),
        )

Renaming a field:

.. code-block:: python

    # Specify the table, original name of the column, and its new name.
    migrate(
        migrator.rename_column('story', 'pub_date', 'publish_date'),
        migrator.rename_column('story', 'mod_date', 'modified_date'),
    )

Dropping a field:

.. code-block:: python

    migrate(
        migrator.drop_column('story', 'some_old_field'),
    )

Making a field nullable or not nullable:

.. code-block:: python

    # Note that when making a field not null that field must not have any
    # NULL values present.
    migrate(
        # Make `pub_date` allow NULL values.
        migrator.drop_not_null('story', 'pub_date'),

        # Prevent `modified_date` from containing NULL values.
        migrator.add_not_null('story', 'modified_date'),
    )

Altering a field's data-type:

.. code-block:: python

    # Change a VARCHAR(50) field to a TEXT field.
    migrate(
        migrator.alter_column_type('person', 'email', TextField())
    )

Renaming a table:

.. code-block:: python

    migrate(
        migrator.rename_table('story', 'stories_tbl'),
    )

Adding an index:

.. code-block:: python

    # Specify the table, column names, and whether the index should be
    # UNIQUE or not.
    migrate(
        # Create an index on the `pub_date` column.
        migrator.add_index('story', ('pub_date',), False),

        # Create a multi-column index on the `pub_date` and `status` fields.
        migrator.add_index('story', ('pub_date', 'status'), False),

        # Create a unique index on the category and title fields.
        migrator.add_index('story', ('category_id', 'title'), True),
    )

Dropping an index:

.. code-block:: python

    # Specify the index name.
    migrate(migrator.drop_index('story', 'story_pub_date_status'))

Adding or dropping table constraints:

.. code-block:: python

    # Add a CHECK() constraint to enforce the price cannot be negative.
    migrate(migrator.add_constraint(
        'products',
        'price_check',
        Check('price >= 0')))

    # Remove the price check constraint.
    migrate(migrator.drop_constraint('products', 'price_check'))

    # Add a UNIQUE constraint on the first and last names.
    migrate(migrator.add_unique('person', 'first_name', 'last_name'))

Adding or dropping a database-level default value for a column:

.. code-block:: python

    # Add a default value for a status column.
    migrate(migrator.add_column_default(
        'entries',
        'status',
        'draft'))

    # Remove the default.
    migrate(migrator.drop_column_default('entries', 'status'))

    # Use a function for the default value (does not work with Sqlite):
    migrate(migrator.add_column_default(
        'entries',
        'timestamp',
        fn.now()))

    # Or alternatively (works with Sqlite):
    migrate(migrator.add_column_default(
        'entries',
        'timestamp',
        'now()'))

.. note::
    Postgres users may need to set the search-path when using a non-standard
    schema. This can be done as follows:

    .. code-block:: python

        new_field = TextField(default='', null=False)
        migrator = PostgresqlMigrator(db)
        migrate(migrator.set_search_path('my_schema_name'),
                migrator.add_column('table', 'field_name', new_field))

.. seealso::
   :ref:`migrate` in the playhouse documentation for the full API.

Raw SQL migrations
^^^^^^^^^^^^^^^^^^^

For changes the migrate module does not cover, execute ALTER TABLE statements
directly:

.. code-block:: python

   with db.atomic():
       db.execute_sql('ALTER TABLE tweet ADD COLUMN view_count INTEGER DEFAULT 0')

SQLite limitations
^^^^^^^^^^^^^^^^^^

SQLite has limited ALTER TABLE support. It supports ``ADD COLUMN`` and
``RENAME TABLE`` but not ``DROP COLUMN``, ``RENAME COLUMN``, or constraint
changes in older versions (SQLite 3.35.0+ adds ``DROP COLUMN``).

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

   python -m pwiz -e postgresql my_database > models.py
   python -m pwiz -e sqlite my_app.db > models.py

The generated models can be used directly or as a starting point for further
customization.
