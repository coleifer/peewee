.. _database:

Database
========

The Peewee :py:class:`Database` object represents a connection to a database.
The :py:class:`Database` class is instantiated with all the information needed
to open a connection to a database, and then can be used to:

* Open and close connections.
* Execute queries.
* Manage transactions (and savepoints).
* Introspect tables, columns, indexes, and constraints.
* Model integration

Peewee comes with support for SQLite, MySQL and Postgres. Each database class
provides some basic, database-specific configuration options.

.. code-block:: python

    from peewee import *

    # SQLite database using WAL journal mode and 64MB cache.
    sqlite_db = SqliteDatabase('/path/to/app.db', pragmas=(
        ('journal_mode', 'wal'),
        ('cache_size', -1024 * 64)))

    # Connect to a MySQL database on network.
    mysql_db = MySQLDatabase('my_app', user='app', password='db_password',
                             host='10.1.0.8', port=3316)

    # Connect to a Postgres database.
    pg_db = PostgresqlDatabase('my_app', user='postgres', password='secret',
                               host='10.1.0.9', port=5432)

Peewee provides advanced support for SQLite and Postgres via database-specific
extension modules. To use the extended-functionality, import the appropriate
database-specific module and use the database class provided:

.. code-block:: python

    from playhouse.sqlite_ext import SqliteExtDatabase

    # Use SQLite (will register a REGEXP function and set busy timeout to 3s).
    db = SqliteExtDatabase('/path/to/app.db', regexp_function=True, timeout=3,
                           pragmas=(('journal_mode', 'wal'),))


    from playhouse.postgres_ext import PostgresqlExtDatabase

    # Use Postgres (and register hstore extension).
    db = PostgresqlExtDatabase('my_app', user='postgres', register_hstore=True)

For more information on database extensions, see:

* :ref:`postgres_ext`
* :ref:`sqlite_ext`
* :ref:`sqlcipher_ext`
* :ref:`apsw_ext`
* :ref:`sqliteq`

Initializing a Database
-----------------------

The :py:class:`Database` initialization method expects the name of the database
as the first parameter. Subsequent keyword arguments are passed to the
underlying database driver when establishing the connection, allowing you to
pass vendor-specific parameters easily.

For instance, with Postgresql it is common to need to specify the ``host``,
``user`` and ``password`` when creating your connection. These are not standard
Peewee :py:class:`Database` parameters, so they will be passed directly back to
``psycopg2`` when creating connections:

.. code-block:: python

    db = PostgresqlDatabase(
        'database_name',  # Required by Peewee.
        user='postgres',  # Will be passed directly to psycopg2.
        password='secret',  # Ditto.
        host='db.mysite.com')  # Ditto.

As another example, the ``pymysql`` driver accepts a ``charset`` parameter
which is not a standard Peewee :py:class:`Database` parameter. To set this
value, simply pass in ``charset`` alongside your other values:

.. code-block:: python

    db = MySQLDatabase('database_name', user='www-data', charset='utf8mb4')

Consult your database driver's documentation for the available parameters:

* Postgres: `psycopg2 <http://initd.org/psycopg/docs/module.html#psycopg2.connect>`_
* MySQL: `MySQLdb <http://mysql-python.sourceforge.net/MySQLdb.html#some-mysql-examples>`_
* MySQL: `pymysql <https://github.com/PyMySQL/PyMySQL/blob/f08f01fe8a59e8acfb5f5add4a8fe874bec2a196/pymysql/connections.py#L494-L513>`_
* SQLite: `sqlite3 <https://docs.python.org/2/library/sqlite3.html#sqlite3.connect>`_

Using Postgresql
----------------

To connect to a Postgresql database, we will use
:py:class:`PostgresqlDatabase`. The first parameter is always the name of the
database, and after that you can specify arbitrary `psycopg2 parameters
<http://initd.org/psycopg/docs/module.html#psycopg2.connect>`_.

.. code-block:: python

    psql_db = PostgresqlDatabase('my_database', user='postgres')

    class BaseModel(Model):
        """A base model that will use our Postgresql database"""
        class Meta:
            database = psql_db

    class User(BaseModel):
        username = CharField()

The :ref:`playhouse` contains a :ref:`Postgresql extension module
<postgres_ext>` which provides many postgres-specific features such as:

* :ref:`Arrays <pgarrays>`
* :ref:`HStore <hstore>`
* :ref:`JSON <pgjson>`
* :ref:`Server-side cursors <server_side_cursors>`
* And more!

If you would like to use these awesome features, use the
:py:class:`PostgresqlExtDatabase` from the ``playhouse.postgres_ext`` module:

.. code-block:: python

    from playhouse.postgres_ext import PostgresqlExtDatabase

    psql_db = PostgresqlExtDatabase('my_database', user='postgres')

.. _using_sqlite:

Using SQLite
------------

To connect to a SQLite database, we will use :py:class:`SqliteDatabase`. The
first parameter is the filename containing the database, or the string
*:memory:* to create an in-memory database. After the database filename, you
can specify arbitrary `sqlite3 parameters
<https://docs.python.org/2/library/sqlite3.html#sqlite3.connect>`_.

.. code-block:: python

    sqlite_db = SqliteDatabase('my_app.db')

    class BaseModel(Model):
        """A base model that will use our Sqlite database."""
        class Meta:
            database = sqlite_db

    class User(BaseModel):
        username = CharField()
        # etc, etc

