.. _databases:

Databases
=========

Below the :py:class:`Model` level, peewee uses an abstraction for representing the database.  The
:py:class:`Database` is responsible for establishing and closing connections, making queries,
and gathering information from the database.

The :py:class:`Database` in turn uses another abstraction called an :py:class:`BaseAdapter`, which
is backend-specific and encapsulates functionality specific to a given db driver.  Since there
is some difference in column types across database engines, this information also resides
in the adapter.  The adapter is responsible for smoothing out the quirks of each database
driver to provide a consistent interface, for example sqlite uses the question-mark "?" character
for parameter interpolation, while all the other backends use "%s".

For a high-level overview of working with transactions, check out the :ref:`transactions cookbook <working_with_transactions>`.

For notes on deferring instantiation of database, for example if loading configuration
at run-time, see the notes on :ref:`deferring initialization <deferring_initialization>`.

.. note::
    The internals of the :py:class:`Database` and :py:class:`BaseAdapter` will be
    of interest to anyone interested in adding support for another database driver.


Writing a database driver
-------------------------

Peewee currently supports Sqlite, MySQL and Postgresql.  These databases are very
popular and run the gamut from fast, embeddable databases to heavyweight servers
suitable for large-scale deployments.  That being said, there are a ton of cool
databases out there and adding support for your database-of-choice should be really
easy, provided the driver supports the `DB-API 2.0 spec <http://www.python.org/dev/peps/pep-0249/>`_.

The db-api 2.0 spec should be familiar to you if you've used the standard library
sqlite3 driver, psycopg2 or the like.  Peewee currently relies on a handful of parts:

* `Connection.commit`
* `Connection.execute`
* `Connection.rollback`
* `Cursor.description`
* `Cursor.fetchone`
* `Cursor.fetchmany`

These methods are generally wrapped up in higher-level abstractions and exposed
by the :py:class:`Database` and :py:class:`BaseAdapter`, so even if your driver doesn't
do these exactly you can still get a lot of mileage out of peewee.  An example
is the `apsw sqlite driver <http://code.google.com/p/apsw/>`_ which I'm tinkering with
adding support for.

.. note:: In later versions of peewee, the db-api 2.0 methods may be further abstracted
    out to add support for drivers that don't conform to the spec.

Getting down to it, writing some classes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are two classes you will want to implement at the very least:

* :py:class:`BaseAdapter` - handles low-level functionality like opening and closing
    connections to the database, as well as describing the features provided by
    the database engine
* :py:class:`Database` - higher-level interface that executes queries, manage
    transactions, and can introspect the underlying db.

Let's say we want to add support for a fictitious "FooDB" which has an open-source
python driver that uses the DB-API 2.0.

The Adapter
^^^^^^^^^^^

The adapter provides a bridge between the driver and peewee's higher-level database
class which is responsible for executing queries.

.. code-block:: python

    from peewee import BaseAdapter
    import foodb # our fictional driver


    class FooAdapter(BaseAdapter):
        def connect(self, database, **kwargs):
            return foodb.connect(database, **kwargs)


Now we want to create a mapping that exposes the operations our database engine
supports.  These are the operations that a user perform when building out the
``WHERE`` clause of a given query.

.. code-block:: python

    class FooAdapter(BaseAdapter):
        operations = {
            'lt': '< %s',
            'lte': '<= %s',
            'gt': '> %s',
            'gte': '>= %s',
            'eq': '= %s',
            'ne': '!= %s',
            'in': 'IN (%s)',
            'is': 'IS %s',
            'isnull': 'IS NULL',
            'between': 'BETWEEN %s AND %s',
            'icontains': 'ILIKE %s',
            'contains': 'LIKE %s',
            'istartswith': 'ILIKE %s',
            'startswith': 'LIKE %s',
        }

        def connect(self, database, **kwargs):
            return foodb.connect(database, **kwargs)

Other things the adapter handles that are not covered here include:

