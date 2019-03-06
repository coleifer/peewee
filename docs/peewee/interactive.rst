.. _interactive:

Using Peewee Interactively
==========================

Peewee contains helpers for working interactively from a Python interpreter or
something like a Jupyter notebook. For this example, we'll assume that we have
a pre-existing Sqlite database with the following simple schema:

.. code-block:: sql

    CREATE TABLE IF NOT EXISTS "event" (
        "id" INTEGER NOT NULL PRIMARY KEY,
        "key" TEXT NOT NULL,
        "timestamp" DATETIME NOT NULL,
        "metadata" TEXT NOT NULL);

To experiment with querying this database from an interactive interpreter
session, we would start our interpreter and import the following helpers:

* ``peewee.SqliteDatabase`` - to reference the "events.db"
* ``playhouse.reflection.generate_models`` - to generate models from an
  existing database.
* ``playhouse.reflection.print_model`` - to view the model definition.
* ``playhouse.reflection.print_table_sql`` - to view the table SQL.

Our terminal session might look like this:

.. code-block:: pycon

    >>> from peewee import SqliteDatabase
    >>> from playhouse.reflection import generate_models, print_model, print_table_sql
    >>>

The :py:func:`generate_models` function will introspect the database and
generate model classes for all the tables that are found. This is a handy way
to get started and can save a lot of typing. The function returns a dictionary
keyed by the table name, with the generated model as the corresponding value:

.. code-block:: pycon

    >>> db = SqliteDatabase('events.db')
    >>> models = generate_models(db)
    >>> list(models.items())
    [('events', <Model: event>)]

    >>> globals().update(models)  # Inject models into global namespace.
    >>> event
    <Model: event>

To take a look at the model definition, which lists the model's fields and
data-type, we can use the :py:func:`print_model` function:

.. code-block:: pycon

    >>> print_model(event)
    event
      id AUTO
      key TEXT
      timestamp DATETIME
      metadata TEXT

We can also generate a SQL ``CREATE TABLE`` for the introspected model, if you
find that easier to read. This should match the actual table definition in the
introspected database:

.. code-block:: pycon

    >>> print_table_sql(event)
    CREATE TABLE IF NOT EXISTS "event" (
      "id" INTEGER NOT NULL PRIMARY KEY,
      "key" TEXT NOT NULL,
      "timestamp" DATETIME NOT NULL,
      "metadata" TEXT NOT NULL)

Now that we are familiar with the structure of the table we're working with, we
can run some queries on the generated ``event`` model:

.. code-block:: pycon

    >>> for e in event.select().order_by(event.timestamp).limit(5):
    ...     print(e.key, e.timestamp)
    ...
    e00 2019-01-01 00:01:00
    e01 2019-01-01 00:02:00
    e02 2019-01-01 00:03:00
    e03 2019-01-01 00:04:00
    e04 2019-01-01 00:05:00

    >>> event.select(fn.MIN(event.timestamp), fn.MAX(event.timestamp)).scalar(as_tuple=True)
    (datetime.datetime(2019, 1, 1, 0, 1), datetime.datetime(2019, 1, 1, 1, 0))

    >>> event.select().count()  # Or, len(event)
    60

For more information about these APIs and other similar reflection utilities,
see the :ref:`reflection` section of the :ref:`playhouse extensions <playhouse>`
document.

To generate an actual Python module containing model definitions for an
existing database, you can use the command-line :ref:`pwiz <pwiz>` tool. Here
is a quick example:

.. code-block:: console

    $ pwiz -e sqlite events.db > events.py

The ``events.py`` file will now be an import-able module containing a database
instance (referencing the ``events.db``) along with model definitions for any
tables found in the database. ``pwiz`` does some additional nice things like
introspecting indexes and adding proper flags for ``NULL``/``NOT NULL``
constraints, etc.

The APIs discussed in this section:

* :py:func:`generate_models`
* :py:func:`print_model`
* :py:func:`print_table_sql`

More low-level APIs are also available on the :py:class:`Database` instance:

* :py:meth:`Database.get_tables`
* :py:meth:`Database.get_indexes`
* :py:meth:`Database.get_columns` (for a given table)
* :py:meth:`Database.get_primary_keys` (for a given table)
* :py:meth:`Database.get_foreign_keys` (for a given table)