The :ref:`playhouse` contains a :ref:`SQLite extension module <sqlite_ext>`
which provides many SQLite-specific features such as :ref:`full-text search
<sqlite_fts>`, json extension support, and much, much more. If you would like
to use these awesome features, use the :py:class:`SqliteExtDatabase` from the
``playhouse.sqlite_ext`` module:

.. code-block:: python

    from playhouse.sqlite_ext import SqliteExtDatabase

    sqlite_db = SqliteExtDatabase('my_app.db', journal_mode='WAL')

.. _sqlite-pragma:

PRAGMA statements
^^^^^^^^^^^^^^^^^

SQLite allows run-time configuration of a number of parameters through
``PRAGMA`` statements (`documentation <https://www.sqlite.org/pragma.html>`_).
These statements are typically run against a new database connection. To run
one or more ``PRAGMA`` statements against new connections, you can specify them
as a list or tuple of 2-tuples containing the pragma name and value:

.. code-block:: python

    db = SqliteDatabase('my_app.db', pragmas=(
        ('journal_mode', 'WAL'),
        ('cache_size', 10000),
        ('mmap_size', 1024 * 1024 * 32),
    ))

PRAGMAs may also be configured dynamically using either the
:py:meth:`~SqliteDatabase.pragma` method or the special properties exposed on
the :py:class:`SqliteDatabase` object:

.. code-block:: python

    # Set cache size to 64MB for current connection.
    db.pragma('cache_size', -1024 * 64)

    # Same as above.
    db.cache_size = -1024 * 64

    # Read the value of several pragmas:
    print('cache_size:', db.cache_size)
    print('foreign_keys:', db.foreign_keys)
    print('journal_mode:', db.journal_mode)
    print('page_size:', db.page_size)

    # Set foreign_keys pragma on current connection *AND* on all
    # connections opened subsequently.
    db.pragma('foreign_keys', 1, permanent=True)

.. attention::
    Pragmas set using the :py:meth:`~SqliteDatabase.pragma` method, by default,
    do not persist after the connection is closed. To configure a pragma to be
    run whenever a connection is opened, specify ``permanent=True``.

.. _sqlite-user-functions:

User-defined functions
^^^^^^^^^^^^^^^^^^^^^^

SQLite can be extended with user-defined Python code. The
:py:class:`SqliteDatabase` class supports three types of user-defined
extensions:

* Functions - which take any number of parameters and return a single value.
* Aggregates - which aggregate parameters from multiple rows and return a
  single value.
* Collations - which describe how to sort some value.

.. note::
    For even more extension support, see :py:class:`SqliteExtDatabase`, which
    is in the ``playhouse.sqlite_ext`` module.

Example user-defined function:

.. code-block:: python

    db = SqliteDatabase('analytics.db')

    from urllib.parse import urlparse

    @db.func('hostname')
    def hostname(url):
        if url is not None:
            return urlparse(url).netloc

    # Call this function in our code:
    # The following finds the most common hostnames of referrers by count:
    query = (PageView
             .select(fn.hostname(PageView.referrer), fn.COUNT(PageView.id))
             .group_by(fn.hostname(PageView.referrer))
             .order_by(fn.COUNT(PageView.id).desc()))

Example user-defined aggregate:

.. code-block:: python

    from hashlib import md5

    @db.aggregate('md5')
    class MD5Checksum(object):
        def __init__(self):
            self.checksum = md5()

        def step(self, value):
            self.checksum.update(value.encode('utf-8'))

        def finalize(self):
            return self.checksum.hexdigest()

    # Usage:
    # The following computes an aggregate MD5 checksum for files broken
    # up into chunks and stored in the database.
    query = (FileChunk
             .select(FileChunk.filename, fn.MD5(FileChunk.data))
             .group_by(FileChunk.filename)
             .order_by(FileChunk.filename, FileChunk.sequence))

Example collation:

.. code-block:: python

    @db.collation('ireverse')
    def collate_reverse(s1, s2):
        # Case-insensitive reverse.
        s1, s2 = s1.lower(), s2.lower()
        return (s1 < s2) - (s1 > s2)  # Equivalent to -cmp(s1, s2)

    # To use this collation to sort books in reverse order...
    Book.select().order_by(collate_reverse.collation(Book.title))

    # Or...
    Book.select().order_by(Book.title.asc(collation='reverse'))

Example user-defined table-value function (see :py:class:`TableFunction`
and :py:class:`~SqliteDatabase.table_function`) for additional details:

.. code-block:: python

    from playhouse.sqlite_ext import TableFunction

    db = SqliteDatabase('my_app.db')

    @db.table_function('series')
    class Series(TableFunction):
        columns = ['value']
        params = ['start', 'stop', 'step']

        def initialize(self, start=0, stop=None, step=1):
            """
            Table-functions declare an initialize() method, which is
            called with whatever arguments the user has called the
            function with.
            """
            self.start = self.current = start
            self.stop = stop or float('Inf')
            self.step = step

        def iterate(self, idx):
            """
            Iterate is called repeatedly by the SQLite database engine
            until the required number of rows has been read **or** the
            function raises a `StopIteration` signalling no more rows
            are available.
            """
            if self.current > self.stop:
                raise StopIteration

            ret, self.current = self.current, self.current + self.step
            return (ret,)

    # Usage:
    cursor = db.execute_sql('SELECT * FROM series(?, ?, ?)', (0, 5, 2))
    for value, in cursor:
        print(value)

    # Prints:
    # 0
    # 2
    # 4

For more information, see:

* :py:meth:`SqliteDatabase.func`
* :py:meth:`SqliteDatabase.aggregate`
* :py:meth:`SqliteDatabase.collation`
* :py:meth:`SqliteDatabase.table_function`
* For even more SQLite extensions, see :ref:`sqlite_ext`

.. _sqlite-locking:

Set locking mode for transaction
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

SQLite transactions can be opened in three different modes:

* *Deferred* (**default**) - only acquires lock when a read or write is
  performed. The first read creates a `shared lock <https://sqlite.org/lockingv3.html#locking>`_
  and the first write creates a `reserved lock <https://sqlite.org/lockingv3.html#locking>`_.
  Because the acquisition of the lock is deferred until actually needed, it is
  possible that another thread or process could create a separate transaction
  and write to the database after the BEGIN on the current thread has executed.
* *Immediate* - a `reserved lock <https://sqlite.org/lockingv3.html#locking>`_
  is acquired immediately. In this mode, no other database may write to the
  database or open an *immediate* or *exclusive* transaction. Other processes
  can continue to read from the database, however.
* *Exclusive* - opens an `exclusive lock <https://sqlite.org/lockingv3.html#locking>`_
  which prevents all (except for read uncommitted) connections from accessing
  the database until the transaction is complete.

Example specifying the locking mode:

.. code-block:: python

    db = SqliteDatabase('app.db')

    with db.atomic('EXCLUSIVE'):
        do_something()


    @db.atomic('IMMEDIATE')
    def some_other_function():
        # This function is wrapped in an "IMMEDIATE" transaction.
        do_something_else()

For more information, see the SQLite `locking documentation <https://sqlite.org/lockingv3.html#locking>`_.
To learn more about transactions in Peewee, see the :ref:`transactions`
documentation.

APSW, an Advanced SQLite Driver
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Peewee also comes with an alternate SQLite database that uses :ref:`apsw`, an
advanced Python SQLite driver. More information on APSW can be obtained on the
`APSW project website <https://code.google.com/p/apsw/>`_. APSW provides
special features like:

* Virtual tables, virtual file-systems, Blob I/O, backups and file control.
* Connections can be shared across threads without any additional locking.
* Transactions are managed explicitly by your code.
* Unicode is handled *correctly*.
* APSW is faster that the standard library sqlite3 module.
* Exposes pretty much the entire SQLite C API to your Python app.

If you would like to use APSW, use the :py:class:`APSWDatabase` from the
`apsw_ext` module:

.. code-block:: python

    from playhouse.apsw_ext import APSWDatabase

    apsw_db = APSWDatabase('my_app.db')

.. _using_mysql:

Using MySQL
-----------

To connect to a MySQL database, we will use :py:class:`MySQLDatabase`. After
the database name, you can specify arbitrary connection parameters that will be
passed back to the driver (either MySQLdb or pymysql).

.. code-block:: python

    mysql_db = MySQLDatabase('my_database')

    class BaseModel(Model):
        """A base model that will use our MySQL database"""
        class Meta:
            database = mysql_db

    class User(BaseModel):
        username = CharField()
        # etc, etc

Error 2006: MySQL server has gone away
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This particular error can occur when MySQL kills an idle database connection.
This typically happens with web apps that do not explicitly manage database
connections. What happens is your application starts, a connection is opened to
handle the first query that executes, and, since that connection is never
closed, it remains open, waiting for more queries.

To fix this, make sure you are explicitly connecting to the database when you
need to execute queries, and close your connection when you are done. In a
web-application, this typically means you will open a connection when a request
comes in, and close the connection when you return a response.

See the :ref:`framework-integration` section for examples of configuring common
web frameworks to manage database connections.

Connecting using a Database URL
-------------------------------

The playhouse module :ref:`db_url` provides a helper :py:func:`connect` function that accepts a database URL and returns a :py:class:`Database` instance.

Example code:

.. code-block:: python

      import os

      from peewee import *
      from playhouse.db_url import connect

      # Connect to the database URL defined in the environment, falling
      # back to a local Sqlite database if no database URL is specified.
      db = connect(os.environ.get('DATABASE') or 'sqlite:///default.db')

      class BaseModel(Model):
          class Meta:
              database = db

Example database URLs:

* *sqlite:///my_database.db* will create a :py:class:`SqliteDatabase` instance for the file ``my_database.db`` in the current directory.
* *sqlite:///:memory:* will create an in-memory :py:class:`SqliteDatabase` instance.
* *postgresql://postgres:my_password@localhost:5432/my_database* will create a :py:class:`PostgresqlDatabase` instance. A username and password are provided, as well as the host and port to connect to.
* *mysql://user:passwd@ip:port/my_db* will create a :py:class:`MySQLDatabase` instance for the local MySQL database *my_db*.
* :ref:`More examples in the db_url documentation <db_url>`.

.. _deferring_initialization:

Run-time database configuration
-------------------------------

Sometimes the database connection settings are not known until run-time, when
these values may be loaded from a configuration file or the environment. In
these cases, you can *defer* the initialization of the database by specifying
``None`` as the database_name.

.. code-block:: python

    database = SqliteDatabase(None)  # Un-initialized database.

    class SomeModel(Model):
        class Meta:
            database = database

If you try to connect or issue any queries while your database is uninitialized
you will get an exception:

.. code-block:: python

    >>> database.connect()
    Exception: Error, database not properly initialized before opening connection

To initialize your database, call the :py:meth:`~Database.init` method with the
database name and any additional keyword arguments:

.. code-block:: python

    database_name = raw_input('What is the name of the db? ')
    database.init(database_name, host='localhost', user='postgres')