* last insert id and number of rows modified
* specifying characters used for string interpolation and quoting identifiers,
  for instance, sqlite uses "?" for interpolation and MySQL uses a backtick for quoting
* modifying user input for various lookup types, for instance a "LIKE" query will
  surround the incoming phrase with "%" characters.

The database class
^^^^^^^^^^^^^^^^^^

The :py:class:`Database` provides a higher-level API and is responsible for executing queries,
creating tables and indexes, and introspecting the database to get lists of tables.
Each database must specify a :py:class:`BaseAdapter` subclass, so our database will
need to specify the ``FooAdapter`` we just defined:

.. code-block:: python

    from peewee import Database

    class FooDatabase(Database):
        def __init__(self, database, **connect_kwargs):
            super(FooDatabase, self).__init__(FooAdapter(), database, **connect_kwargs)


This is the absolute minimum needed, though some features will not work -- for best
results you will want to additionally add a method for extracting a list of tables
and indexes for a table from the database.  We'll pretend that ``FooDB`` is a lot like
MySQL and has special "SHOW" statements:

.. code-block:: python

    class FooDatabase(Database):
        def __init__(self, database, **connect_kwargs):
            super(FooDatabase, self).__init__(FooAdapter(), database, **connect_kwargs)

        def get_tables(self):
            res = self.execute('SHOW TABLES;')
            return [r[0] for r in res.fetchall()]

        def get_indexes_for_table(self, table):
            res = self.execute('SHOW INDEXES IN %s;' % self.quote_name(table))
            rows = sorted([(r[2], r[1] == 0) for r in res.fetchall()])
            return rows

There is a good deal of functionality provided by the Database class that is not
covered here.  Refer to the documentation below or the `source code <https://github.com/coleifer/peewee/blob/master/peewee.py>`_. for details.

.. note:: If your driver conforms to the db-api 2.0 spec, there shouldn't be
    much work needed to get up and running.


Using our new database
^^^^^^^^^^^^^^^^^^^^^^

Our new database can be used just like any of the other database subclasses:

.. code-block:: python

    from peewee import *
    from foodb_ext import FooDatabase

    db = FooDatabase('my_database', user='foo', password='secret')

    class BaseModel(Model):
        class Meta:
            database = db

    class Blog(BaseModel):
        title = CharField()
        contents = TextField()
        pub_date = DateTimeField()


Database and its subclasses
---------------------------

