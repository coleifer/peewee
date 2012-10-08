.. _databases:

Databases
=========

Below the :py:class:`Model` level, peewee uses an abstraction for representing the database.  The
:py:class:`Database` is responsible for establishing and closing connections, making queries,
and gathering information from the database.  The :py:class:`Database` encapsulates functionality
specific to a given db driver.  For example difference in column types across database engines,
or support for certain features like sequences.  The database is responsible for smoothing out
the quirks of each backend driver to provide a consistent interface.

The :py:class:`Database` also uses a subclass of :py:class:`QueryCompiler` to generate
valid SQL.  The QueryCompiler maps the internal data structures used by peewee to
SQL statements.

For a high-level overview of working with transactions, check out the :ref:`transactions cookbook <working_with_transactions>`.

For notes on deferring instantiation of database, for example if loading configuration
at run-time, see the notes on :ref:`deferring initialization <deferring_initialization>`.

.. note::
    The internals of the :py:class:`Database` and :py:class:`QueryCompiler` will be
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

These methods are generally wrapped up in higher-level abstractions and exposed
by the :py:class:`Database`, so even if your driver doesn't
do these exactly you can still get a lot of mileage out of peewee.  An example
is the `apsw sqlite driver <http://code.google.com/p/apsw/>`_ in the "playhouse"
module.


Starting out
^^^^^^^^^^^^

The first thing is to provide a subclass of :py:class:`Database` that will open
a connection.

.. code-block:: python

    from peewee import Database
    import foodb # our fictional driver


    class FooDatabase(Database):
        def _connect(self, database, **kwargs):
            return foodb.connect(database, **kwargs)


Essential methods to override
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :py:class:`Database` provides a higher-level API and is responsible for executing queries,
creating tables and indexes, and introspecting the database to get lists of tables. The above
implementation is the absolute minimum needed, though some features will not work -- for best
results you will want to additionally add a method for extracting a list of tables
and indexes for a table from the database.  We'll pretend that ``FooDB`` is a lot like
MySQL and has special "SHOW" statements:

.. code-block:: python

    class FooDatabase(Database):
        def _connect(self, database, **kwargs):
            return foodb.connect(database, **kwargs)

        def get_tables(self):
            res = self.execute('SHOW TABLES;')
            return [r[0] for r in res.fetchall()]

        def get_indexes_for_table(self, table):
            res = self.execute('SHOW INDEXES IN %s;' % self.quote_name(table))
            rows = sorted([(r[2], r[1] == 0) for r in res.fetchall()])
            return rows


Other things the database handles that are not covered here include:

* last insert id and number of rows modified
* specifying characters used for string interpolation and quoting identifiers,
  for instance, sqlite uses "?" for interpolation and MySQL uses a backtick for quoting
* mapping operations such as "LIKE/ILIKE" to their database equivalent

Refer to the documentation below or the `source code <https://github.com/coleifer/peewee/blob/master/peewee.py>`_. for details.

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

    .. py:attribute:: compiler_class = QueryCompiler

        A class suitable for compiling queries

    .. py:attribute:: expr_overrides = {}

        A mapping of expression codes to string operators

    .. py:attribute:: field_overrides = {}

        A mapping of field types to database column types, e.g. ``{'primary_key': 'SERIAL'}``

    .. py:attribute:: for_update = False

        Whether the given backend supports selecting rows for update

    .. py:attribute:: interpolation = '%s'

        The string used by the driver to interpolate query parameters

    .. py:attribute:: op_overrides = {}

        A mapping of operation codes to string operations, e.g. ``{OP_LIKE: 'LIKE BINARY'}``

    .. py:attribute:: quote_char = '"'

        The string used by the driver to quote names

    .. py:attribute:: reserved_tables = []

        Table names that are reserved by the backend -- if encountered in the
        application a warning will be issued.

    .. py:attribute:: sequences = False

        Whether the given backend supports sequences

    .. py:attribute:: subquery_delete_same_table = True

        Whether the given backend supports deleting rows using a subquery
        that selects from the same table

    .. py:method:: __init__(database[, threadlocals=False[, autocommit=True[, **connect_kwargs]]])

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

    .. py:method:: get_compiler()

        :rtype: an instance of :py:class:`QueryCompiler`

    .. py:method:: set_autocommit(autocommit)

        :param autocommit: a boolean value indicating whether to turn on/off autocommit
            **for the current connection**

    .. py:method:: get_autocommit()

        :rtype: a boolean value indicating whether autocommit is on **for the current connection**

    .. py:method:: execute(query)

        :param: a query instance, such as a :py:class:`SelectQuery`
        :rtype: the resulting cursor

    .. py:method:: execute_sql(sql[, params=None[, require_commit=True]])

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

    .. py:method:: create_table(model_class)

        :param model_class: :py:class:`Model` class to create table for

    .. py:method:: create_index(model_class, fields[, unique=False])

        :param model_class: :py:class:`Model` table on which to create index
        :param fields: field(s) to create index on (either field instances or field names)
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