For even more control over initializing your database, see the next section,
:ref:`dynamic_db`.

.. _dynamic_db:

Dynamically defining a database
-------------------------------

For even more control over how your database is defined/initialized, you can
use the :py:class:`Proxy` helper. :py:class:`Proxy` objects act as a
placeholder, and then at run-time you can swap it out for a different object.
In the example below, we will swap out the database depending on how the app is
configured:

.. code-block:: python

    database_proxy = Proxy()  # Create a proxy for our db.

    class BaseModel(Model):
        class Meta:
            database = database_proxy  # Use proxy for our DB.

    class User(BaseModel):
        username = CharField()

    # Based on configuration, use a different database.
    if app.config['DEBUG']:
        database = SqliteDatabase('local.db')
    elif app.config['TESTING']:
        database = SqliteDatabase(':memory:')
    else:
        database = PostgresqlDatabase('mega_production_db')

    # Configure our proxy to use the db we specified in config.
    database_proxy.initialize(database)

.. warning::
    Only use this method if your actual database driver varies at run-time. For
    instance, if your tests and local dev environment run on SQLite, but your
    deployed app uses PostgreSQL, you can use the :py:class:`Proxy` to swap out
    engines at run-time.

    However, if it is only connection values that vary at run-time, such as the
    path to the database file, or the database host, you should instead use
    :py:meth:`Database.init`. See :ref:`deferring_initialization` for more
    details.

Connection Management
---------------------

To open a connection to a database, use the :py:meth:`Database.connect` method:

.. code-block:: pycon

    >>> db = SqliteDatabase(':memory:')  # In-memory SQLite database.
    >>> db.connect()
    True

If we try to call ``connect()`` on an already-open database, we get a
:py:class:`OperationalError`:

.. code-block:: pycon

    >>> db.connect()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "/home/charles/pypath/peewee.py", line 2390, in connect
        raise OperationalError('Connection already opened.')
    peewee.OperationalError: Connection already opened.

To prevent this exception from being raised, we can call ``connect()`` with an
additional argument, ``reuse_if_open``:

.. code-block:: pycon

    >>> db.close()  # Close connection.
    True
    >>> db.connect()
    True
    >>> db.connect(reuse_if_open=True)
    False

Note that the call to ``connect()`` returns ``False`` if the database
connection was already open.

To close a connection, use the :py:meth:`Database.close` method:

.. code-block:: pycon

    >>> db.close()
    True

Calling ``close()`` on an already-closed connection will not result in an
exception, but will return ``False``:

.. code-block:: pycon

    >>> db.connect()  # Open connection.
    True
    >>> db.close()  # Close connection.
    True
    >>> db.close()  # Connection already closed, returns False.
    False

You can test whether the database is closed using the
:py:meth:`Database.is_closed` method:

.. code-block:: pycon

    >>> db.is_closed()
    True

A note of caution
^^^^^^^^^^^^^^^^^

Although it is not necessary to explicitly connect to the database before using
it, managing connections explicitly is considered a **best practice**. For
example, if the connection fails, the exception will be caught when the
connection is being opened, rather than some arbitrary time later when a query
is executed. Furthermore, if you are using a :ref:`connection pool <pool>`, it
is necessary to call :py:meth:`~Database.connect` and
:py:meth:`~Database.close` to ensure connections are recycled properly.

Thread Safety
^^^^^^^^^^^^^

Peewee keeps track of the connection state using thread-local storage, making
the Peewee :py:class:`Database` object safe to use with multiple threads. Each
thread will have it's own connection, and conversely, any given thread will
only have a single connection open at a given time.

Context managers
^^^^^^^^^^^^^^^^

The database object itself can be used as a context-manager, which opens a
connection for the duration of the wrapped block of code. Additionally, a
transaction is opened at the start of the wrapped block and committed before
the connection is closed (unless an error occurs, in which case the transaction
is rolled back).

.. code-block:: pycon

    >>> db.is_closed()
    True
    >>> with db:
    ...     print(db.is_closed())  # db is open inside context manager.
    ...
    False
    >>> db.is_closed()  # db is closed.
    True

If you want to manage transactions separately, you can use the
:py:meth:`Database.connection_context` context manager.

.. code-block:: pycon

    >>> with db.connection_context():
    ...     # db connection is open.
    ...     pass
    ...
    >>> db.is_closed()  # db connection is closed.
    True

The ``connection_context()`` method can also be used as a decorator:

.. code-block:: python

    @db.connection_context()
    def prepare_database():
        # DB connection will be managed by the decorator, which opens
        # a connection, calls function, and closes upon returning.
        db.create_tables(MODELS)  # Create schema.
        load_fixture_data(db)


DB-API Connection Object
^^^^^^^^^^^^^^^^^^^^^^^^

To obtain a reference to the underlying DB-API 2.0 connection, use the
:py:meth:`Database.connection` method. This method will return the
currently-open connection object, if one exists, otherwise it will open a new
connection.

.. code-block:: pycon

    >>> db.connection()
    <sqlite3.Connection object at 0x7f94e9362f10>

.. _connection_pooling:

Connection Pooling
------------------

Connection pooling is provided by the :ref:`pool module <pool>`, included in
the :ref:`playhouse <playhouse>` extensions library. The pool supports:

* Timeout after which connections will be recycled.
* Upper bound on the number of open connections.

.. code-block:: python

    from playhouse.pool import PooledPostgresqlExtDatabase

    db = PooledPostgresqlExtDatabase(
        'my_database',
        max_connections=8,
        stale_timeout=300,
        user='postgres')

    class BaseModel(Model):
        class Meta:
            database = db