.. py:class:: Database

    A high-level api for working with the supported database engines.  ``Database``
    provides a wrapper around some of the functions performed by the ``Adapter``,
    in addition providing support for:

    - execution of SQL queries
    - creating and dropping tables and indexes

    .. py:method:: __init__(adapter, database[, threadlocals=False[, autocommit=True[, **connect_kwargs]]])

        :param adapter: an instance of a :py:class:`BaseAdapter` subclass
        :param database: the name of the database (or filename if using sqlite)
        :param threadlocals: whether to store connections in a threadlocal
        :param autocommit: automatically commit every query executed by calling :py:meth:`~Database.execute`
        :param connect_kwargs: any arbitrary parameters to pass to the database driver when connecting

        .. note::
            if your database name is not known when the class is declared, you can pass
            ``None`` in as the database name which will mark the database as "deferred"
            and any attempt to connect while in this state will raise an exception.  To
            initialize your database, call the :py:meth:`Database.init` method with
            the database name

    .. py:method:: init(database[, **connect_kwargs])

        If the database was instantiated with database=None, the database is said to be in
        a 'deferred' state (see :ref:`notes <deferring_initialization>`) -- if this is the case,
        you can initialize it at any time by calling the ``init`` method.

        :param database: the name of the database (or filename if using sqlite)
        :param connect_kwargs: any arbitrary parameters to pass to the database driver when connecting

    .. py:method:: connect()

        Establishes a connection to the database

        .. note::
            If you initialized with ``threadlocals=True``, then this will store
            the connection inside a threadlocal, ensuring that connections are not
            shared across threads.

    .. py:method:: close()

        Closes the connection to the database (if one is open)

        .. note::
            If you initialized with ``threadlocals=True``, only a connection local
            to the calling thread will be closed.

    .. py:method:: get_conn()

        :rtype: a connection to the database, creates one if does not exist

    .. py:method:: get_cursor()

        :rtype: a cursor for executing queries

    .. py:method:: set_autocommit(autocommit)

        :param autocommit: a boolean value indicating whether to turn on/off autocommit
            **for the current connection**

    .. py:method:: get_autocommit()

        :rtype: a boolean value indicating whether autocommit is on **for the current connection**

    .. py:method:: execute(sql[, params=None])

        :param sql: a string sql query
        :param params: a list or tuple of parameters to interpolate

        .. note::
            You can configure whether queries will automatically commit by using
            the :py:meth:`~Database.set_autocommit` and :py:meth:`Database.get_autocommit`
            methods.

    .. py:method:: commit()

        Call ``commit()`` on the active connection, committing the current transaction

    .. py:method:: rollback()

        Call ``rollback()`` on the active connection, rolling back the current transaction

    .. py:method:: commit_on_success(func)

        Decorator that wraps the given function in a single transaction, which,
        upon success will be committed.  If an error is raised inside the function,
        the transaction will be rolled back and the error will be re-raised.

        :param func: function to decorate

        .. code-block:: python

            @database.commit_on_success
            def transfer_money(from_acct, to_acct, amt):
                from_acct.charge(amt)
                to_acct.pay(amt)
                return amt

    .. py:method:: transaction()

        Return a context manager that executes statements in a transaction.  If an
        error is raised inside the context manager, the transaction will be rolled
        back, otherwise statements are committed when exiting.

        .. code-block:: python

            # delete a blog instance and all its associated entries, but
            # do so within a transaction
            with database.transaction():
                blog.delete_instance(recursive=True)

    .. py:method:: last_insert_id(cursor, model)

        :param cursor: the database cursor used to perform the insert query
        :param model: the model class that was just created
        :rtype: the primary key of the most recently inserted instance

    .. py:method:: rows_affected(cursor)

        :rtype: number of rows affected by the last query

    .. py:method:: create_table(model_class[, safe=False])

        :param model_class: :py:class:`Model` class to create table for
        :param safe: if ``True``, query will add a ``IF NOT EXISTS`` clause

    .. py:method:: create_index(model_class, field_names[, unique=False])

        :param model_class: :py:class:`Model` table on which to create index
        :param field_name: name of field(s) to create index on (a string or list)
        :param unique: whether the index should enforce uniqueness

    .. py:method:: create_foreign_key(model_class, field)

        :param model_class: :py:class:`Model` table on which to create foreign key index / constraint
        :param field: :py:class:`Field` object

    .. py:method:: drop_table(model_class[, fail_silently=False])

        :param model_class: :py:class:`Model` table to drop
        :param fail_silently: if ``True``, query will add a ``IF EXISTS`` clause

        .. note::
            Cascading drop tables are not supported at this time, so if a constraint
            exists that prevents a table being dropped, you will need to handle
            that in application logic.

    .. py:method:: add_column_sql(model_class, field_name)

        :param model_class: :py:class:`Model` which we are adding a column to
        :param string field_name: the name of the field we are adding

        :rtype: SQL suitable for adding the column

        .. note::
            Adding a non-null column to a table with rows may cause an IntegrityError.

    .. py:method:: rename_column_sql(model_class, field_name, new_name)

        :param model_class: :py:class:`Model` instance
        :param string field_name: the current name of the field
        :param string new_name: new name for the field

        :rtype: SQL suitable for renaming the column

        .. note::
            There must be a field instance named ``field_name`` at the time this SQL
            is generated.

        .. note:: SQLite does not support renaming columns

    .. py:method:: drop_column_sql(model_class, field_name)

        :param model_class: :py:class:`Model` instance
        :param string field_name: the name of the field to drop

        .. note:: SQLite does not support dropping columns

    .. py:method:: create_sequence(sequence_name)

        :param sequence_name: name of sequence to create

        .. note:: only works with database engines that support sequences

    .. py:method:: drop_sequence(sequence_name)

        :param sequence_name: name of sequence to drop

        .. note:: only works with database engines that support sequences

    .. py:method:: get_indexes_for_table(table)

        :param table: the name of table to introspect
        :rtype: a list of ``(index_name, is_unique)`` tuples

        .. warning::
            Not implemented -- implementations exist in subclasses

    .. py:method:: get_tables()

        :rtype: a list of table names in the database

        .. warning::
            Not implemented -- implementations exist in subclasses

    .. py:method:: sequence_exists(sequence_name)

        :rtype boolean:


