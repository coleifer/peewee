.. _databases:

Managing your Database
======================

This document describes how to perform typical database-related tasks with peewee. Throughout this document we will use the following example models:

.. code-block:: python

    from peewee import *

    class User(Model):
        username = CharField(unique=True)

    class Tweet(Model):
        user = ForeignKeyField(User, related_name='tweets')
        message = TextField()
        created_date = DateTimeField(default=datetime.datetime.now)
        is_published = BooleanField(default=True)

Creating a database connection and tables
-----------------------------------------

While it is not necessary to explicitly connect to the database before using it, managing connections explicitly is a good practice. This way if the connection fails, the exception can be caught during the *connect* step, rather than some arbitrary time later when a query is executed.

.. code-block:: python

    >>> database = SqliteDatabase('my_app.db')
    >>> database.connect()

To use this database with your models, set the ``database`` attribute on an inner :ref:`Meta <model-options>` class:

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

Using Postgresql
----------------

To connect to a Postgresql database, we will use :py:class:`PostgresqlDatabase`. The first parameter is always the name of the database, and after that you can specify arbitrary `psycopg2 parameters <http://initd.org/psycopg/docs/module.html#psycopg2.connect>`_.

.. code-block:: python

    psql_db = PostgresqlDatabase('my_database', user='postgres')

    class BaseModel(Model):
        """A base model that will use our Postgresql database"""
        class Meta:
            database = psql_db

    class User(BaseModel):
        username = CharField()

The :ref:`playhouse` contains a :ref:`Postgresql extension module <postgres_ext>` which provides many postgres-specific features such as:

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

Using SQLite
------------

To connect to a SQLite database, we will use :py:class:`SqliteDatabase`. The first parameter is the filename containing the database, or the string *:memory:* to create an in-memory database. After the database filename, you can specify arbitrary `sqlite3 parameters <https://docs.python.org/2/library/sqlite3.html#sqlite3.connect>`_.

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

    sqlite_db = SqliteExtDatabase('my_app.db', journal_mode='WAL')

Common Pitfalls with SQLite
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use care when committing transactions while iterating over a cursor with SQLite. Depending on your installed version of pysqlite (or ``sqlite3``), when a transaction is committed it might `reset all statements *and cursors* open on that connection <http://article.gmane.org/gmane.comp.python.db.pysqlite.user/2217>`_. Consider the following code:

.. code-block:: python

    for user in User.select():
        Tweet.create(user=user, message='hello!')

Because the outer select query is lazily evaluated, the cursor is held open for the duration of the loop. If the database is in autocommit mode (default behavior), the call to *Tweet.create* will call *commit()* on the underlying connection, resetting the outer-loop's cursor. As a result, it may happen that the first *two* users actually receive duplicate tweets.

Here are some ways to work around the issue:

.. code-block:: python

    # By running in a transaction, the new tweets will not be committed
    # immediately, and the outer SELECT will not be reset.
    with database.transaction():
        for user in User.select():
            Tweet.create(user=user, message='hello!')

    # By consuming the cursor immediately (by coercing to a list), the
    # inner COMMITs will not affect the iteration.
    for user in list(User.select()):
        Tweet.create(user=user, message='hello!')

Many, many thanks to @tmoertel for `his excellent comment <https://github.com/coleifer/peewee/issues/12#issuecomment-5614404>`_ explaining this behavior.

APSW, an Advanced SQLite Driver
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Using BerkeleyDB
----------------

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

Using MySQL
-----------

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

Connecting using a Database URL
-------------------------------

The playhouse module :ref:`db_url` provides a helper :py:func:`connect` function that accepts a database URL and returns a :py:class:`Database` instance.

Examples:

* *sqlite:///my_database.db* will create a :py:class:`SqliteDatabase` instance for the file ``my_database.db`` in the current directory.
* *postgresql://postgres:my_password@localhost:5432/my_database* will create a :py:class:`PostgresqlDatabase` instance. A username and password are provided, as well as the host and port to connect to.
* *mysql:///my_db* will create a :py:class:`MySQLDatabase` instance for the local MySQL database *my_db*.

Multi-threaded applications
---------------------------

Some database engines may not allow a connection to be shared across threads, notably SQLite. As of version 2.3.3, peewee's default behavior is to maintain a connection-per-thread. For earlier versions, instantiate your database with ``threadlocals=True``:

.. code-block:: python

    database = SqliteDatabase('my_app.db', threadlocals=True)

The above code will cause peewee to store the connection state in a thread local; each thread gets its own separate connection.

Alternatively, Python sqlite3 module can share a connection across different threads, but you have to disable runtime checks to reuse the single connection. This behavior can lead to subtle bugs regarding nested transactions when not used with care, so typically I do not recommend using this option.

.. code-block:: python

    database = SqliteDatabase('stats.db', check_same_thread=False)

.. note::
    For web applications or any multi-threaded (including green threads!) app,
    it is best to set ``threadlocals=True`` when instantiating your database.

    As of version 2.3.3, this is the default behavior when instantiating your
    database, but for earlier versions you will need to specify this manually.

.. _deferring_initialization:

Deferring initialization
------------------------

Sometimes the database connection settings are not known until run-time, when these values may be loaded from a configuration file or the environment. In these cases, you can *defer* the initialization of the database by specifying ``None`` as the database_name.

.. code-block:: python

    database = SqliteDatabase(None)  # Un-initialized database.

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
-------------------------------

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
------------------

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
    If you have a multi-threaded application (including green threads), be sure to specify ``threadlocals=True`` when instantiating your pooled database. As of versoin 2.3.3, this is the default behavior.