The following pooled database classes are available:

* :py:class:`PooledPostgresqlDatabase`
* :py:class:`PooledPostgresqlExtDatabase`
* :py:class:`PooledMySQLDatabase`
* :py:class:`PooledSqliteDatabase`
* :py:class:`PooledSqliteExtDatabase`

For an in-depth discussion of peewee's connection pool, see the :ref:`pool`
section of the :ref:`playhouse <playhouse>` documentation.

.. _testing:

Testing Peewee Applications
---------------------------

When writing tests for an application that uses Peewee, it may be desirable to
use a special database for tests. Another common practice is to run tests
against a clean database, which means ensuring tables are empty at the start of
each test.

To bind your models to a database at run-time, you can use the following
methods:

* :py:meth:`Database.bind_ctx`, which returns a context-manager that will bind
  the given models to the database instance for the duration of the wrapped
  block.
* :py:meth:`Model.bind_ctx`, which likewise returns a context-manager that
  binds the model (and optionally its dependencies) to the given database for
  the duration of the wrapped block.
* :py:meth:`Database.bind`, which is a one-time operation that binds the models
  (and optionally its dependencies) to the given database.
* :py:meth:`Model.bind`, which is a one-time operation that binds the model
  (and optionally its dependencies) to the given database.

Depending on your use-case, one of these options may make more sense. For the
examples below, I will use :py:meth:`Model.bind`.

Example test-case setup:

.. code-block:: python

    # tests.py
    import unittest
    from my_app.models import EventLog, Relationship, Tweet, User

    MODELS = [User, Tweet, EventLog, Relationship]

    # use an in-memory SQLite for tests.
    test_db = SqliteDatabase(':memory:')

    class BaseTestCase(unittest.TestCase):
        def setUp(self):
            # Bind model classes to test db. Since we have a complete list of
            # all models, we do not need to recursively bind dependencies.
            for model in MODELS:
                model.bind(test_db, bind_refs=False, bind_backrefs=False)

            test_db.connect()
            test_db.create_tables(MODELS)

        def tearDown(self):
            # Not strictly necessary since SQLite in-memory databases only live
            # for the duration of the connection, and in the next step we close
            # the connection...but a good practice all the same.
            test_db.drop_tables(MODELS)

            # Close connection to db.
            test_db.close()

            # If we wanted, we could re-bind the models to their original
            # database here. But for tests this is probably not necessary.

As an aside, and speaking from experience, I recommend testing your application
using the same database backend you use in production, so as to avoid any
potential compatibility issues.

If you'd like to see some more examples of how to run tests using Peewee, check
out Peewee's own `test-suite <https://github.com/coleifer/peewee/tree/master/tests>`_.

Async with Gevent
-----------------

`gevent <http://www.gevent.org/>` is recommended for doing asynchronous i/o
with Postgresql or MySQL. Reasons I prefer gevent:

* No need for special-purpose "loop-aware" re-implementations of *everything*.
  Third-party libraries using asyncio usually have to re-implement layers and
  layers of code as well as re-implementing the protocols themselves.
* Gevent allows you to write your application in normal, clean, idiomatic
  Python. No need to litter every line with "async", "await" and other noise.
  No callbacks. No cruft.
* Gevent works with both Python 2 *and* Python 3.
* Gevent is *Pythonic*. Asyncio is an un-pythonic abomination.

Besides monkey-patching socket, no special steps are required if you are using
**MySQL** with a pure Python driver like `pymysql <https://github.com/PyMySQL/PyMySQL>`_
or are using `mysql-connector <https://dev.mysql.com/doc/connector-python/en/>`_
in pure-python mode. MySQL drivers written in C will require special
configuration which is beyond the scope of this document.

For **Postgres** and `psycopg2 <http://initd.org/psycopg>`_, which is a C
extension, you can use the following code snippet to register event hooks that
will make your connection async:

.. code-block:: python

    from gevent.socket import wait_read, wait_write
    from psycopg2 import extensions

    # Call this function after monkey-patching socket (etc).
    def patch_psycopg2():
        extensions.set_wait_callback(_psycopg2_gevent_callback)

    def _psycopg2_gevent_callback(conn, timeout=None):
        while True:
            state = conn.poll()
            if state == extensions.POLL_OK:
                break
            elif state == extensions.POLL_READ:
                wait_read(conn.fileno(), timeout=timeout)
            elif state == extensions.POLL_WRITE:
                wait_write(conn.fileno(), timeout=timeout)
            else:
                raise ValueError('poll() returned unexpected result')

**SQLite**, because it is embedded in the Python application itself, does not
do any socket operations that would be a candidate for non-blocking. Async has
no effect one way or the other on SQLite databases.

.. _framework-integration:

Framework Integration
---------------------

For web applications, it is common to open a connection when a request is
received, and to close the connection when the response is delivered. In this
section I will describe how to add hooks to your web app to ensure the database
connection is handled properly.

These steps will ensure that regardless of whether you're using a simple SQLite
database, or a pool of multiple Postgres connections, peewee will handle the
connections correctly.

.. note::
    Applications that receive lots of traffic may benefit from using a
    :ref:`connection pool <pool>` to mitigate the cost of setting up and
    tearing down connections on every request.

Flask
^^^^^

Flask and peewee are a great combo and my go-to for projects of any size. Flask
provides two hooks which we will use to open and close our db connection. We'll
open the connection when a request is received, then close it when the response
is returned.

