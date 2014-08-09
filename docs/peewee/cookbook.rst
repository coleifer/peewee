.. _cookbook:

Peewee Cookbook
===============

Below are outlined some of the ways to perform typical database-related tasks
with peewee.

.. _user_and_tweet_models:

Throughout this document we will use the following example models:

.. include:: includes/user_tweet.rst

Database and Connection Recipes
-------------------------------

This section describes ways to configure and connect to various databases.

.. _database_cookbook:

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

Generating Models from Existing Databases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
^^^^^^^^^^^^^^^

All queries are logged to the *peewee* namespace using the standard library ``logging`` module. Queries are logged using the *DEBUG* level.  If you're interested in doing something with the queries, you can simply register a handler.

.. code-block:: python

    # Print all queries to stderr.
    import logging
    logger = logging.getLogger('peewee')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

Generating skeleton code
^^^^^^^^^^^^^^^^^^^^^^^^

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
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Models and Fields
-----------------

:py:class:`Model` classes and their associated :py:class:`Field` instances provide a direct mapping to database tables and columns. Model instances correspond to rows in the database table, and their attributes are the column values for the given row.

The following code shows the typical way you will define your database connection and model classes.

.. _blog-models:

.. include:: includes/user_tweet_with_db

1. Create an instance of a :py:class:`Database`.

    .. code-block:: python

        db = SqliteDatabase('my_app.db')

    The ``db`` object will be used to manage the connections to the Sqlite database. In this example we're using :py:class:`SqliteDatabase`, but you could also use one of the other :ref:`database engines <database_cookbook>`_.

2. Create a base model class which specifies our database.

    .. code-block:: python

        class BaseModel(Model):
            class Meta:
                database = db

    It is good practice to define a base model class which establishes the database connection. This makes your code DRY as you will not have to specify the database for subsequent models.

    Model configuration is kept namespaced in a special class called ``Meta``. This convention is borrowed from Django.  ``Meta`` configuration is passed on to subclasses, so our project's models will all subclass ``BaseModel``. There are :ref:`many different attributes <model-options>` you can configure using *Model.Meta*.

3. Define a model class.

    .. code-block:: python

        class User(BaseModel):
            username = CharField(unique=True)

    Model definition uses the declarative style seen in other popular ORMs like SQLAlchemy or Django. Note that we are extending the *BaseModel* class so the *User* model will inherit the database connection.

    We have explicitly defined a single *username* column with a unique constraint. Because we have not specified a primary key, peewee will automatically add an auto-incrementing integer primary key field named *id*.

.. note::
    If you would like to start using peewee with an existing database, you can use :ref:`pwiz` to automatically generate model definitions.

Fields
^^^^^^

The :py:class:`Field` class is used to describe the mapping of :py:class:`Model` attributes to database columns. Each field type has a corresponding SQL storage class (i.e. varchar, int), and conversion between python data types and underlying storage is handled transparently.

When creating a :py:class:`Model` class, fields are defined as class-level attributes. This should look familiar to users of the django framework. Here's an example:

.. code-block:: python

    from peewee import *

    class User(Model):
        username = CharField()
        join_date = DateTimeField()
        about_me = TextField()

There is one special type of field, :py:class:`ForeignKeyField`, which allows you
to expose foreign-key relationships between models in an intuitive way:

.. code-block:: python

    class Message(Model):
        user = ForeignKeyField(User, related_name='messages')
        body = TextField()
        send_date = DateTimeField()

This allows you to write code like the following:

.. code-block:: python

    >>> print some_message.user.username
    Some User

    >>> for message in some_user.messages:
    ...     print message.body
    some message
    another message
    yet another message

For full documentation on fields, see the :ref:`Fields API notes <fields-api>`

Field initialization arguments
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Parameters accepted by all field types and their default values:

* ``null = False`` -- boolean indicating whether null values are allowed to be stored
* ``index = False`` -- boolean indicating whether to create an index on this column
* ``unique = False`` -- boolean indicating whether to create a unique index on this column. See also :ref:`adding composite indexes <model_indexes>`.
* ``verbose_name = None`` -- string representing the "user-friendly" name of this field
* ``help_text = None`` -- string representing any helpful text for this field
* ``db_column = None`` -- string representing the underlying column to use if different, useful for legacy databases
* ``default = None`` -- any value to use as a default for uninitialized models
* ``choices = None`` -- an optional iterable containing 2-tuples of ``value``, ``display``
* ``primary_key = False`` -- whether this field is the primary key for the table
* ``sequence = None`` -- sequence to populate field (if backend supports it)
* ``constraints = None`` - a list of one or more constraints, e.g. ``[Check('price > 0')]``
* ``schema = None`` -- optional name of the schema to use, if your db supports this.

Field types table
^^^^^^^^^^^^^^^^^

===================   =================   =================   =================
Field Type            Sqlite              Postgresql          MySQL
===================   =================   =================   =================
``CharField``         varchar             varchar             varchar
``TextField``         text                text                longtext
``DateTimeField``     datetime            timestamp           datetime
``IntegerField``      integer             integer             integer
``BooleanField``      smallint            boolean             bool
``FloatField``        real                real                real
``DoubleField``       real                double precision    double precision
``BigIntegerField``   integer             bigint              bigint
``DecimalField``      decimal             numeric             numeric
``PrimaryKeyField``   integer             serial              integer
``ForeignKeyField``   integer             integer             integer
``DateField``         date                date                date
``TimeField``         time                time                time
``BlobField``         blob                bytea               blob
``UUIDField``         not supported       uuid                not supported
===================   =================   =================   =================

Some fields take special parameters...
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

+--------------------------------+------------------------------------------------+
| Field type                     | Special Parameters                             |
+================================+================================================+
| :py:class:`CharField`          | ``max_length``                                 |
+--------------------------------+------------------------------------------------+
| :py:class:`DateTimeField`      | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`DateField`          | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`TimeField`          | ``formats``                                    |
+--------------------------------+------------------------------------------------+
| :py:class:`DecimalField`       | ``max_digits``, ``decimal_places``,            |
|                                | ``auto_round``, ``rounding``                   |
+--------------------------------+------------------------------------------------+
| :py:class:`ForeignKeyField`    | ``rel_model``, ``related_name``, ``to_field``, |
|                                | ``on_delete``, ``on_update``, ``extra``        |
+--------------------------------+------------------------------------------------+

.. note::
    Both ``default`` and ``choices`` could be implemented at the database level as
``DEFAULT`` and ``CHECK CONSTRAINT`` respectively, but any application change would
require a schema change.  Because of this, ``default`` is implemented purely in
python and ``choices`` are not validated but exist for metadata purposes only.

    To add database (server-side) constraints, use the ``constraints`` parameter.

DateTimeField, DateField and TimeField
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The three fields devoted to working with dates and times have special properties
which allow access to things like the year, month, hour, etc.

:py:class:`DateField` has properties for:

* ``year``
* ``month``
* ``day``