.. py:class:: SqliteDatabase(Database)

    :py:class:`Database` subclass that communicates to the "sqlite3" driver

.. py:class:: MySQLDatabase(Database)

    :py:class:`Database` subclass that communicates to the "MySQLdb" driver

.. py:class:: PostgresqlDatabase(Database)

    :py:class:`Database` subclass that communicates to the "psycopg2" driver


BaseAdapter and its subclasses
------------------------------

.. py:class:: BaseAdapter

    The various subclasses of `BaseAdapter` provide a bridge between the high-
    level :py:class:`Database` abstraction and the underlying python libraries like
    psycopg2.  It also provides a way to unify the pythonic field types with
    the underlying column types used by the database engine.

    The `BaseAdapter` provides two types of mappings:
    - mapping between filter operations and their database equivalents
    - mapping between basic field types and their database column types

    The `BaseAdapter` also is the mechanism used by the :py:class:`Database` class to:
    - handle connections with the database
    - extract information from the database cursor

    .. py:attribute:: operations = {'eq': '= %s'}

        A mapping of query operation to SQL

    .. py:attribute:: interpolation = '%s'

        The string used by the driver to interpolate query parameters

    .. py:attribute:: sequence_support = False

        Whether the given backend supports sequences

    .. py:attribute:: reserved_tables = []

        Table names that are reserved by the backend -- if encountered in the
        application a warning will be issued.

    .. py:method:: get_field_types()

        :rtype: a dictionary mapping "user-friendly field type" to specific column type,
            e.g. ``{'string': 'VARCHAR', 'float': 'REAL', ... }``

    .. py:method:: get_field_type_overrides()

        :rtype: a dictionary similar to that returned by ``get_field_types()``.

        Provides a mechanism to override any number of field types without having
        to override all of them.

    .. py:method:: connect(database, **kwargs)

        :param database: string representing database name (or filename if using sqlite)
        :param kwargs: any keyword arguments to pass along to the database driver when connecting
        :rtype: a database connection

    .. py:method:: close(conn)

        :param conn: a database connection

        Close the given database connection

    .. py:method:: lookup_cast(lookup, value)

        :param lookup: a string representing the lookup type
        :param value: a python value that will be passed in to the lookup
        :rtype: a converted value appropriate for the given lookup

        Used as a hook when a specific lookup requires altering the given value,
        like for example when performing a LIKE query you may need to insert wildcards.

    .. py:method:: last_insert_id(cursor, model)

        :rtype: most recently inserted primary key

    .. py:method:: rows_affected(cursor)

        :rtype: number of rows affected by most recent query


.. py:class:: SqliteAdapter(BaseAdapter)

    Subclass of :py:class:`BaseAdapter` that works with the "sqlite3" driver

.. py:class:: MySQLAdapter(BaseAdapter)

    Subclass of :py:class:`BaseAdapter` that works with the "MySQLdb" driver

.. py:class:: PostgresqlAdapter(BaseAdapter)

    Subclass of :py:class:`BaseAdapter` that works with the "psycopg2" driver
