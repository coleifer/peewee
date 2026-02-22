.. _database:

Database
========

The Peewee :class:`Database` object represents a connection to a database.
The :class:`Database` class is instantiated with all the information needed
to connect to a database.

Database responsibilities:

* Connection lifecycle.
* Execute queries.
* Manage database schema.
* :ref:`Manage transactions <transactions>`.

Peewee supports:

* SQLite - :class:`SqliteDatabase` using the standard library ``sqlite3``.

  .. code-block:: python

     # SQLite database (use WAL journal mode and 64MB cache).
     db = SqliteDatabase('/path/to/app.db', pragmas={
         'journal_mode': 'wal',
         'cache_size': -1024 * 64})

* Postgresql - :class:`PostgresqlDatabase` using ``psycopg2`` or ``psycopg3``.

  .. code-block:: python

     db = PostgresqlDatabase(
         'my_app',
         user='postgres',
         password='secret',
         host='10.1.0.9',
         port=5432)

* MySQL and MariaDB - :class:`MySQLDatabase` using ``pymysql``.

  .. code-block:: python

     db = MySQLDatabase(
         'my_app',
         user='app',
         password='db_password',
         host='10.1.0.8',
         port=3306)


Using SQLite
------------

To connect to a SQLite database, use :class:`SqliteDatabase`. The first
parameter is the filename containing the database, or the string ``':memory:'``
to create an in-memory database.

After the database filename specify pragmas or other `sqlite3 parameters <https://docs.python.org/3/library/sqlite3.html#sqlite3.connect>`__.

.. code-block:: python

   db = SqliteDatabase('my_app.db', pragmas={'journal_mode': 'wal'})

   class BaseModel(Model):
       """Base model that will use our Sqlite database."""
       class Meta:
           database = db

   class User(BaseModel):
       username = TextField()
       ...

.. seealso:: :ref:`advanced-sqlite`

Using Postgresql
----------------

To use Peewee with Postgresql install ``psycopg2`` or ``psycopg3``:

.. code-block:: shell

   $ pip install "psycopg2-binary"  # Psycopg2.

   $ pip install "psycopg[binary]"  # Psycopg3.

To connect to a Postgresql database, use :py:class:`PostgresqlDatabase`.
The first parameter is always the name of the database.

After the database name specify additional `psycopg2 <https://www.psycopg.org/docs/module.html#psycopg2.connect>`__
or `psycopg3 <https://www.psycopg.org/psycopg3/docs/api/module.html#psycopg.connect>`__
connection parameters:

.. code-block:: python

   db = PostgresqlDatabase(
       'my_database',
       user='postgres',
       host='10.8.0.1',
       port=5432)

   class BaseModel(Model):
       """A base model that will use our Postgresql database"""
       class Meta:
           database = psql_db

   class User(BaseModel):
       username = CharField()
       ...

.. seealso:: :ref:`advanced-postgresql`

Using MySQL / MariaDB
---------------------

To use Peewee with MySQL or MariaDB install ``pymysql``:

.. code-block:: shell

   $ pip install pymysql

To connect to a MySQL or MariaDB database, use :py:class:`MySQLDatabase`.
The first parameter is always the name of the database.

After the database name specify additional `pymysql Connection parameters
<https://pymysql.readthedocs.io/en/latest/modules/connections.html>`__:

.. code-block:: python

   db = MySQLDatabase(
       'my_database',
       host='10.8.0.1',
       port=3306,
       connection_timeout=5)

   class BaseModel(Model):
       """A base model that will use our MySQL database"""
       class Meta:
           database = mysql_db

   class User(BaseModel):
       username = CharField()
       # ...

.. seealso:: :ref:`advanced-mysql`

Connection Parameters
---------------------

:class:`Database` initialization methods expect the name of the database as the
first parameter. Subsequent keyword arguments are passed to the underlying
database driver when establishing the connection.

With Postgresql it is common to need to specify the ``host``, ``user`` and
``password`` when creating a connection. These should be specified when
initializing the database, and they will be passed directly back to
``psycopg`` when creating connections:

.. code-block:: python

    db = PostgresqlDatabase(
        'database_name',  # Required by Peewee.
        user='postgres',  # Will be passed directly to psycopg.
        password='secret',  # Ditto.
        host='db.mysite.com')  # Ditto.

As another example, the ``pymysql`` driver accepts a ``charset`` parameter
which is not a standard Peewee :class:`Database` parameter. To set this
value, pass in ``charset`` alongside your other settings:

.. code-block:: python

   db = MySQLDatabase('database_name', user='www-data', charset='utf8mb4')

Consult your database driver's documentation for the available parameters:

* Postgresql: `psycopg2 <https://www.psycopg.org/docs/module.html#psycopg2.connect>`__
  or `psycopg3 <https://www.psycopg.org/psycopg3/docs/api/module.html#psycopg.connect>`__
* MySQL: `pymysql <https://github.com/PyMySQL/PyMySQL/blob/f08f01fe8a59e8acfb5f5add4a8fe874bec2a196/pymysql/connections.py#L494-L513>`__
* SQLite: `sqlite3 <https://docs.python.org/3/library/sqlite3.html#sqlite3.connect>`__


Initializing the Database
-------------------------

There are three ways to initialize a database:

1. Initialize database directly. Use when connection settings are available at
   the time the database is declared:

   .. code-block:: python

      db = SqliteDatabase('/path/to/app.db')

   Environment variables, config settings, etc. typically fall into this
   category as well:

   .. code-block:: python

      import os

      db = PostgresqlDatabase(
          database=app.config['APP_NAME'],
          user=os.environ.get('PGUSER') or 'postgres',
          host=os.environ.get('PGHOST') or '127.0.0.1')

2. Defer initialization. This method is needed when a connection setting is not
   available until run-time or it is inconvenient to import connection settings
   where the database is declared:

   .. code-block:: python

      db = PostgresqlDatabase(None)

      # ... some time later ...
      db_name = input('Enter database name: ')

      # Initialize the database now.
      db.init(db_name, user='postgres', host='10.8.0.1')

   Attempting to use an uninitialized database will raise an :class:`InterfaceError`.

3. Use a :class:`DatabaseProxy` and set the database at run-time. This method
   is needed when the database implementation may change at run-time. For
   example it may be either Sqlite or Postgresql depending on a command-line
   option:

   .. code-block:: python

      db = DatabaseProxy()

      # ... some time later ...
      if app.config['DEBUG']:
          database = SqliteDatabase('local.db')
      elif app.config['TESTING']:
          database = SqliteDatabase(':memory:')
      else:
          database = PostgresqlDatabase('production')

      db.initialize(database)

   Attempting to use an uninitialized database proxy will raise an ``AttributeError``.

.. _binding_database:

Changing the database at run-time
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Peewee can also set or change the database at run-time in a different way. This
technique is used by the Peewee test suite to **bind** test model classes to
various database instances when running tests.

There are two sets of complementary methods:

* :meth:`Database.bind` and :meth:`Model.bind` - bind one or more models
  to a database.
* :meth:`Database.bind_ctx` and :meth:`Model.bind_ctx` - which are the
  same as their ``bind()`` counterparts, but return a context-manager and are
  useful when the database should only be changed temporarily.

As an example, we'll declare two models **without** specifying any database:

.. code-block:: python

   class User(Model):
       username = TextField()

   class Tweet(Model):
       user = ForeignKeyField(User, backref='tweets')
       content = TextField()
       timestamp = TimestampField()

Bind the models to a database at run-time:

.. code-block:: python
   :emphasize-lines: 7, 10

   postgres_db = PostgresqlDatabase('my_app', user='postgres')
   sqlite_db = SqliteDatabase('my_app.db')

   # At this point, the User and Tweet models are NOT bound to any database.

   # Bind them to the Postgres database:
   postgres_db.bind([User, Tweet])

   # Temporarily bind them to the sqlite database:
   with sqlite_db.bind_ctx([User, Tweet]):
       # User and Tweet are now bound to the sqlite database.
       assert User._meta.database is sqlite_db

   # User and Tweet are once again bound to the Postgres database.
   assert User._meta.database is postgres_db

The :meth:`Model.bind` and :meth:`Model.bind_ctx` methods work the same
for binding a given model class:

.. code-block:: python
   :emphasize-lines: 3, 9

   # Bind the user model to the sqlite db. By default, Peewee will also
   # bind any models that are related to User via foreign-key as well.
   User.bind(sqlite_db)

   assert User._meta.database is sqlite_db
   assert Tweet._meta.database is sqlite_db  # Related models bound too.

   # Temporarily bind *just* the User model to the postgres db.
   with User.bind_ctx(postgres_db, bind_backrefs=False):
       assert User._meta.database is postgres_db
       assert Tweet._meta.database is sqlite_db  # Has not changed.

   # User is back to being bound to the sqlite_db.
   assert User._meta.database is sqlite_db