:py:class:`TimeField` has properties for:

* ``hour``
* ``minute``
* ``second``

:py:class:`DateTimeField` has all of the above.

These properties can be used just like any other expression.  Let's say we have
an events calendar and want to hi-lite all the days in the current month that
have an event attached:

.. code-block:: python

    # Get the current time.
    now = datetime.datetime.now()

    # Get days that have events for the current month.
    Event.select(Event.event_date.day.alias('day')).where(
        (Event.event_date.year == now.year) &
        (Event.event_date.month == now.month))

Creating a custom field
^^^^^^^^^^^^^^^^^^^^^^^

It isn't too difficult to add support for custom field types in peewee. Let's add a UUID field for postgresql (which has a native UUID column type).

To add a custom field type you need to first identify what type of column the field data will be stored in. If you just want to add "python" behavior atop, say, a decimal field (for instance to make a currency field) you would just subclass :py:class:`DecimalField`. On the other hand, if the database offers a custom column type you will need to let peewee know. This is controlled by the :py:attr:`Field.db_field` attribute.

Let's start by defining our UUID field:

.. code-block:: python

    class UUIDField(Field):
        db_field = 'uuid'

We will store the UUIDs in a native UUID column. Since psycopg2 treats the data as a string by default, we will add two methods to the field to handle:

* The data coming out of the database to be used in our application
* The data from our python app going into the database

.. code-block:: python

    import uuid

    class UUIDField(Field):
        db_field = 'uuid'

        def db_value(self, value):
            return str(value) # convert UUID to str

        def python_value(self, value):
            return uuid.UUID(value) # convert str to UUID

Now, we need to let the database know how to map this "uuid" label to an actual "uuid" column type in the database. There are 2 ways of doing this:

1. Specify the overrides in the :py:class:`Database` constructor:

  .. code-block:: python

      db = PostgresqlDatabase('my_db', fields={'uuid': 'uuid'})

2. Register them class-wide using :py:meth:`Database.register_fields`:

  .. code-block:: python

      # will affect all instances of PostgresqlDatabase
      PostgresqlDatabase.register_fields({'uuid': 'uuid'})

That is it! Some fields may support exotic operations, like the postgresql HStore field acts like a key/value store and has custom operators for things like "contains" and "update". You can specify "op overrides" as well.  For more information, check out the source code for the :py:class:`HStoreField`, in ``playhouse.postgres_ext``.

Creating tables
^^^^^^^^^^^^^^^

In order to start using these models, its necessary to open a connection to the database and create the tables first. Peewee will run the necessary *CREATE TABLE* queries, additionally creating any constraints and indexes.

.. code-block:: python

    # Connect to our database.
    db.connect()

    # Create the tables.
    db.create_tables([User, Tweet])

.. note::
    Strictly speaking, it is not necessary to call :py:meth:`~Database.connect` but it is good practice to be explicit. That way if something goes wrong, the error occurs at the connect step, rather than some arbitrary time later.

.. note::
    Peewee can determine if your tables already exist, and conditionally create them:

    .. code-block:: python

        # Only create the tables if they do not exist.
        db.create_tables([User, Tweet], safe=True)

After you have created your tables, if you choose to modify your database schema (by adding, removing or otherwise changing the columns) you will need to either:

* Drop the table and re-create it.
* Run one or more *ALTER TABLE* queries. Peewee comes with a schema migration tool which can greatly simplify this. Check the :ref:`schema migrations <migrate>` docs for details.

Model options and table metadata
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In order not to pollute the model namespace, model-specific configuration is placed in a special class called *Meta* (a convention borrowed from the django framework):

.. code-block:: python

    from peewee import *

    contacts_db = SqliteDatabase('contacts.db')

    class Person(Model):
        name = CharField()

        class Meta:
            database = contacts_db

This instructs peewee that whenever a query is executed on *Person* to use the contacts database.

.. note::
    Take a look at :ref:`the sample models <blog-models>` - you will notice that we created a ``BaseModel`` that defined the database, and then extended. This is the preferred way to define a database and create models.

Once the class is defined, you should not access ``ModelClass.Meta``, but instead use ``ModelClass._meta``:

.. code-block:: pycon

    >>> Person.Meta
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    AttributeError: type object 'Preson' has no attribute 'Meta'

    >>> Person._meta
    <peewee.ModelOptions object at 0x7f51a2f03790>

The :py:class:`ModelOptions` class implements several methods which may be of use for retrieving model metadata (such as lists of fields, foreign key relationships, and more).

.. code-block:: pycon

    >>> Person._meta.fields
    {'id': <peewee.PrimaryKeyField object at 0x7f51a2e92750>, 'name': <peewee.CharField object at 0x7f51a2f0a510>}

    >>> Person._meta.primary_key
    <peewee.PrimaryKeyField object at 0x7f51a2e92750>

    >>> Person._meta.database
    <peewee.SqliteDatabase object at 0x7f519bff6dd0>

.. _model-options:

There are several options you can specify as ``Meta`` attributes. While most options are inheritable, some are table-specific and will not be inherited by subclasses.

===================   ==============================================   ============
Option                Meaning                                          Inheritable?
===================   ==============================================   ============
``database``          database for model                               yes
``db_table``          name of the table to store data                  no
``indexes``           a list of fields to index                        yes
``order_by``          a list of fields to use for default ordering     yes
``primary_key``       a :py:class:`CompositeKey` instance              yes
``table_alias``       an alias to use for the table in queries         no
===================   ==============================================   ============

Here is an example showing inheritable versus non-inheritable attributes:

.. code-block:: pycon

    >>> db = SqliteDatabase(':memory:')
    >>> class ModelOne(Model):
    ...     class Meta:
    ...         database = db
    ...         db_table = 'model_one_tbl'
    ...
    >>> class ModelTwo(ModelOne):
    ...     pass
    ...
    >>> ModelOne._meta.database is ModelTwo._meta.database
    True
    >>> ModelOne._meta.db_table == ModelTwo._meta.db_table
    False

.. _model_indexes:

Specifying indexes for a model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Peewee can create indexes on single or multiple columns, optionally including a *UNIQUE* constraint.

Single column indexes are defined using field initialization parameters. The following example adds a unique index on the *username* field, and a normal index on the *email* field:

.. code-block:: python

    class User(Model):
        username = CharField(unique=True)
        email = CharField(index=True)

Multi-column indexes are defined as *Meta* attributes using a nested tuple. Each database index is a 2-tuple, the first part of which is a tuple of the names of the fields, the second part a boolean indicating whether the index should be unique.

.. code-block:: python

    class Transaction(Model):
        from_acct = CharField()
        to_acct = CharField()
        amount = DecimalField()
        date = DateTimeField()

        class Meta:
            indexes = (
                # create a unique on from/to/date
                (('from_acct', 'to_acct', 'date'), True),

                # create a non-unique on from/to
                (('from_acct', 'to_acct'), False),
            )

Basic CRUD operations
---------------------