.. _using_read_slaves:

Read Slaves
-----------

Peewee can automatically run *SELECT* queries against one or more read replicas. The :ref:`read_slave module <read_slaves>`, included in the :ref:`playhouse` extensions library, contains a :py:class:`Model` subclass which provides this behavior.

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

Generating Models from Existing Databases
-----------------------------------------

If you'd like to generate peewee model definitions for an existing database, you can try out the database introspection tool :ref:`pwiz` that comes with peewee. *pwiz* is capable of introspecting Postgresql, MySQL and SQLite databases.

Introspecting a Postgresql database:

.. code-block:: console

    pwiz.py --engine=postgresql my_postgresql_database

Introspecting a SQLite database:

.. code-block:: console

    pwiz.py --engine=sqlite test.db

pwiz will generate:

* Database connection object
* A *BaseModel* class to use with the database
* *Model* classes for each table in the database.

The generated code is written to stdout, and can easily be redirected to a file:

.. code-block:: console

    pwiz.py -e postgresql my_postgresql_db > models.py

.. note::
    pwiz generally works quite well with even large and complex database
    schemas, but in some cases it will not be able to introspect a column.
    You may need to go through the generated code to add indexes, fix unrecognized
    column types, and resolve any circular references that were found.

Logging queries
---------------

All queries are logged to the *peewee* namespace using the standard library ``logging`` module. Queries are logged using the *DEBUG* level.  If you're interested in doing something with the queries, you can simply register a handler.

.. code-block:: python

    # Print all queries to stderr.
    import logging
    logger = logging.getLogger('peewee')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

Generating skeleton code
------------------------

For writing quick scripts, peewee comes with a helper script :ref:`pskel` which generates database connection and model boilerplate code. If you find yourself frequently writing small programs, :ref:`pskel` can really save you time.

To generate a script, you can simply run:

.. code-block:: console

    pskel User Tweet SomeModel AnotherModel > my_script.py

``pskel`` will generate code to connect to an in-memory SQLite database, as well as blank model definitions for the model names specified on the command line.

Here is a more complete example, which will use the :py:class:`PostgresqlExtDatabase` with query logging enabled:

.. code-block:: console

    pskel -l -e postgres_ext -d my_database User Tweet > my_script.py

You can now fill in the model definitions and get to hacking!

Adding a new Database Driver
----------------------------

Peewee comes with built-in support for Postgres, MySQL and SQLite. These databases are very popular and run the gamut from fast, embeddable databases to heavyweight servers suitable for large-scale deployments.  That being said, there are a ton of cool databases out there and adding support for your database-of-choice should be really easy, provided the driver supports the `DB-API 2.0 spec <http://www.python.org/dev/peps/pep-0249/>`_.

The db-api 2.0 spec should be familiar to you if you've used the standard library sqlite3 driver, psycopg2 or the like. Peewee currently relies on a handful of parts:

* `Connection.commit`
* `Connection.execute`
* `Connection.rollback`
* `Cursor.description`
* `Cursor.fetchone`

These methods are generally wrapped up in higher-level abstractions and exposed by the :py:class:`Database`, so even if your driver doesn't do these exactly you can still get a lot of mileage out of peewee.  An example is the `apsw sqlite driver <http://code.google.com/p/apsw/>`_ in the "playhouse" module.

The first thing is to provide a subclass of :py:class:`Database` that will open a connection.

.. code-block:: python

    from peewee import Database
    import foodb  # Our fictional DB-API 2.0 driver.


    class FooDatabase(Database):
        def _connect(self, database, **kwargs):
            return foodb.connect(database, **kwargs)

The :py:class:`Database` provides a higher-level API and is responsible for executing queries, creating tables and indexes, and introspecting the database to get lists of tables. The above implementation is the absolute minimum needed, though some features will not work -- for best results you will want to additionally add a method for extracting a list of tables and indexes for a table from the database.  We'll pretend that ``FooDB`` is a lot like MySQL and has special "SHOW" statements:

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

* :py:meth:`~Database.last_insert_id` and :py:meth:`~Database.rows_affected`
* :py:attr:`~Database.interpolation` and :py:attr:`~Database.quote_char`
* :py:attr:`~Database.op_overrides` for mapping operations such as "LIKE/ILIKE" to their database equivalent

Refer to the :py:class:`Database` API reference or the `source code <https://github.com/coleifer/peewee/blob/master/peewee.py>`_. for details.

.. note:: If your driver conforms to the DB-API 2.0 spec, there shouldn't be much work needed to get up and running.

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

Schema migrations
-----------------

Currently peewee does not have support for *automatic* schema migrations, but you can use the :ref:`migrate` module to create simple migration scripts. The schema migrations module works with SQLite, MySQL and Postgres, and will even allow you to do things like drop or rename columns in SQLite!

Here is an example of how you might write a migration script:

.. code-block:: python

    from playhouse.migrate import *

    my_db = SqliteDatabase('my_database.db')
    migrator = SqliteMigrator(my_db)

    title_field = CharField(default='')
    status_field = IntegerField(null=True)

    with my_db.transaction():
        migrate(
            migrator.add_column('some_table', 'title', title_field),
            migrator.add_column('some_table', 'status', status_field),
            migrator.drop_column('some_table', 'old_column'),
        )

Check the :ref:`migrate` documentation for more details.