.. code-block:: python

    from flask import Flask
    from peewee import *

    database = SqliteDatabase('my_app.db')
    app = Flask(__name__)

    # This hook ensures that a connection is opened to handle any queries
    # generated by the request.
    @app.before_request
    def _db_connect():
        database.connect()

    # This hook ensures that the connection is closed when we've finished
    # processing the request.
    @app.teardown_request
    def _db_close(exc):
        if not database.is_closed():
            database.close()

Django
^^^^^^

While it's less common to see peewee used with Django, it is actually very easy
to use the two. To manage your peewee database connections with Django, the
easiest way in my opinion is to add a middleware to your app. The middleware
should be the very first in the list of middlewares, to ensure it runs first
when a request is handled, and last when the response is returned.

If you have a django project named *my_blog* and your peewee database is
defined in the module ``my_blog.db``, you might add the following middleware
class:

.. code-block:: python

    # middleware.py
    from my_blog.db import database  # Import the peewee database instance.


    class PeeweeConnectionMiddleware(object):
        def process_request(self, request):
            database.connect()

        def process_response(self, request, response):
            if not database.is_closed():
                database.close()
            return response

To ensure this middleware gets executed, add it to your ``settings`` module:

.. code-block:: python

    # settings.py
    MIDDLEWARE_CLASSES = (
        # Our custom middleware appears first in the list.
        'my_blog.middleware.PeeweeConnectionMiddleware',

        # These are the default Django 1.7 middlewares. Yours may differ,
        # but the important this is that our Peewee middleware comes first.
        'django.middleware.common.CommonMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
    )

    # ... other Django settings ...

Bottle
^^^^^^

I haven't used bottle myself, but looking at the documentation I believe the
following code should ensure the database connections are properly managed:

.. code-block:: python

    # app.py
    from bottle import hook  #, route, etc, etc.
    from peewee import *

    db = SqliteDatabase('my-bottle-app.db')

    @hook('before_request')
    def _connect_db():
        db.connect()

    @hook('after_request')
    def _close_db():
        if not db.is_closed():
            db.close()

    # Rest of your bottle app goes here.

Web.py
^^^^^^

See the documentation for
`application processors <http://webpy.org/cookbook/application_processors>`_.

.. code-block:: python

    db = SqliteDatabase('my_webpy_app.db')

    def connection_processor(handler):
        db.connect()
        try:
            return handler()
        finally:
            if not db.is_closed():
                db.close()

    app.add_processor(connection_processor)

Tornado
^^^^^^^

It looks like Tornado's ``RequestHandler`` class implements two hooks which can
be used to open and close connections when a request is handled.

.. code-block:: python

    from tornado.web import RequestHandler

    db = SqliteDatabase('my_db.db')

    class PeeweeRequestHandler(RequestHandler):
        def prepare(self):
            db.connect()
            return super(PeeweeRequestHandler, self).prepare()

        def on_finish(self):
            if not db.is_closed():
                db.close()
            return super(PeeweeRequestHandler, self).on_finish()

In your app, instead of extending the default ``RequestHandler``, now you can
extend ``PeeweeRequestHandler``.

Note that this does not address how to use peewee asynchronously with Tornado
or another event loop.

Wheezy.web
^^^^^^^^^^

The connection handling code can be placed in a `middleware
<https://pythonhosted.org/wheezy.http/userguide.html#middleware>`_.

.. code-block:: python

    def peewee_middleware(request, following):
        db.connect()
        try:
            response = following(request)
        finally:
            if not db.is_closed():
                db.close()
        return response

    app = WSGIApplication(middleware=[
        lambda x: peewee_middleware,
        # ... other middlewares ...
    ])

Thanks to GitHub user *@tuukkamustonen* for submitting this code.

Falcon
^^^^^^

The connection handling code can be placed in a `middleware component
<https://falcon.readthedocs.io/en/stable/api/middleware.html>`_.

.. code-block:: python

    import falcon
    from peewee import *

    database = SqliteDatabase('my_app.db')

    class PeeweeConnectionMiddleware(object):
        def process_request(self, req, resp):
            database.connect()

        def process_response(self, req, resp, resource):
            if not database.is_closed():
                database.close()

    application = falcon.API(middleware=[
        PeeweeConnectionMiddleware(),
        # ... other middlewares ...
    ])

Pyramid
^^^^^^^

Set up a Request factory that handles database connection lifetime as follows:

.. code-block:: python

    from pyramid.request import Request

    db = SqliteDatabase('pyramidapp.db')

    class MyRequest(Request):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            db.connect()
            self.add_finished_callback(self.finish)

        def finish(self, request):
            if not db.is_closed():
                db.close()

In your application `main()` make sure `MyRequest` is used as
`request_factory`:

.. code-block:: python

    def main(global_settings, **settings):
        config = Configurator(settings=settings, ...)
        config.set_request_factory(MyRequest)

CherryPy
^^^^^^^^

See `Publish/Subscribe pattern
<http://docs.cherrypy.org/en/latest/extend.html#publish-subscribe-pattern>`_.

.. code-block:: python

    def _db_connect():
        db.connect()

    def _db_close():
        if not db.is_closed():
            db.close()

    cherrypy.engine.subscribe('before_request', _db_connect)
    cherrypy.engine.subscribe('after_request', _db_close)

Sanic
^^^^^

In Sanic, the connection handling code can be placed in the request and
response middleware `sanic middleware <http://sanic.readthedocs.io/en/latest/sanic/middleware.html>`_.