This section will cover the basic CRUD operations commonly performed on a relational database:

* :py:meth:`Model.create`, for executing *INSERT* queries.
* :py:meth:`Model.save` and :py:meth:`Model.update`, for executing *UPDATE* queries.
* :py:meth:`Model.delete_instance` and :py:meth:`Model.delete`, for executing *DELETE* queries.
* :py:meth:`Model.select`, for executing *SELECT* queries.

Creating a new record
^^^^^^^^^^^^^^^^^^^^^

You can use :py:meth:`Model.create` to create a new model instance. This method accepts keyword arguments, where the keys correspond to the names of the model's fields. A new instance is returned and a row is added to the table.

.. code-block:: pycon

    >>> User.create(username='Charlie')
    <__main__.User object at 0x2529350>

This will *INSERT* a new row into the database. The primary key will automatically be retrieved and stored on the model instance.

Alternatively, you can build up a model instance programmatically and then call :py:meth:`~Model.save`:

.. code-block:: pycon

    >>> user = User(username='Charlie')
    >>> user.save()  # save() returns the number of rows modified.
    1
    >>> user.id
    1
    >>> peewee = User()
    >>> peewee.username = 'Peewee'
    >>> peewee.save()
    1
    >>> peewee.id
    2

When a model has a foreign key, you can directly assign a model instance to the foreign key field when creating a new record.

.. code-block:: pycon

    >>> tweet = Tweet.create(user=peewee, message='Hello!')

You can also use the value of the related object's primary key:

.. code-block:: pycon

    >>> tweet = Tweet.create(user=2, message='Hello again!')

If you simply wish to insert data and do not need to create a model instance, you can use :py:meth:`Model.insert`:

.. code-block:: pycon

    >>> User.insert(username='Huey').execute()
    3

After executing the insert query, the primary key of the new row is returned.

.. note::
    There are several ways you can speed up bulk insert operations. Check out
    the :ref:`bulk_inserts` recipe section for more information.

.. _bulk_inserts:

Bulk inserts
^^^^^^^^^^^^

There are a couple of ways you can load lots of data quickly. The naive approach is to simply call :py:meth:`Model.create` in a loop:

.. code-block:: python

    data_source = [
        {'field1': 'val1-1', 'field2': 'val1-2'},
        {'field1': 'val2-1', 'field2': 'val2-2'},
        # ...
    ]

    for data_dict in data_source:
        Model.create(**data_dict)

The above approach is slow for a couple of reasons:

1. If you are using autocommit (the default), then each call to :py:meth:`~Model.create` happens in its own transaction. That is going to be really slow!
2. There is a decent amount of Python logic getting in your way, and each :py:class:`InsertQuery` must be generated and parsed into SQL.
3. That's a lot of data (in terms of raw bytes of SQL) you are sending to your database to parse.
4. We are retrieving the *last insert id*, which causes an additional query to be executed in some cases.

You can get a **very significant speedup** by simply wrapping this in a :py:meth:`~Database.transaction`.

.. code-block:: python

    # This is much faster.
    with db.transaction():
        for data_dict in data_source:
            Model.create(**data_dict)

The above code still suffers from points 2, 3 and 4. We can get another big boost by calling :py:meth:`~Model.insert_many`. This method accepts a list of dictionaries to insert.

.. code-block:: python

    # Fastest.
    with db.transaction():
        Model.insert_many(data_source).execute()

Depending on the number of rows in your data source, you may need to break it up into chunks:

.. code-block:: python

    # Insert rows 1000 at a time.
    with db.transaction():
        for idx in range(0, len(data_source), 1000):
            Model.insert_many(data_source[idx:idx+1000]).execute()

If the data you would like to bulk load is stored in another table, you can also create *INSERT* queries whose source is a *SELECT* query. Use the :py:meth:`Model.insert_from` method:

.. code-block:: python

    query = (TweetArchive
             .insert_from(
                 fields=[Tweet.user, Tweet.message],
                 query=Tweet.select(Tweet.user, Tweet.message))
             .execute())

Updating existing records
^^^^^^^^^^^^^^^^^^^^^^^^^

Once a model instance has a primary key, any subsequent call to :py:meth:`~Model.save` will result in an *UPDATE* rather than another *INSERT*. The model's primary key will not change:

.. code-block:: pycon

    >>> user.save()  # save() returns the number of rows modified.
    1
    >>> user.id
    1
    >>> user.save()
    >>> user.id
    1
    >>> peewee.save()
    1
    >>> peewee.id
    2

If you want to update multiple records, issue an *UPDATE* query. The following example will update all ``Tweet`` objects, marking them as *published*, if they were created before today. :py:meth:`Model.update` accepts keyword arguments where the keys correspond to the model's field names:

.. code-block:: pycon

    >>> today = datetime.today()
    >>> query = Tweet.update(is_published=True).where(Tweet.creation_date < today)
    >>> query.execute()  # Returns the number of rows that were updated.
    4

For more information, see the documentation on :py:meth:`Model.update` and :py:class:`UpdateQuery`.

.. note::
    If you would like more information on performing atomic updates (such as
    incrementing the value of a column), check out the :ref:`atomic update <atomic_updates>`
    recipes.

.. _atomic_updates:

Atomic updates
^^^^^^^^^^^^^^

Peewee allows you to perform atomic updates. Let's suppose we need to update some counters. The naive approach would be to write something like this:

.. code-block:: pycon

    >>> for stat in Stat.select().where(Stat.url == request.url):
    ...     stat.counter += 1
    ...     stat.save()

**Do not do this!** Not only is this slow, but it is also vulnerable to race conditions if multiple processes are updating the counter at the same time.

Instead, you can update the counters atomically using :py:meth:`~Model.update`:

.. code-block:: pycon

    >>> query = Stat.update(counter=Stat.counter + 1).where(Stat.url == request.url)
    >>> query.update()

You can make these update statements as complex as you like. Let's give all our employees a bonus equal to their previous bonus plus 10% of their salary:

.. code-block:: pycon

    >>> query = Employee.update(bonus=(Employee.bonus + (Employee.salary * .1)))
    >>> query.execute()  # Give everyone a bonus!

We can even use a subquery to update the value of a column. Suppose we had a denormalized column on the ``User`` model that stored the number of tweets a user had made, and we updated this value periodically. Here is how you might write such a query:

.. code-block:: pycon

    >>> subquery = Tweet.select(fn.COUNT(Tweet.id)).where(Tweet.user == User.id)
    >>> update = User.update(num_tweets=subquery)
    >>> update.execute()

Deleting a record
^^^^^^^^^^^^^^^^^

To delete a single model instance, you can use the :py:meth:`Model.delete_instance` shortcut. :py:meth:`~Model.delete_instance` will delete the given model instance and can optionally delete any dependent objects recursively (by specifying `recursive=True`).

