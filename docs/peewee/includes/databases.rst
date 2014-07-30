Creating a database connection and tables
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

While it is not necessary to explicitly connect to the database before using it, managing connections explicitly is a good practice.  This way if the connection fails, the exception can be caught during the "connect" step, rather than some arbitrary time later when a query is executed.

.. code-block:: python

    >>> database = SqliteDatabase('my_app.db')
    >>> database.connect()

To use this database with your models, set the ``database`` attribute on an inner *Meta* class:

.. code-block:: python

    class MyModel(Model):
        some_field = CharField()

        class Meta:
            database = database

**Best practice:** define a base model class that points at the database object you wish to use, and then all your models will extend it:

.. code-block:: python

    database = SqliteDatabase('my_app.db')

    class BaseModel(Model):
        class Meta:
            database = database

    class User(BaseModel):
        username = CharField()

    class Tweet(BaseModel):
        user = ForeignKeyField(User, related_name='tweets')
        message = TextField()
        # etc, etc

.. note::
    Remember to specify a database on your model classes, otherwise peewee will
    fall back to a default sqlite database named "peewee.db".

.. _using_postgresql:

Connecting to Postgresql
^^^^^^^^^^^^^^^^^^^^^^^^

To connect to a postgresql database, we will use :py:class:`PostgresqlDatabase`. The first parameter is always the name of the database, and after that you can specify arbitrary `psycopg2 parameters <http://initd.org/psycopg/docs/module.html#psycopg2.connect>`_.

.. code-block:: python

    psql_db = PostgresqlDatabase('my_database', user='postgres')

    class BaseModel(Model):
        """A base model that will use our Postgresql database"""
        class Meta:
            database = psql_db

    class User(BaseModel):
        username = CharField()

The :ref:`playhouse` contains a :ref:`PostgreSQL extension module <postgres_ext>` which provides many postgres-specific features such as:

* :ref:`Arrays <pgarrays>`
* :ref:`HStore <hstore>`
* :ref:`JSON <pgjson>`
* :ref:`Server-side cursors <server_side_cursors>`
* And more!

If you would like to use these awesome features, use the :py:class:`PostgresqlExtDatabase` from the ``playhouse.postgres_ext`` module:

.. code-block:: python

    from playhouse.postgres_ext import PostgresqlExtDatabase

    psql_db = PostgresqlExtDatabase('my_database', user='postgres')

.. _using_sqlite:

Using with SQLite
^^^^^^^^^^^^^^^^^

To connect to a SQLite database, we will use :py:class:`SqliteDatabase`. The first parameter is the filename containing the database, or the string *:memory:* to create an in-memory database.


.. code-block:: python

    sqlite_db = SqliteDatabase('my_app.db')

    class BaseModel(Model):
        """A base model that will use our Sqlite database."""
        class Meta:
            database = sqlite_db

    class User(BaseModel):
        username = CharField()
        # etc, etc

The :ref:`playhouse` contains a :ref:`SQLite extension module <sqlite_ext>` which provides many SQLite-specific features such as:

* :ref:`Full-text search <sqlite_fts>`
* Support for custom functions, aggregates and collations
* Advanced transaction support
* And more!

If you would like to use these awesome features, use the :py:class:`SqliteExtDatabase` from the ``playhouse.sqlite_ext`` module:

.. code-block:: python

    from playhouse.sqlite_ext import SqliteExtDatabase

    sqlite_db = SqliteExtDatabase('my_app.db')

Peewee also comes with an alternate SQLite database that uses :ref:`apsw`, an advanced Python SQLite driver. More information on APSW can be obtained on the `APSW project website <https://code.google.com/p/apsw/>`_. APSW provides special features like:

* Virtual tables, virtual file-systems, Blob I/O, backups and file control.
* Connections can be shared across threads without any additional locking.
* Transactions are managed explicitly by your code.
* Transactions can be nested.
* Unicode is handled *correctly*.
* APSW is faster that the standard library sqlite3 module.

If you would like to use APSW, use the :py:class:`APSWDatabase` from the `apsw_ext` module:

.. code-block:: python

    from playhouse.apsw_ext import APSWDatabase

    apsw_db = APSWDatabase('my_app.db')

.. _using_berkeleydb:

Using with BerkeleyDB
^^^^^^^^^^^^^^^^^^^^^

The :ref:`playhouse <playhouse>` contains a special extension module for using a :ref:`BerkeleyDB database <berkeleydb>`. BerkeleyDB can be compiled with a SQLite-compatible API, then the python SQLite driver can be compiled to use the Berkeley version of SQLite.

To simplify this process, you can use the ``berkeley_build.sh`` script found in the ``playhouse`` directory or find instructions in `this blog post <http://charlesleifer.com/blog/building-the-python-sqlite-driver-for-use-with-berkeleydb/>`_.