.. code-block:: python

    # app.py
    @app.middleware('request')
    async def handle_request(request):
        db.connect()

    @app.middleware('response')
    async def handle_response(request, response):
        if not db.is_closed():
            db.close()

Other frameworks
^^^^^^^^^^^^^^^^

Don't see your framework here? Please `open a GitHub ticket
<https://github.com/coleifer/peewee/issues/new>`_ and I'll see about adding a
section, or better yet, submit a documentation pull-request.

Executing Queries
-----------------

SQL queries will typically be executed by calling ``execute()`` on a query
constructed using the query-builder APIs (or by simply iterating over a query
object in the case of a :py:class:`Select` query). For cases where you wish to
execute SQL directly, you can use the :py:meth:`Database.execute_sql` method.

.. code-block:: python

    db = SqliteDatabase('my_app.db')
    db.connect()

    # Example of executing a simple query and ignoring the results.
    db.execute_sql("ATTACH DATABASE ':memory:' AS cache;")

    # Example of iterating over the results of a query using the cursor.
    cursor = db.execute_sql('SELECT * FROM users WHERE status = ?', (ACTIVE,))
    for row in cursor.fetchall():
        # Do something with row, which is a tuple containing column data.
        pass

Managing Transactions
---------------------

Peewee provides several interfaces for working with transactions. The most
general is the :py:meth:`Database.atomic` method, which also supports nested
transactions. :py:meth:`~Database.atomic` blocks will be run in a transaction
or savepoint, depending on the level of nesting.

If an exception occurs in a wrapped block, the current transaction/savepoint
will be rolled back. Otherwise the statements will be committed at the end of
the wrapped block.

.. note::
    While inside a block wrapped by the :py:meth:`~Database.atomic` context
    manager, you can explicitly rollback or commit at any point by calling
    :py:meth:`Transaction.rollback` or :py:meth:`Transaction.commit`. When you
    do this inside a wrapped block of code, a new transaction will be started
    automatically.

    .. code-block:: python

        with db.atomic() as transaction:  # Opens new transaction.
            try:
                save_some_objects()
            except ErrorSavingData:
                # Because this block of code is wrapped with "atomic", a
                # new transaction will begin automatically after the call
                # to rollback().
                transaction.rollback()
                error_saving = True

            create_report(error_saving=error_saving)
            # Note: no need to call commit. Since this marks the end of the
            # wrapped block of code, the `atomic` context manager will
            # automatically call commit for us.

.. note::
    :py:meth:`~Database.atomic` can be used as either a **context manager** or
    a **decorator**.

Context manager
^^^^^^^^^^^^^^^

Using ``atomic`` as context manager:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    with db.atomic() as txn:
        # This is the outer-most level, so this block corresponds to
        # a transaction.
        User.create(username='charlie')

        with db.atomic() as nested_txn:
            # This block corresponds to a savepoint.
            User.create(username='huey')

            # This will roll back the above create() query.
            nested_txn.rollback()

        User.create(username='mickey')

    # When the block ends, the transaction is committed (assuming no error
    # occurs). At that point there will be two users, "charlie" and "mickey".

You can use the ``atomic`` method to perform *get or create* operations as
well:

.. code-block:: python

    try:
        with db.atomic():
            user = User.create(username=username)
        return 'Success'
    except peewee.IntegrityError:
        return 'Failure: %s is already in use.' % username

Decorator
^^^^^^^^^

Using ``atomic`` as a decorator:

.. code-block:: python

    @db.atomic()
    def create_user(username):
        # This statement will run in a transaction. If the caller is already
        # running in an `atomic` block, then a savepoint will be used instead.
        return User.create(username=username)

    create_user('charlie')

Nesting Transactions
^^^^^^^^^^^^^^^^^^^^

:py:meth:`~Database.atomic` provides transparent nesting of transactions. When
using :py:meth:`~Database.atomic`, the outer-most call will be wrapped in a
transaction, and any nested calls will use savepoints.

.. code-block:: python

    with db.atomic() as txn:
        perform_operation()

        with db.atomic() as nested_txn:
            perform_another_operation()

Peewee supports nested transactions through the use of savepoints (for more
information, see :py:meth:`~Database.savepoint`).

Explicit transaction
^^^^^^^^^^^^^^^^^^^^

If you wish to explicitly run code in a transaction, you can use
:py:meth:`~Database.transaction`. Like :py:meth:`~Database.atomic`,
:py:meth:`~Database.transaction` can be used as a context manager or as a
decorator.

If an exception occurs in a wrapped block, the transaction will be rolled back.
Otherwise the statements will be committed at the end of the wrapped block.

.. code-block:: python

    db = SqliteDatabase(':memory:')

    with db.transaction() as txn:
        # Delete the user and their associated tweets.
        user.delete_instance(recursive=True)

Transactions can be explicitly committed or rolled-back within the wrapped
block. When this happens, a new transaction will be started.

.. code-block:: python

    with db.transaction() as txn:
        User.create(username='mickey')
        txn.commit()  # Changes are saved and a new transaction begins.
        User.create(username='huey')

        # Roll back. "huey" will not be saved, but since "mickey" was already
        # committed, that row will remain in the database.
        txn.rollback()

    with db.transaction() as txn:
        User.create(username='whiskers')
        # Roll back changes, which removes "whiskers".
        txn.rollback()

        # Create a new row for "mr. whiskers" which will be implicitly committed
        # at the end of the `with` block.
        User.create(username='mr. whiskers')