.. code-block:: pycon

    >>> user = User.get(User.id == 1)
    >>> user.delete_instance()  # Returns the number of rows deleted.
    1

    >>> User.get(User.id == 1)
    UserDoesNotExist: instance matching query does not exist:
    SQL: SELECT t1."id", t1."username" FROM "user" AS t1 WHERE t1."id" = ?
    PARAMS: [1]

To delete an arbitrary set of rows, you can issue a *DELETE* query. The following will delete all ``Tweet`` objects that are over one year old:

.. code-block:: pycon

    >>> query = Tweet.delete().where(Tweet.creation_date < one_year_ago)
    >>> query.execute()  # Returns the number of rows deleted.
    7

For more information, see the documentation on:

* :py:meth:`Model.delete_instance`
* :py:meth:`Model.delete`
* :py:class:`DeleteQuery`

Selecting a single record
^^^^^^^^^^^^^^^^^^^^^^^^^

You can use the :py:meth:`Model.get` method to retrieve a single instance matching the given query.

This method is a shortcut that calls :py:meth:`Model.select` with the given query, but limits the result set to a single row. Additionally, if no model matches the given query, a ``DoesNotExist`` exception will be raised.

.. code-block:: pycon

    >>> User.get(User.id == 1)
    <__main__.User object at 0x25294d0>

    >>> User.get(User.id == 1).username
    u'Charlie'

    >>> User.get(User.username == 'Charlie')
    <__main__.User object at 0x2529410>

    >>> User.get(User.username == 'nobody')
    UserDoesNotExist: instance matching query does not exist:
    SQL: SELECT t1."id", t1."username" FROM "user" AS t1 WHERE t1."username" = ?
    PARAMS: ['nobody']

For more advanced operations, you can use :py:meth:`SelectQuery.get`. The following query retrieves the latest tweet from the user named *charlie*:

.. code-block:: pycon

    >>> (Tweet
    ...  .select()
    ...  .join(User)
    ...  .where(User.username == 'charlie')
    ...  .order_by(Tweet.created_date.desc())
    ...  .get())
    <__main__.Tweet object at 0x2623410>

For more information, see the documentation on:

* :ref:`querying`
* :py:meth:`Model.get`
* :py:meth:`Model.select`
* :py:meth:`SelectQuery.get`

Get or create
^^^^^^^^^^^^^

While peewee has a :py:meth:`~Model.get_or_create` method, this should really not be used outside of tests as it is vulnerable to a race condition. The proper way to perform a *get or create* with peewee is to rely on the database to enforce a constraint.

Let's say we wish to implement registering a new user account using the :ref:`example User model <user_and_tweet_models>`. The *User* model has a *unique* constraint on the username field, so we will rely on the database's integrity guarantees to ensure we don't end up with duplicate usernames:

.. code-block:: python

    try:
        with db.transaction():
            user = User.create(username=username)
        return 'Success'
    except peewee.IntegrityError:
        return 'Failure: %s is already in use' % username

Selecting multiple records
^^^^^^^^^^^^^^^^^^^^^^^^^^

We can use :py:meth:`Model.select` to retrieve rows from the table. When you construct a *SELECT* query, the database will return any rows that correspond to your query. Peewee allows you to iterate over these rows, as well as use indexing and slicing operations.

In the following example, we will simply call :py:meth:`~Model.select` and iterate over the return value, which is an instance of :py:class:`SelectQuery`. This will return all the rows in the *User* table:

.. code-block:: pycon

    >>> for user in User.select():
    ...     print user.username
    ...
    Charlie
    Huey
    Peewee

.. note::
    Subsequent iterations of the same query will not hit the database as the results are cached. To disable this behavior (to reduce memory usage), call :py:meth:`SelectQuery.iterator` when iterating.

When iterating over a model that contains a foreign key, be careful with the way you access values on related models. Accidentally resolving a foreign key or iterating over a back-reference can cause :ref:`N+1 query behavior <cookbook_nplusone>`.

When you create a foreign key, such as ``Tweet.user``, you can use the *related_name* to create a back-reference (``User.tweets``). Back-references are exposed as :py:class:`SelectQuery` instances:

.. code-block:: pycon

    >>> tweet = Tweet.get()
    >>> tweet.user  # Accessing a foreign key returns the related model.
    <tw.User at 0x7f3ceb017f50>

    >>> user = User.get()
    >>> user.tweets  # Accessing a back-reference returns a query.
    <SelectQuery> SELECT t1."id", t1."user_id", t1."message", t1."created_date", t1."is_published" FROM "tweet" AS t1 WHERE (t1."user_id" = ?) [1]

You can iterate over the ``user.tweets`` back-reference just like any other :py:class:`SelectQuery`:

.. code-block:: pycon

    >>> for tweet in user.tweets:
    ...     print tweet.message
    ...
    hello world
    this is fun
    look at this picture of my food

Filtering records
^^^^^^^^^^^^^^^^^

You can filter for particular records using normal python operators. Peewee supports a :ref:`wide variety of operations <column-lookups>`.

.. code-block:: pycon

    >>> user = User.get(User.username == 'Charlie')
    >>> for tweet in Tweet.select().where(Tweet.user == user, Tweet.is_published == True):
    ...     print '%s: %s (%s)' % (tweet.user.username, tweet.message)
    ...
    Charlie: hello world
    Charlie: this is fun

    >>> for tweet in Tweet.select().where(Tweet.created_date < datetime.datetime(2011, 1, 1)):
    ...     print tweet.message, tweet.created_date
    ...
    Really old tweet 2010-01-01 00:00:00

You can also filter across joins:

.. code-block:: pycon

    >>> for tweet in Tweet.select().join(User).where(User.username == 'Charlie'):
    ...     print tweet.message
    hello world
    this is fun
    look at this picture of my food

If you want to express a complex query, use parentheses and python's bitwise *or* and *and* operators:

.. code-block:: pycon

    >>> Tweet.select().join(User).where(
    ...     (User.username == 'Charlie') |
    ...     (User.username == 'Peewee Herman')
    ... )

Check out :ref:`the table of query operations <column-lookups>` to see what types of queries are possible.

.. note::

    A lot of fun things can go in the where clause of a query, such as:

    * A field expression, e.g. ``User.username == 'Charlie'``
    * A function expression, e.g. ``fn.Lower(fn.Substr(User.username, 1, 1)) == 'a'``
    * A comparison of one column to another, e.g. ``Employee.salary < (Employee.tenure * 1000) + 40000``

    You can also nest queries, for example tweets by users whose username starts with "a":

    .. code-block:: python

        # get users whose username starts with "a"
        a_users = User.select().where(fn.Lower(fn.Substr(User.username, 1, 1)) == 'a')

        # the "<<" operator signifies an "IN" query
        a_user_tweets = Tweet.select().where(Tweet.user << a_users)

More query examples
^^^^^^^^^^^^^^^^^^^

Get active users:

.. code-block:: python

    User.select().where(User.active == True)

Get users who are either staff or superusers:

.. code-block:: python

    User.select().where(
        (User.is_staff == True) | (User.is_superuser == True))