To connect to a BerkeleyDB database, we will use :py:class:`BerkeleyDatabase`. Like :py:class:`SqliteDatabase`, the first parameter is the filename containing the database or the string *:memory:* to create an in-memory database.

.. code-block:: python

    from playhouse.berkeleydb import BerkeleyDatabase

    berkeley_db = BerkeleyDatabase('my_app.db')

    class BaseModel(Model):
        """A base model that will use our BDB database."""
        class Meta:
            database = berkeley_db

    class User(BaseModel):
        username = CharField()
        # etc, etc

.. _using_mysql:

Connecting to MySQL
^^^^^^^^^^^^^^^^^^^

To connect to a MySQL database, we will use :py:class:`MySQLDatabase`. After the database name, you can specify arbitrary connection parameters that will be passed back to the driver (either MySQLdb or pymysql).

.. code-block:: python

    mysql_db = MySQLDatabase('my_database')

    class BaseModel(Model):
        """A base model that will use our MySQL database"""
        class Meta:
            database = mysql_db

    class User(BaseModel):
        username = CharField()
        # etc, etc

Multi-threaded applications
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Some database engines may not allow a connection to be shared across threads, notably SQLite. If you would like peewee to maintain a single connection per-thread, instantiate your database with ``threadlocals=True`` (*recommended*):

.. code-block:: python

    database = SqliteDatabase('my_app.db', threadlocals=True)

The above code will cause peewee to store the connection state in a thread local; each thread gets its own separate connection.

Alternatively, Python sqlite3 module can share a connection across different threads, but you have to disable runtime checks to reuse the single connection:

.. code-block:: python

    database = SqliteDatabase('stats.db', check_same_thread=False)

.. attention::
    For web applications or any multi-threaded (including green threads!) app,
    it is best to set ``threadlocals=True`` when instantiating your database.

.. _deferring_initialization:

Deferring initialization
^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes the database information is not known until run-time, when it might be loaded from a configuration file or the environment. In these cases, you can *defer* the initialization of the database by specifying ``None`` as the database_name.

.. code-block:: python

    database = SqliteDatabase(None)  # Our database will be created, but is un-initialized.

    class SomeModel(Model):
        class Meta:
            database = database

If you try to connect or issue any queries while your database is uninitialized you will get an exception:

.. code-block:: python

    >>> database.connect()
    Exception: Error, database not properly initialized before opening connection

To initialize your database, call the :py:meth:`~Database.init` method with the database name and any additional keyword arguments:

.. code-block:: python

    database_name = raw_input('What is the name of the db? ')
    database.init(database_name, host='localhost', user='postgres')

.. _dynamic_db:

Dynamically defining a database
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For even more control over how your database is defined/initialized, you can use the :py:class:`Proxy` helper. :py:class:`Proxy` objects act as a placeholder, and then at run-time you can swap it out for a different object. In the example below, we will swap out the database depending on how the app is configured:

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

.. _connection_pooling:

Connection Pooling
^^^^^^^^^^^^^^^^^^

Connection pooling is provided by the :ref:`pool module <pool>`, included in the :ref:`playhouse` extensions library. The pool supports:

* Timeout after which connections will be recycled.
* Upper bound on the number of open connections.

The connection pool module comes with support for Postgres and MySQL (though adding support for other databases is trivial).

.. code-block:: python

    from playhouse.pool import PooledPostgresqlDatabase

    db = PooledPostgresqlDatabase(
        'my_database',
        max_connections=8,
        stale_timeout=300,
        threadlocals=True,
        user='postgres')

    class BaseModel(Model):
        class Meta:
            database = db

The following pooled database classes are available:

* :py:class:`PooledPostgresqlDatabase`
* :py:class:`PooledPostgresqlExtDatabase`
* :py:class:`PooledMySQLDatabase`

.. note::
    If you have a multi-threaded application (including green threads), be sure to specify ``threadlocals=True`` when instantiating your pooled database.

.. _using_read_slaves

Read Slaves
^^^^^^^^^^^

Peewee can automatically run *SELECT* queries against one or more read replicas. The :ref:`read_slave module <read_slave>`, included in the :ref:`playhouse` extensions library, contains a :py:class:`Model` subclass which provides this behavior.

Here is how you might use the :py:class:`ReadSlaveModel`:

.. code-block:: python

    from peewee import *
    from playhouse.read_slave import ReadSlaveModel

    # Declare a master and two read-replicas.
    master = PostgresqlDatabase('master')
    replica_1 = PostgresqlDatabase('replica', host='192.168.1.2')
    replica_2 = PostgresqlDatabase('replica', host='192.168.1.3')

    class BaseModel(ReadSlaveModel):
        class Meta:
            database = master
            read_slaves = (replica_1, replica_2)

    class User(BaseModel):
        username = CharField()

Now when you execute writes (or deletes), they will be run on the master, while all read-only queries will be executed against one of the replicas. Queries are dispatched among the read slaves in round-robin fashion.