.. note::
   Peewee database connections are thread-safe. However, if you plan to **bind**
   the database at run-time in a multi-threaded application, storing the model's
   database in a thread-local is necessary. This can be accomplished with
   the :class:`ThreadSafeDatabaseMetadata` included in ``playhouse.shortcuts``:

   .. code-block:: python

      from peewee import *
      from playhouse.shortcuts import ThreadSafeDatabaseMetadata

      class BaseModel(Model):
          class Meta:
              model_metadata_class = ThreadSafeDatabaseMetadata

   The database can now be swapped safely while running in a multi-threaded
   environment using the :meth:`Database.bind` or :meth:`Database.bind_ctx`.

Connection Lifecycle
--------------------

To open a connection to a database, use the :meth:`Database.connect` method:

.. code-block:: pycon
   :emphasize-lines: 2

   >>> db = SqliteDatabase(':memory:')  # In-memory SQLite database.
   >>> db.connect()
   True

.. tip::
   Connections are stored in a thread-local by default. This enables Peewee to
   safely be used in multi-threaded applications, or when using gevent.

Calling ``connect()`` on an already-open database raises :class:`OperationalError`.
To prevent this exception from being raised, pass ``reuse_if_open=True``:

.. code-block:: pycon

   >>> db.connect()
   True
   >>> db.connect(reuse_if_open=True)
   False

To close a connection, use the :meth:`Database.close` method:

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

Determine whether the database is closed using the :meth:`Database.is_closed`
method:

.. code-block:: pycon

   >>> db.is_closed()
   True

Using autoconnect
^^^^^^^^^^^^^^^^^

By default Peewee will automatically open a connection on-demand. This behavior
is controlled by the ``autoconnect`` Database parameter. Managing
connections explicitly is considered a **best practice**, therefore
consider disabling the ``autoconnect`` behavior:

.. code-block:: python

   db = PostgresqlDatabase('app', autoconnect=False)

It is helpful to be explicit about connection lifetimes. If a connection cannot
be opened, the exception will be caught when the connection is being opened,
rather than at query time.

Thread Safety
^^^^^^^^^^^^^

Database connections and associated transactions are thread-safe.

Peewee keeps track of the connection state using thread-local storage, making
the Peewee :py:class:`Database` object safe to use with multiple threads. Each
thread will have it's own connection, and as a result any given thread will
only have a single connection open at a given time.

Context managers
^^^^^^^^^^^^^^^^

The database object can be used as a context-manager, which opens a connection
for the duration of the wrapped block of code. Additionally, a transaction is
opened at the start of the wrapped block and committed before the connection is
closed (unless an error occurs, in which case the transaction is rolled back).

.. code-block:: pycon

   >>> db.is_closed()
   True

   >>> with db:
   ...     print(db.is_closed())  # db is open and in a transaction.
   ...
   False

   >>> db.is_closed()  # db is closed, transaction is committed.
   True

If you want to manage transactions separately, you can use the
:meth:`Database.connection_context` context manager instead:

.. code-block:: pycon

   >>> with db.connection_context():
   ...     # db is open.
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

:meth:`Database.connection` returns a reference to the underlying DB-API driver
connection. This method will return the currently-open connection object, if
one exists, otherwise it will open a new connection.

.. code-block:: pycon

   >>> db.connection()
   <sqlite3.Connection object at 0x7f94e9362f10>

Executing Queries
-----------------

SQL queries will typically be executed by calling ``execute()`` on a query
constructed using the query-builder APIs (or by simply iterating over a query
object in the case of a :class:`Select` query). For cases where you wish to
execute SQL directly, use the :meth:`Database.execute_sql`:

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

.. _database-errors:

Database Errors
---------------

The Python DB-API 2.0 spec describes `several types of exceptions <https://www.python.org/dev/peps/pep-0249/#exceptions>`_.
Because most database drivers have their own implementations of these
exceptions, Peewee simplifies things by providing its own wrappers around any
implementation-specific exception classes. That way, you don't need to worry
about dealing with driver-specific exception classes, you can just use the ones
from peewee:

* ``DatabaseError``
* ``DataError``
* ``IntegrityError``
* ``InterfaceError``
* ``InternalError``
* ``NotSupportedError``
* ``OperationalError``
* ``ProgrammingError``

.. note:: All of these error classes extend ``PeeweeException``.