Get tweets by user named "charlie":

.. code-block:: python

    Tweet.select().join(User).where(User.username == 'charlie')

Get tweets by staff or superusers (assumes FK relationship):

.. code-block:: python

    Tweet.select().join(User).where(
        (User.is_staff == True) | (User.is_superuser == True))

Get tweets by staff or superusers using a subquery:

.. code-block:: python

    staff_super = User.select(User.id).where(
        (User.is_staff == True) | (User.is_superuser == True))
    Tweet.select().where(Tweet.user << staff_super)

Query operators
^^^^^^^^^^^^^^^

The following types of comparisons are supported by peewee:

================ =======================================
Comparison       Meaning
================ =======================================
``==``           x equals y
``<``            x is less than y
``<=``           x is less than or equal to y
``>``            x is greater than y
``>=``           x is greater than or equal to y
``!=``           x is not equal to y
``<<``           x IN y, where y is a list or query
``>>``           x IS y, where y is None/NULL
``%``            x LIKE y where y may contain wildcards
``**``           x ILIKE y where y may contain wildcards
================ =======================================

Because I ran out of operators to override, there are some additional query operations available as methods:

=====================   ===============================================
Method                  Meaning
=====================   ===============================================
``.contains(substr)``   Wild-card search for substring.
``.startswith(prefix)`` Search for values beginning with ``prefix``.
``.endswith(suffix)``   Search for values ending with ``suffix``.
``.between(low, high)`` Search for values between ``low`` and ``high``.
``.regexp(exp)``        Regular expression match.
``.bin_and(value)``     Binary AND.
``.bin_or(value)``      Binary OR.
``.in_(value)``         IN lookup (identical to ``<<``).
=====================   ===============================================

Here is how you might use some of these query operators:

.. code-block:: python

    User.select().where(User.username == 'charlie')
    User.select().where(User.username << ['charlie', 'huey', 'mickey'])

    Employee.select().where(Employee.salary.between(50000, 60000))

    Employee.select().where(Employee.name.startswith('C'))

    Blog.select().where(Blog.title.contains(search_string))

.. note::
    Because SQLite's ``LIKE`` operation is case-insensitive by default,
    peewee will use the SQLite ``GLOB`` operation for case-sensitive searches.
    The glob operation uses asterisks for wildcards as opposed to the usual
    percent-sign.  **If you are using SQLite and want case-sensitive partial
    string matching, remember to use asterisks for the wildcard (``*``).**

.. _custom-lookups:

Adding user-defined operators
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Because I ran out of python operators to overload, there are some missing operators in peewee, for instance `modulo <https://github.com/coleifer/peewee/issues/177>`_. If you find that you need to support an operator that is not in the table above, it is very easy to add your own.

Here is how you might add support for ``modulo`` in SQLite:

.. code-block:: python

    from peewee import *
    from peewee import Expression # the building block for expressions

    OP_MOD = 'mod'

    def mod(lhs, rhs):
        return Expression(lhs, OP_MOD, rhs)

    SqliteDatabase.register_ops({OP_MOD: '%'})

Now you can use these custom operators to build richer queries:

.. code-block:: python

    # Users with even ids.
    User.select().where(mod(User.id, 2) == 0)

For more examples check out the source to the ``playhouse.postgresql_ext`` module, as it contains numerous operators specific to postgresql's hstore.

Traversing foriegn keys
^^^^^^^^^^^^^^^^^^^^^^^

Referring back to the :ref:`User and Tweet models <blog-models>`, note that there is a :py:class:`ForeignKeyField` from *Tweet* to *User*. The foreign key can be traversed, allowing you access to the associated user instance:

.. code-block:: pycon

    >>> tweet.user.username
    'charlie'

.. note::
    Unless the *User* model was explicitly selected when retrieving the *Tweet*, an additional query will be required to load the *User* data. To learn how to avoid the extra query, see the :ref:`N+1 query documentation <nplusone>`.

The reverse is also true, and we can iterate over the tweets associated with a given *User* instance:

.. code-block:: python

    >>> for tweet in user.tweets:
    ...     print tweet.message
    ...
    http://www.youtube.com/watch?v=xdhLQCYQ-nQ

Under the hood, the *tweets* attribute is just a :py:class:`SelectQuery` with the *WHERE* clause pre-populated to point to the given *User* instance:

.. code-block:: python

    >>> user.tweets
    <class 'twx.Tweet'> SELECT t1."id", t1."user_id", t1."message", ...

Joining tables
^^^^^^^^^^^^^^

Use the :py:meth:`~SelectQuery.join` method to *JOIN* additional tables. When a foreign key exists between the source model and the join model, you do not need to specify any additional parameters:

.. code-block:: pycon

    >>> my_tweets = Tweet.select().join(User).where(User.username == 'charlie')

By default peewee will use an *INNER* join, but you can use *LEFT OUTER* or *FULL* joins as well:

.. code-block:: python

    users = (User
             .select(User, fn.Count(Tweet.id).alias('num_tweets'))
             .join(Tweet, JOIN_LEFT_OUTER)
             .group_by(User)
             .order_by(fn.Count(Tweet.id).desc()))
    for user in users:
        print user.username, 'has created', user.num_tweets, 'tweet(s).'

If a foreign key does not exist between two tables you can still perform a join, but you must manually specify the join condition.

.. note:: By specifying an alias on the join condition, you can control the attribute peewee will assign the joined instance to.

.. code-block:: python

    user_log = (User
                .select(User, ActivityLog)
                .join(
                    ActivityLog,
                    on=(User.id == ActivityLog.object_id).alias('log'))
                .where(
                    (ActivityLog.activity_type == 'user_activity') &
                    (User.username == 'charlie')))

    for user in user_log:
        print user.username, user.log.description

    #### Print something like ####
    charlie logged in
    charlie posted a tweet
    charlie retweeted
    charlie posted a tweet
    charlie logged out

When calling :py:meth:`~Query.join`, peewee will use the *last joined table* as the source table. For example:

.. code-block:: python

    User.join(Tweet).join(Comment)

This query will result in a join from *User* to *Tweet*, and another join from *Tweet* to *Comment*.

If you would like to join the same table twice, use the :py:meth:`~Query.switch` method:

.. code-block:: python

    # Join the Artist table on both `Ablum` and `Genre`.
    Artist.join(Album).switch(Artist).join(Genre)

.. attention:: The :ref:`cookbook_nplusone` docs discuss ways to use joins to avoid N+1 query behavior.

.. _manytomany:

Implementing Many to Many
^^^^^^^^^^^^^^^^^^^^^^^^^

Peewee does not provide a "field" for many to many relationships the way that
django does -- this is because the "field" really is hiding an intermediary
table.  To implement many-to-many with peewee, you will therefore create the
intermediary table yourself and query through it:

.. code-block:: python

    class Student(Model):
        name = CharField()

    class Course(Model):
        name = CharField()

    class StudentCourse(Model):
        student = ForeignKeyField(Student)
        course = ForeignKeyField(Course)