.. note::
    If you attempt to nest transactions with peewee using the
    :py:meth:`~Database.transaction` context manager, only the outer-most
    transaction will be used. However if an exception occurs in a nested block,
    this can lead to unpredictable behavior, so it is strongly recommended that
    you use :py:meth:`~Database.atomic`.

Explicit Savepoints
^^^^^^^^^^^^^^^^^^^

Just as you can explicitly create transactions, you can also explicitly create
savepoints using the :py:meth:`~Database.savepoint` method. Savepoints must
occur within a transaction, but can be nested arbitrarily deep.

.. code-block:: python

    with db.transaction() as txn:
        with db.savepoint() as sp:
            User.create(username='mickey')

        with db.savepoint() as sp2:
            User.create(username='zaizee')
            sp2.rollback()  # "zaizee" will not be saved, but "mickey" will be.

.. warning::
    If you manually commit or roll back a savepoint, a new savepoint **will
    not** automatically be created. This differs from the behavior of
    :py:class:`transaction`, which will automatically open a new transaction
    after manual commit/rollback.

Autocommit Mode
^^^^^^^^^^^^^^^

By default, Peewee operates in *autocommit mode*, such that any statements
executed outside of a transaction are run in their own transaction. To group
multiple statements into a transaction, Peewee provides the
:py:meth:`~Database.atomic` context-manager/decorator. This should cover all
use-cases, but in the unlikely event you want to temporarily disable Peewee's
transaction management completely, you can use the
:py:meth:`Database.manual_commit` context-manager/decorator.

Here is how you might emulate the behavior of the
:py:meth:`~Database.transaction` context manager:

.. code-block:: python

    with db.manual_commit():
        db.begin()  # Have to begin transaction explicitly.
        try:
            user.delete_instance(recursive=True)
        except:
            db.rollback()  # Rollback! An error occurred.
            raise
        else:
            try:
                db.commit()  # Commit changes.
            except:
                db.rollback()
                raise

Again -- I don't anticipate anyone needing this, but it's here just in case.

.. _database-errors:

Database Errors
---------------

The Python DB-API 2.0 spec describes `several types of exceptions <https://www.python.org/dev/peps/pep-0249/#exceptions>`_. Because most database drivers have their own implementations of these exceptions, Peewee simplifies things by providing its own wrappers around any implementation-specific exception classes. That way, you don't need to worry about importing any special exception classes, you can just use the ones from peewee:

* ``DatabaseError``
* ``DataError``
* ``IntegrityError``
* ``InterfaceError``
* ``InternalError``
* ``NotSupportedError``
* ``OperationalError``
* ``ProgrammingError``

.. note:: All of these error classes extend ``PeeweeException``.

Logging queries
---------------

All queries are logged to the *peewee* namespace using the standard library ``logging`` module. Queries are logged using the *DEBUG* level.  If you're interested in doing something with the queries, you can simply register a handler.

.. code-block:: python

    # Print all queries to stderr.
    import logging
    logger = logging.getLogger('peewee')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

Adding a new Database Driver
----------------------------

Peewee comes with built-in support for Postgres, MySQL and SQLite. These
databases are very popular and run the gamut from fast, embeddable databases to
heavyweight servers suitable for large-scale deployments.  That being said,
there are a ton of cool databases out there and adding support for your
database-of-choice should be really easy, provided the driver supports the
`DB-API 2.0 spec <http://www.python.org/dev/peps/pep-0249/>`_.

The db-api 2.0 spec should be familiar to you if you've used the standard
library sqlite3 driver, psycopg2 or the like. Peewee currently relies on a
handful of parts:

* `Connection.commit`
* `Connection.execute`
* `Connection.rollback`
* `Cursor.description`
* `Cursor.fetchone`

These methods are generally wrapped up in higher-level abstractions and exposed
by the :py:class:`Database`, so even if your driver doesn't do these exactly
you can still get a lot of mileage out of peewee.  An example is the `apsw
sqlite driver <http://code.google.com/p/apsw/>`_ in the "playhouse" module.

The first thing is to provide a subclass of :py:class:`Database` that will open
a connection.

.. code-block:: python

    from peewee import Database
    import foodb  # Our fictional DB-API 2.0 driver.


    class FooDatabase(Database):
        def _connect(self, database, **kwargs):
            return foodb.connect(database, **kwargs)

The :py:class:`Database` provides a higher-level API and is responsible for
executing queries, creating tables and indexes, and introspecting the database
to get lists of tables. The above implementation is the absolute minimum
needed, though some features will not work -- for best results you will want to
additionally add a method for extracting a list of tables and indexes for a
table from the database.  We'll pretend that ``FooDB`` is a lot like MySQL and
has special "SHOW" statements:

.. code-block:: python

    class FooDatabase(Database):
        def _connect(self, database, **kwargs):
            return foodb.connect(database, **kwargs)

        def get_tables(self):
            res = self.execute('SHOW TABLES;')
            return [r[0] for r in res.fetchall()]

Other things the database handles that are not covered here include:

* :py:meth:`~Database.last_insert_id` and :py:meth:`~Database.rows_affected`
* :py:attr:`~Database.interpolation` and :py:attr:`~Database.quote_char`
* :py:attr:`~Database.op_overrides` for mapping operations such as "LIKE/ILIKE" to their database equivalent

Refer to the :py:class:`Database` API reference or the `source code
<https://github.com/coleifer/peewee/blob/master/peewee.py>`_. for details.

.. note::
    If your driver conforms to the DB-API 2.0 spec, there shouldn't be much
    work needed to get up and running.

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