To query, let's say we want to find students who are enrolled in math class:

.. code-block:: python

    for student in Student.select().join(StudentCourse).join(Course).where(Course.name == 'math'):
        print student.name

To query what classes a given student is enrolled in:

.. code-block:: python

    courses = (Course
        .select()
        .join(StudentCourse)
        .join(Student)
        .where(Student.name == 'da vinci'))

    for course in courses:
        print course.name

To efficiently iterate over a many-to-many relation, i.e., list all students
and their respective courses, we will query the "through" model ``StudentCourse``
and "precompute" the Student and Course:

.. code-block:: python

    query = (StudentCourse
        .select(StudentCourse, Student, Course)
        .join(Course)
        .switch(StudentCourse)
        .join(Student)
        .order_by(Student.name))

To print a list of students and their courses you might do the following:

.. code-block:: python

    last = None
    for student_course in query:
        student = student_course.student
        if student != last:
            last = student
            print 'Student: %s' % student.name
        print '    - %s' % student_course.course.name

Since we selected all fields from ``Student`` and ``Course`` in the ``select``
clause of the query, these foreign key traversals are "free" and we've done the
whole iteration with just 1 query.

Sorting records
^^^^^^^^^^^^^^^

To return rows in order, use the :py:meth:`~SelectQuery.order_by` method:

.. code-block:: pycon

    >>> for t in Tweet.select().order_by(Tweet.created_date):
    ...     print t.pub_date
    ...
    2010-01-01 00:00:00
    2011-06-07 14:08:48
    2011-06-07 14:12:57

    >>> for t in Tweet.select().order_by(Tweet.created_date.desc()):
    ...     print t.pub_date
    ...
    2011-06-07 14:12:57
    2011-06-07 14:08:48
    2010-01-01 00:00:00

You can also order across joins. Assuming you want to order tweets by the username of the author, then by created_date:

.. code-block:: pycon

    >>> qry = Tweet.select().join(User).order_by(User.username, Tweet.created_date.desc())

.. code-block:: sql

    SELECT t1."id", t1."user_id", t1."message", t1."is_published", t1."created_date"
    FROM "tweet" AS t1
    INNER JOIN "user" AS t2
      ON t1."user_id" = t2."id"
    ORDER BY t2."username", t1."created_date" DESC

Getting random records
^^^^^^^^^^^^^^^^^^^^^^

Occasionally you may want to pull a random record from the database. You can accomplish this by ordering by the *random* or *rand* function (depending on your database):

Postgresql and Sqlite use the *Random* function:

.. code-block:: python

    # Pick 5 lucky winners:
    LotteryNumber.select().order_by(fn.Random()).limit(5)

MySQL uses *Rand*:

.. code-block:: python

    # Pick 5 lucky winners:
    LotterNumber.select().order_by(fn.Rand()).limit(5)

Paginating records
^^^^^^^^^^^^^^^^^^

The :py:meth:`~SelectQuery.paginate` method makes it easy to grab a *page* or records. :py:meth:`~SelectQuery.paginate` takes two parameters, ``page_number``, and ``items_per_page``.

.. attention::
    Page numbers are 1-based, so the first page of results will be page 1.

.. code-block:: pycon

    >>> for tweet in Tweet.select().order_by(Tweet.id).paginate(2, 10):
    ...     print tweet.message
    ...
    tweet 10
    tweet 11
    tweet 12
    tweet 13
    tweet 14
    tweet 15
    tweet 16
    tweet 17
    tweet 18
    tweet 19

If you would like more granular control, you can always use :py:meth:`~SelectQuery.limit` and :py:meth:`~SelectQuery.offset`.

Counting records
^^^^^^^^^^^^^^^^

You can count the number of rows in any select query:

.. code-block:: python

    >>> Tweet.select().count()
    100
    >>> Tweet.select().where(Tweet.id > 50).count()
    50

In some cases it may be necessary to wrap your query and apply a count to the rows of the inner query (such as when using *DISTINCT* or *GROUP BY*). Peewee will usually do this automatically, but in some cases you may need to manually call :py:meth:`~SelectQuery.wrapped_count` instead.

Iterating over lots of rows
^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default peewee will cache the rows returned when iterating of a :py:class:`SelectQuery`. This is an optimization to allow multiple iterations as well as indexing and slicing without causing additional queries. This caching can be problematic, however, when you plan to iterate over a large number of rows.

To reduce the amount of memory used by peewee when iterating over a query, use the :py:meth:`~SelectQuery.iterator` method. This method allows you to iterate without caching each model returned, using much less memory when iterating over large result sets.

.. code-block:: python

    # Let's assume we've got 10 million stat objects to dump to a csv file.
    stats = Stat.select()

    # Our imaginary serializer class
    serializer = CSVSerializer()

    # Loop over all the stats and serialize.
    for stat in stats.iterator():
        serializer.serialize_object(stat)

For simple queries you can see further speed improvements by using the :py:meth:`~SelectQuery.naive` method. This method speeds up the construction of peewee model instances from raw cursor data. See the :py:meth:`~SelectQuery.naive` documentation for more details on this optimization.

.. code-block:: python

    for stat in stats.naive().iterator():
        serializer.serialize_object(stat)

You can also see performance improvements by using the :py:meth:`~SelectQuery.dicts` and :py:meth:`~SelectQuery.tuples` methods.

Aggregating records
^^^^^^^^^^^^^^^^^^^

Suppose you have some users and want to get a list of them along with the count of tweets in each. The :py:meth:`~SelectQuery.annotate` method provides a short-hand for creating these types of queries:

.. code-block:: python

    query = User.select().annotate(Tweet)

The above query is equivalent to:

.. code-block:: python

    query = (User
             .select(User, fn.Count(Tweet.id).alias('count'))
             .join(Tweet)
             .group_by(User))

The resulting query will return *User* objects with all their normal attributes plus an additional attribute *count* which will contain the count of tweets for each user. By default it uses an inner join if the foreign key is not nullable, which means users without tweets won't appear in the list. To remedy this, manually specify the type of join to include users with 0 tweets:

.. code-block:: python

    query = (User
             .select()
             .join(Tweet, JOIN_LEFT_OUTER)
             .annotate(Tweet))

You can also specify a custom aggregator, such as *MIN* or *MAX*:

.. code-block:: python

    query = (User
             .select()
             .annotate(
                 Tweet,
                 fn.Max(Tweet.created_date).alias('latest_tweet_date')))

Let's assume you have a tagging application and want to find tags that have a certain number of related objects. For this example we'll use some different models in a :ref:`many-to-many <manytomany>` configuration:

.. code-block:: python

    class Photo(Model):
        image = CharField()

    class Tag(Model):
        name = CharField()

    class PhotoTag(Model):
        photo = ForeignKeyField(Photo)
        tag = ForeignKeyField(Tag)

Now say we want to find tags that have at least 5 photos associated with them:

.. code-block:: python

    query = (Tag
             .select()
             .join(PhotoTag)
             .join(Photo)
             .group_by(Tag)
             .having(fn.Count(Photo.id) > 5))

This query is equivalent to the following SQL:

.. code-block:: sql

    SELECT t1."id", t1."name"
    FROM "tag" AS t1
    INNER JOIN "phototag" AS t2 ON t1."id" = t2."tag_id"
    INNER JOIN "photo" AS t3 ON t2."photo_id" = t3."id"
    GROUP BY t1."id", t1."name"
    HAVING Count(t3."id") > 5

Suppose we want to grab the associated count and store it on the tag:

.. code-block:: python

    query = (Tag
             .select(Tag, fn.Count(Photo.id).alias('count'))
             .join(PhotoTag)
             .join(Photo)
             .group_by(Tag)
             .having(fn.Count(Photo.id) > 5))

Retrieving Scalar Values
^^^^^^^^^^^^^^^^^^^^^^^^

You can retrieve scalar values by calling :py:meth:`Query.scalar`. For instance:

.. code-block:: python

    >>> PageView.select(fn.Count(fn.Distinct(PageView.url))).scalar()
    100

You can retrieve multiple scalar values by passing ``as_tuple=True``:

.. code-block:: python

    >>> Employee.select(
    ...     fn.Min(Employee.salary), fn.Max(Employee.salary)
    ... ).scalar(as_tuple=True)
    (30000, 50000)

SQL Functions, Subqueries and "Raw expressions"
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Suppose you need to want to get a list of all users whose username begins with *a*. There are a couple ways to do this, but one method might be to use some SQL functions like *LOWER* and *SUBSTR*. To use arbitrary SQL functions, use the special :py:func:`fn` object to construct queries:

.. code-block:: python

    # Select the user's id, username and the first letter of their username, lower-cased
    query = User.select(User, fn.Lower(fn.Substr(User.username, 1, 1)).alias('first_letter'))

    # Alternatively we could select only users whose username begins with 'a'
    a_users = User.select().where(fn.Lower(fn.Substr(User.username, 1, 1)) == 'a')

    >>> for user in a_users:
    ...    print user.username

There are times when you may want to simply pass in some arbitrary sql. You can do this using the special :py:class:`SQL` class. One use-case is when referencing an alias:

.. code-block:: python

    # We'll query the user table and annotate it with a count of tweets for
    # the given user
    query = User.select(User, fn.Count(Tweet.id).alias('ct')).join(Tweet).group_by(User)

    # Now we will order by the count, which was aliased to "ct"
    query = query.order_by(SQL('ct'))

There are two ways to execute hand-crafted SQL statements with peewee:

1. :py:meth:`Database.execute_sql` for executing any type of query
2. :py:class:`RawQuery` for executing ``SELECT`` queries and *returning model instances*.

Example:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    class Person(Model):
        name = CharField()
        class Meta:
            database = db

    # let's pretend we want to do an "upsert", something that SQLite can
    # do, but peewee cannot.
    for name in ('charlie', 'mickey', 'huey'):
        db.execute_sql('REPLACE INTO person (name) VALUES (?)', (name,))

    # now let's iterate over the people using our own query.
    for person in Person.raw('select * from person'):
        print person.name  # .raw() will return model instances.

Window functions
^^^^^^^^^^^^^^^^

peewee comes with basic support for SQL window functions, which can be created by calling :py:meth:`fn.over` and passing in your partitioning or ordering parameters.

.. code-block:: python

    # Get the list of employees and the average salary for their dept.
    query = (Employee
             .select(
                 Employee.name,
                 Employee.department,
                 Employee.salary,
                 fn.Avg(Employee.salary).over(
                     partition_by=[Employee.department]))
             .order_by(Employee.name))

    # Rank employees by salary.
    query = (Employee
             .select(
                 Employee.name,
                 Employee.salary,
                 fn.rank().over(
                     order_by=[Employee.salary])))

For general information on window functions, check out the `postgresql docs <http://www.postgresql.org/docs/9.1/static/tutorial-window.html>`_.

Retrieving raw tuples / dictionaries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes you do not need the overhead of creating model instances and simply want to iterate over the row tuples. To do this, call :py:meth:`SelectQuery.tuples` or :py:meth:`RawQuery.tuples`:

.. code-block:: python

    stats = Stat.select(Stat.url, fn.Count(Stat.url)).group_by(Stat.url).tuples()

    # iterate over a list of 2-tuples containing the url and count
    for stat_url, stat_count in stats:
        print stat_url, stat_count

Similarly, you can return the rows from the cursor as dictionaries using :py:meth:`SelectQuery.dicts` or :py:meth:`RawQuery.dicts`:

.. code-block:: python

    stats = Stat.select(Stat.url, fn.Count(Stat.url).alias('ct')).group_by(Stat.url).dicts()

    # iterate over a list of 2-tuples containing the url and count
    for stat in stats:
        print stat['url'], stat['ct']

.. _cookbook_nplusone:

.. include:: includes/nplusone.rst

.. _working_with_transactions:

Working with transactions
-------------------------

Context manager
^^^^^^^^^^^^^^^

You can execute queries within a transaction using the ``transaction`` context manager,
which will issue a commit if all goes well, or a rollback if an exception is raised:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    with db.transaction():
        user.delete_instance(recursive=True) # delete user and associated tweets

Decorator
^^^^^^^^^

Similar to the context manager, you can decorate functions with the ``commit_on_success``
decorator:

.. code-block:: python

    db = SqliteDatabase(':memory:')

    @db.commit_on_success
    def delete_user(user):
        user.delete_instance(recursive=True)

Changing autocommit behavior
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default, databases are initialized with ``autocommit=True``, you can turn this
on and off at runtime if you like.  The behavior below is roughly the same as the
context manager and decorator:

.. code-block:: python

    db.set_autocommit(False)
    try:
        user.delete_instance(recursive=True)
    except:
        db.rollback()
        raise
    else:
        try:
            db.commit()
        except:
            db.rollback()
            raise
    finally:
        db.set_autocommit(True)

If you would like to manually control *every* transaction, simply turn autocommit
off when instantiating your database:

.. code-block:: python

    db = SqliteDatabase(':memory:', autocommit=False)

    User.create(username='somebody')
    db.commit()

.. _non_integer_primary_keys:

Non-integer Primary Keys, Composite Keys and other Tricks
---------------------------------------------------------

Non-integer primary keys
^^^^^^^^^^^^^^^^^^^^^^^^

If you would like use a non-integer primary key (which I generally don't recommend), you can specify ``primary_key=True`` when creating a field. When you wish to create a new instance for a model using a non-autoincrementing primary key, you need to be sure you :py:meth:`~Model.save` specifying ``force_insert=True``.

.. code-block:: python

    from peewee import *

    class UUIDModel(Model):
        id = UUIDField(primary_key=True)

Auto-incrementing IDs are, as their name says, automatically generated for you when you insert a new row into the database. When you call :py:meth:`~Model.save`, peewee determines whether to do an *INSERT* versus an *UPDATE* based on the presence of a primary key value. Since, with our uuid example, the database driver won't generate a new ID, we need to specify it manually. When we call save() for the first time, pass in ``force_insert = True``:

.. code-block:: python

    # This works because .create() will specify `force_insert=True`.
    obj1 = UUIDModel.create(id=uuid.uuid4())

    # This will not work, however. Peewee will attempt to do an update:
    obj2 = UUIDModel(id=uuid.uuid4())
    obj2.save() # WRONG

    obj2.save(force_insert=True) # CORRECT

    # Once the object has been created, you can call save() normally.
    obj2.save()

.. note::
    Any foreign keys to a model with a non-integer primary key will have a ``ForeignKeyField`` use the same underlying storage type as the primary key they are related to.

Composite primary keys
^^^^^^^^^^^^^^^^^^^^^^

Peewee has very basic support for composite keys.  In order to use a composite key, you must set the ``primary_key`` attribute of the model options to a :py:class:`CompositeKey` instance:

.. code-block:: python

    class BlogToTag(Model):
        """A simple "through" table for many-to-many relationship."""
        blog = ForeignKeyField(Blog)
        tag = ForeignKeyField(Tag)

        class Meta:
            primary_key = CompositeKey('blog', 'tag')

Manually specifying primary keys
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes you do not want the database to automatically generate a value for the primary key, for instance when bulk loading relational data. To handle this on a *one-off* basis, you can simply tell peewee to turn off ``auto_increment`` during the import:

.. code-block:: python

    data = load_user_csv() # load up a bunch of data

    User._meta.auto_increment = False # turn off auto incrementing IDs
    with db.transaction():
        for row in data:
            u = User(id=row[0], username=row[1])
            u.save(force_insert=True) # <-- force peewee to insert row

    User._meta.auto_increment = True

If you *always* want to have control over the primary key, simply do not use the :py:class:`PrimaryKeyField` field type, but use a normal :py:class:`IntegerField` (or other column type):

.. code-block:: python

    class User(BaseModel):
        id = IntegerField(primary_key=True)
        username = CharField()

    >>> u = User.create(id=999, username='somebody')
    >>> u.id
    999
    >>> User.get(User.username == 'somebody').id
    999

Self-referential foreign keys
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When creating a heirarchical structure it is necessary to create a self-referential foreign key which links a child object to its parent.  Because the model class is not defined at the time you instantiate the self-referential foreign key, use the special string ``'self'`` to indicate a self-referential foreign key:

.. code-block:: python

    class Category(Model):
        name = CharField()
        parent = ForeignKeyField('self', null=True, related_name='children')

As you can see, the foreign key points *upward* to the parent object and the back-reference is named *children*.

.. attention:: Self-referential foreign-keys should always be ``null=True``.

When querying against a model that contains a self-referential foreign key you may sometimes need to perform a self-join. In those cases you can use :py:meth:`Model.alias` to create a table reference. Here is how you might query the category and parent model using a self-join:

.. code-block:: python

    Parent = Category.alias()
    GrandParent = Category.alias()
    query = (Category
             .select(Category, Parent)
             .join(Parent, on=(Category.parent == Parent.id))
             .join(GrandParent, on=(Parent.parent == GrandParent.id))
             .where(GrandParent.name == 'some category')
             .order_by(Category.name))

Circular foreign key dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes it happens that you will create a circular dependency between two tables.

.. note::
  My personal opinion is that circular foreign keys are a code smell and should be refactored (by adding an intermediary table, for instance).

Adding circular foreign keys with peewee is a bit tricky because at the time you are defining either foreign key, the model it points to will not have been defined yet, causing a ``NameError``.

By using :py:class:`Proxy` we can get around the problem, though:

.. code-block:: python

    # Create a proxy object to stand in for our as-yet-undefined Tweet model.
    TweetProxy = Proxy()

    class User(Model):
        username = CharField()
        # Tweet has not been defined yet so use the proxy.
        favorite_tweet = ForeignKeyField(TweetProxy, null=True)

    class Tweet(Model):
        message = TextField()
        user = ForeignKeyField(User, related_name='tweets')

    # Now that Tweet is defined, we can initialize the proxy object.
    TweetProxy.initialize(Tweet)

After initializing the proxy the foreign key fields are now correctly set up. There is one more quirk to watch out for, though. When you call :py:class:`~Model.create_table` we will again encounter the same issue. For this reason peewee will not automatically create a foreign key constraint for any *deferred* foreign keys.

Here is how to create the tables:

.. code-block:: python

    # Foreign key constraint from User -> Tweet will NOT be created because the
    # Tweet table does not exist yet. `favorite_tweet` will just be a regular
    # integer field:
    User.create_table()

    # Foreign key constraint from Tweet -> User will be created normally.
    Tweet.create_table()

    # Now that both tables exist, we can create the foreign key from User -> Tweet:
    db.create_foreign_key(User, User.favorite_tweet)

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

Query evaluation
----------------

In order to execute a query, it is *always* necessary to call the ``execute()`` method.

To get a better idea of how querying works let's look at some example queries and their return values:

.. code-block:: pycon

    >>> dq = User.delete().where(User.active == False) # <-- returns a DeleteQuery
    >>> dq
    <peewee.DeleteQuery object at 0x7fc866ada4d0>
    >>> dq.execute() # <-- executes the query and returns number of rows deleted
    3

    >>> uq = User.update(active=True).where(User.id > 3) # <-- returns an UpdateQuery
    >>> uq
    <peewee.UpdateQuery object at 0x7fc865beff50>
    >>> uq.execute() # <-- executes the query and returns number of rows updated
    2

    >>> iq = User.insert(username='new user') # <-- returns an InsertQuery
    >>> iq
    <peewee.InsertQuery object at 0x7fc865beff10>
    >>> iq.execute() # <-- executes query and returns the new row's PK
    8

    >>> sq = User.select().where(User.active == True) # <-- returns a SelectQuery
    >>> sq
    <peewee.SelectQuery object at 0x7fc865b7a510>
    >>> qr = sq.execute() # <-- executes query and returns a QueryResultWrapper
    >>> qr
    <peewee.QueryResultWrapper object at 0x7fc865b7a6d0>
    >>> [u.id for u in qr]
    [1, 2, 3, 4, 7, 8]
    >>> [u.id for u in qr] # <-- re-iterating over qr does not re-execute query
    [1, 2, 3, 4, 7, 8]

    >>> [u.id for u in sq] # <-- as a shortcut, you can iterate directly over
    >>>                    #     a SelectQuery (which uses a QueryResultWrapper
    >>>                    #     behind-the-scenes)
    [1, 2, 3, 4, 7, 8]


.. note::
    Iterating over a :py:class:`SelectQuery` will cause it to be evaluated, but iterating over it multiple times will not result in the query being executed again.
