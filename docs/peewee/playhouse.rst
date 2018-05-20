.. _playhouse:

Playhouse, extensions to Peewee
===============================

Peewee comes with numerous extension modules which are collected under the
``playhouse`` namespace. Despite the silly name, there are some very useful
extensions, particularly those that expose vendor-specific database features
like the :ref:`sqlite_ext` and :ref:`postgres_ext` extensions.

Below you will find a loosely organized listing of the various modules that
make up the ``playhouse``.

**Database drivers / vendor-specific database functionality**

* :ref:`sqlite_ext` (on its own page)
* :ref:`sqliteq`
* :ref:`sqlite_udf`
* :ref:`apsw`
* :ref:`sqlcipher_ext`
* :ref:`postgres_ext`
* :ref:`mysql_ext`

**High-level features**

* :ref:`extra-fields`
* :ref:`shortcuts`
* :ref:`hybrid`
* :ref:`kv`
* :ref:`signals`
* :ref:`dataset`

**Database management and framework integration**

* :ref:`pwiz`
* :ref:`migrate`
* :ref:`pool`
* :ref:`reflection`
* :ref:`db_url`
* :ref:`test_utils`
* :ref:`flask_utils`


.. _sqliteq:

SqliteQ
-------

The ``playhouse.sqliteq`` module provides a subclass of
:py:class:`SqliteExtDatabase`, that will serialize concurrent writes to a
SQLite database. :py:class:`SqliteQueueDatabase` can be used as a drop-in
replacement for the regular :py:class:`SqliteDatabase` if you want simple
**read and write** access to a SQLite database from **multiple threads**.

SQLite only allows one connection to write to the database at any given time.
As a result, if you have a multi-threaded application (like a web-server, for
example) that needs to write to the database, you may see occasional errors
when one or more of the threads attempting to write cannot acquire the lock.

:py:class:`SqliteQueueDatabase` is designed to simplify things by sending all
write queries through a single, long-lived connection. The benefit is that you
get the appearance of multiple threads writing to the database without
conflicts or timeouts. The downside, however, is that you cannot issue
write transactions that encompass multiple queries -- all writes run in
autocommit mode, essentially.

.. note::
    The module gets its name from the fact that all write queries get put into
    a thread-safe queue. A single worker thread listens to the queue and
    executes all queries that are sent to it.

Transactions
^^^^^^^^^^^^

Because all queries are serialized and executed by a single worker thread, it
is possible for transactional SQL from separate threads to be executed
out-of-order. In the example below, the transaction started by thread "B" is
rolled back by thread "A" (with bad consequences!):

* Thread A: UPDATE transplants SET organ='liver', ...;
* Thread B: BEGIN TRANSACTION;
* Thread B: UPDATE life_support_system SET timer += 60 ...;
* Thread A: ROLLBACK; -- Oh no....

Since there is a potential for queries from separate transactions to be
interleaved, the :py:meth:`~SqliteQueueDatabase.transaction` and
:py:meth:`~SqliteQueueDatabase.atomic` methods are disabled on :py:class:`SqliteQueueDatabase`.

For cases when you wish to temporarily write to the database from a different
thread, you can use the :py:meth:`~SqliteQueueDatabase.pause` and
:py:meth:`~SqliteQueueDatabase.unpause` methods. These methods block the
caller until the writer thread is finished with its current workload. The
writer then disconnects and the caller takes over until ``unpause`` is called.

The :py:meth:`~SqliteQueueDatabase.stop`, :py:meth:`~SqliteQueueDatabase.start`,
and :py:meth:`~SqliteQueueDatabase.is_stopped` methods can also be used to
control the writer thread.

.. note::
    Take a look at SQLite's `isolation <https://www.sqlite.org/isolation.html>`_
    documentation for more information about how SQLite handles concurrent
    connections.

Code sample
^^^^^^^^^^^

Creating a database instance does not require any special handling. The
:py:class:`SqliteQueueDatabase` accepts some special parameters which you
should be aware of, though. If you are using `gevent <http://gevent.org>`_, you
must specify ``use_gevent=True`` when instantiating your database -- this way
Peewee will know to use the appropriate objects for handling queueing, thread
creation, and locking.

.. code-block:: python

    from playhouse.sqliteq import SqliteQueueDatabase

    db = SqliteQueueDatabase(
        'my_app.db',
        use_gevent=False,  # Use the standard library "threading" module.
        autostart=False,  # The worker thread now must be started manually.
        queue_max_size=64,  # Max. # of pending writes that can accumulate.
        results_timeout=5.0)  # Max. time to wait for query to be executed.


If ``autostart=False``, as in the above example, you will need to call
:py:meth:`~SqliteQueueDatabase.start` to bring up the worker threads that will
do the actual write query execution.

.. code-block:: python

    @app.before_first_request
    def _start_worker_threads():
        db.start()

If you plan on performing SELECT queries or generally wanting to access the
database, you will need to call :py:meth:`~Database.connect` and
:py:meth:`~Database.close` as you would with any other database instance.

When your application is ready to terminate, use the :py:meth:`~SqliteQueueDatabase.stop`
method to shut down the worker thread. If there was a backlog of work, then
this method will block until all pending work is finished (though no new work
is allowed).

.. code-block:: python

    import atexit

    @atexit.register
    def _stop_worker_threads():
        db.stop()


Lastly, the :py:meth:`~SqliteQueueDatabase.is_stopped` method can be used to
determine whether the database writer is up and running.

.. _sqlite_udf:

Sqlite User-Defined Functions
-----------------------------

The ``sqlite_udf`` playhouse module contains a number of user-defined
functions, aggregates, and table-valued functions, which you may find useful.
The functions are grouped in collections and you can register these
user-defined extensions individually, by collection, or register everything.

Scalar functions are functions which take a number of parameters and return a
single value. For example, converting a string to upper-case, or calculating
the MD5 hex digest.

Aggregate functions are like scalar functions that operate on multiple rows of
data, producing a single result. For example, calculating the sum of a list of
integers, or finding the smallest value in a particular column.

Table-valued functions are simply functions that can return multiple rows of
data. For example, a regular-expression search function that returns all the
matches in a given string, or a function that accepts two dates and generates
all the intervening days.

.. note::
    To use table-valued functions, you will need to build the
    ``playhouse._sqlite_ext`` C extension.

Registering user-defined functions:

.. code-block:: python

    db = SqliteDatabase('my_app.db')

    # Register *all* functions.
    register_all(db)

    # Alternatively, you can register individual groups. This will just
    # register the DATE and MATH groups of functions.
    register_groups(db, 'DATE', 'MATH')

    # If you only wish to register, say, the aggregate functions for a
    # particular group or groups, you can:
    register_aggregate_groups(db, 'DATE')

Using a library function ("hostname"):

.. code-block:: python

    # Assume we have a model, Link, that contains lots of arbitrary URLs.
    # We want to discover the most common hosts that have been linked.
    query = (Link
             .select(fn.hostname(Link.url).alias('host'), fn.COUNT(Link.id))
             .group_by(fn.hostname(Link.url))
             .order_by(fn.COUNT(Link.id).desc())
             .tuples())

    # Print the hostname along with number of links associated with it.
    for host, count in query:
        print('%s: %s' % (host, count))


Functions, listed by collection name
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Scalar functions are indicated by ``(f)``, aggregate functions by ``(a)``, and
table-valued functions by ``(t)``.

**CONTROL_FLOW**

.. py:function:: if_then_else(cond, truthy[, falsey=None])

    Simple ternary-type operator, where, depending on the truthiness of the
    ``cond`` parameter, either the ``truthy`` or ``falsey`` value will be
    returned.

**DATE**

.. py:function:: strip_tz(date_str)

    :param date_str: A datetime, encoded as a string.
    :returns: The datetime with any timezone info stripped off.

    The time is not adjusted in any way, the timezone is simply removed.

.. py:function:: humandelta(nseconds[, glue=', '])

    :param int nseconds: Number of seconds, total, in timedelta.
    :param str glue: Fragment to join values.
    :returns: Easy-to-read description of timedelta.

    Example, 86471 -> "1 day, 1 minute, 11 seconds"

.. py:function:: mintdiff(datetime_value)

    :param datetime_value: A date-time.
    :returns: Minimum difference between any two values in list.

    Aggregate function that computes the minimum difference between any two
    datetimes.

.. py:function:: avgtdiff(datetime_value)

    :param datetime_value: A date-time.
    :returns: Average difference between values in list.

    Aggregate function that computes the average difference between consecutive
    values in the list.

.. py:function:: duration(datetime_value)

    :param datetime_value: A date-time.
    :returns: Duration from smallest to largest value in list, in seconds.

    Aggregate function that computes the duration from the smallest to the
    largest value in the list, returned in seconds.

.. py:function:: date_series(start, stop[, step_seconds=86400])

    :param datetime start: Start datetime
    :param datetime stop: Stop datetime
    :param int step_seconds: Number of seconds comprising a step.

    Table-value function that returns rows consisting of the date/+time values
    encountered iterating from start to stop, ``step_seconds`` at a time.

    Additionally, if start does not have a time component and step_seconds is
    greater-than-or-equal-to one day (86400 seconds), the values returned will
    be dates. Conversely, if start does not have a date component, values will
    be returned as times. Otherwise values are returned as datetimes.

    Example:

    .. code-block:: sql

        SELECT * FROM date_series('2017-01-28', '2017-02-02');

        value
        -----
        2017-01-28
        2017-01-29
        2017-01-30
        2017-01-31
        2017-02-01
        2017-02-02

**FILE**

.. py:function:: file_ext(filename)

    :param str filename: Filename to extract extension from.
    :return: Returns the file extension, including the leading ".".

.. py:function:: file_read(filename)

    :param str filename: Filename to read.
    :return: Contents of the file.

**HELPER**

.. py:function:: gzip(data[, compression=9])

    :param bytes data: Data to compress.
    :param int compression: Compression level (9 is max).
    :returns: Compressed binary data.

.. py:function:: gunzip(data)

    :param bytes data: Compressed data.
    :returns: Uncompressed binary data.

.. py:function:: hostname(url)

    :param str url: URL to extract hostname from.
    :returns: hostname portion of URL

.. py:function:: toggle(key)

    :param key: Key to toggle.

    Toggle a key between True/False state. Example:

    .. code-block:: pycon

        >>> toggle('my-key')
        True
        >>> toggle('my-key')
        False
        >>> toggle('my-key')
        True

.. py:function:: setting(key[, value=None])

    :param key: Key to set/retrieve.
    :param value: Value to set.
    :returns: Value associated with key.

    Store/retrieve a setting in memory and persist during lifetime of
    application. To get the current value, only specify the key. To set a new
    value, call with key and new value.

.. py:function:: clear_toggles()

    Clears all state associated with the :py:func:`toggle` function.

.. py:function:: clear_settings()

    Clears all state associated with the :py:func:`setting` function.

**MATH**

.. py:function:: randomrange(start[, stop=None[, step=None]])

    :param int start: Start of range (inclusive)
    :param int end: End of range(not inclusive)
    :param int step: Interval at which to return a value.

    Return a random integer between ``[start, end)``.

.. py:function:: gauss_distribution(mean, sigma)

    :param float mean: Mean value
    :param float sigma: Standard deviation

.. py:function:: sqrt(n)

    Calculate the square root of ``n``.

.. py:function:: tonumber(s)

    :param str s: String to convert to number.
    :returns: Integer, floating-point or NULL on failure.

.. py:function:: mode(val)

    :param val: Numbers in list.
    :returns: The mode, or most-common, number observed.

    Aggregate function which calculates *mode* of values.

.. py:function:: minrange(val)

    :param val: Value
    :returns: Min difference between two values.

    Aggregate function which calculates the minimal distance between two
    numbers in the sequence.

.. py:function:: avgrange(val)

    :param val: Value
    :returns: Average difference between values.

    Aggregate function which calculates the average distance between two
    consecutive numbers in the sequence.

.. py:function:: range(val)

    :param val: Value
    :returns: The range from the smallest to largest value in sequence.

    Aggregate function which returns range of values observed.

.. py:function:: median(val)

    :param val: Value
    :returns: The median, or middle, value in a sequence.

    Aggregate function which calculates the middle value in a sequence.

    .. note:: Only available if you compiled the ``_sqlite_udf`` extension.

**STRING**

.. py:function:: substr_count(haystack, needle)

    Returns number of times ``needle`` appears in ``haystack``.

.. py:function:: strip_chars(haystack, chars)

    Strips any characters in ``chars`` from beginning and end of ``haystack``.

.. py:function:: damerau_levenshtein_dist(s1, s2)

    Computes the edit distance from s1 to s2 using the damerau variant of the
    levenshtein algorithm.

    .. note:: Only available if you compiled the ``_sqlite_udf`` extension.

.. py:function:: levenshtein_dist(s1, s2)

    Computes the edit distance from s1 to s2 using the levenshtein algorithm.

    .. note:: Only available if you compiled the ``_sqlite_udf`` extension.

.. py:function:: str_dist(s1, s2)

    Computes the edit distance from s1 to s2 using the standard library
    SequenceMatcher's algorithm.

    .. note:: Only available if you compiled the ``_sqlite_udf`` extension.

.. py:function:: regex_search(regex, search_string)

    :param str regex: Regular expression
    :param str search_string: String to search for instances of regex.

    Table-value function that searches a string for substrings that match
    the provided ``regex``. Returns rows for each match found.

    Example:

    .. code-block:: python

        SELECT * FROM regex_search('\w+', 'extract words, ignore! symbols');

        value
        -----
        extract
        words
        ignore
        symbols

.. _apsw:

apsw, an advanced sqlite driver
-------------------------------

The ``apsw_ext`` module contains a database class suitable for use with
the apsw sqlite driver.

APSW Project page: https://github.com/rogerbinns/apsw

APSW is a really neat library that provides a thin wrapper on top of SQLite's
C interface, making it possible to use all of SQLite's advanced features.

Here are just a few reasons to use APSW, taken from the documentation:

* APSW gives all functionality of SQLite, including virtual tables, virtual
  file system, blob i/o, backups and file control.
* Connections can be shared across threads without any additional locking.
* Transactions are managed explicitly by your code.
* APSW can handle nested transactions.
* Unicode is handled correctly.
* APSW is faster.

For more information on the differences between apsw and pysqlite,
check `the apsw docs <http://rogerbinns.github.io/apsw/>`_.

How to use the APSWDatabase
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from apsw_ext import *

    db = APSWDatabase(':memory:')

    class BaseModel(Model):
        class Meta:
            database = db

    class SomeModel(BaseModel):
        col1 = CharField()
        col2 = DateTimeField()


apsw_ext API notes
^^^^^^^^^^^^^^^^^^

:py:class:`APSWDatabase` extends the :py:class:`SqliteExtDatabase` and inherits
its advanced features.

.. py:class:: APSWDatabase(database, **connect_kwargs)

    :param string database: filename of sqlite database
    :param connect_kwargs: keyword arguments passed to apsw when opening a connection

    .. py:method:: register_module(mod_name, mod_inst)

        Provides a way of globally registering a module. For more information,
        see the `documentation on virtual tables <http://rogerbinns.github.io/apsw/vtable.html>`_.

        :param string mod_name: name to use for module
        :param object mod_inst: an object implementing the `Virtual Table <http://rogerbinns.github.io/apsw/vtable.html#vttable-class>`_ interface

    .. py:method:: unregister_module(mod_name)

        Unregister a module.

        :param string mod_name: name to use for module

.. note::
    Be sure to use the ``Field`` subclasses defined in the ``apsw_ext``
    module, as they will properly handle adapting the data types for storage.

    For example, instead of using ``peewee.DateTimeField``, be sure you are importing
    and using ``playhouse.apsw_ext.DateTimeField``.


.. _sqlcipher_ext:

Sqlcipher backend
-----------------

* Although this extention's code is short, it has not been properly
  peer-reviewed yet and may have introduced vulnerabilities.
* The code contains minimum values for `passphrase` length and
  `kdf_iter`, as well as a default value for the later.
  **Do not** regard these numbers as advice. Consult the docs at
  http://sqlcipher.net/sqlcipher-api/ and security experts.

Also note that this code relies on pysqlcipher_ and sqlcipher_, and
the code there might have vulnerabilities as well, but since these
are widely used crypto modules, we can expect "short zero days" there.

..  _pysqlcipher: https://pypi.python.org/pypi/pysqlcipher
..  _sqlcipher: http://sqlcipher.net

sqlcipher_ext API notes
^^^^^^^^^^^^^^^^^^^^^^^

.. py:class:: SqlCipherDatabase(database, passphrase, kdf_iter=64000, **kwargs)

    Subclass of :py:class:`SqliteDatabase` that stores the database
    encrypted. Instead of the standard ``sqlite3`` backend, it uses pysqlcipher_:
    a python wrapper for sqlcipher_, which -- in turn -- is an encrypted wrapper
    around ``sqlite3``, so the API is *identical* to :py:class:`SqliteDatabase`'s,
    except for object construction parameters:

    :param database: Path to encrypted database filename to open [or create].
    :param passphrase: Database encryption passphrase: should be at least 8 character
        long (or an error is raised), but it is *strongly advised* to enforce better
        `passphrase strength`_ criteria in your implementation.
    :param kdf_iter: [Optional] number of PBKDF2_ iterations.

    * If the ``database`` file doesn't exist, it will be *created* with
      encryption by a key derived from ``passhprase`` with ``kdf_iter``
      PBKDF2_ iterations.
    * When trying to open an existing database, ``passhprase`` and ``kdf_iter``
      should be *identical* to the ones used when it was created.

    .. py:method:: rekey(passphrase)

        :param str passphrase: New passphrase for database.

        Change the passphrase for database.

.. _PBKDF2: https://en.wikipedia.org/wiki/PBKDF2
.. _passphrase strength: https://en.wikipedia.org/wiki/Password_strength

Notes:

    * [Hopefully] there's no way to tell whether the passphrase is wrong
      or the file is corrupt.
      In both cases -- *the first time we try to acces the database* -- a
      :py:class:`DatabaseError` error is raised,
      with the *exact* message: ``"file is encrypted or is not a database"``.

      As mentioned above, this only happens when you *access* the databse,
      so if you need to know *right away* whether the passphrase was correct,
      you can trigger this check by calling [e.g.]
      :py:meth:`~Database.get_tables()` (see example below).

    * Most applications can expect failed attempts to open the database
      (common case: prompting the user for ``passphrase``), so
      the database can't be hardwired into the :py:class:`Meta` of
      model classes. To defer initialization, pass `None` in to the
      database.

Example:

.. code-block:: python

    db = SqlCipherDatabase(None)

    class BaseModel(Model):
        """Parent for all app's models"""
        class Meta:
            # We won't have a valid db until user enters passhrase.
            database = db

    # Derive our model subclasses
    class Person(BaseModel):
        name = TextField(primary_key=True)

    right_passphrase = False
    while not right_passphrase:
        db.init(
            'testsqlcipher.db',
            passphrase=get_passphrase_from_user())

        try:  # Actually execute a query against the db to test passphrase.
            db.get_tables()
        except DatabaseError as exc:
            # This error indicates the password was wrong.
            if exc.args[0] == 'file is encrypted or is not a database':
                tell_user_the_passphrase_was_wrong()
                db.init(None)  # Reset the db.
            else:
                raise exc
        else:
            # The password was correct.
            right_passphrase = True

See also: a slightly more elaborate `example <https://gist.github.com/thedod/11048875#file-testpeeweesqlcipher-py>`_.

.. _postgres_ext:

Postgresql Extensions
---------------------

The postgresql extensions module provides a number of "postgres-only" functions,
currently:

* :ref:`hstore support <hstore>`
* :ref:`json support <pgjson>`, including *jsonb* for Postgres 9.4.
* :ref:`server-side cursors <server_side_cursors>`
* :ref:`full-text search <pg_fts>`
* :py:class:`ArrayField` field type, for storing arrays.
* :py:class:`HStoreField` field type, for storing key/value pairs.
* :py:class:`IntervalField` field type, for storing ``timedelta`` objects.
* :py:class:`JSONField` field type, for storing JSON data.
* :py:class:`BinaryJSONField` field type for the ``jsonb`` JSON data type.
* :py:class:`TSVectorField` field type, for storing full-text search data.
* :py:class:`DateTimeTZ` field type, a timezone-aware datetime field.

In the future I would like to add support for more of postgresql's features.
If there is a particular feature you would like to see added, please
`open a Github issue <https://github.com/coleifer/peewee/issues>`_.

.. warning:: In order to start using the features described below, you will need to use the extension :py:class:`PostgresqlExtDatabase` class instead of :py:class:`PostgresqlDatabase`.

The code below will assume you are using the following database and base model:

.. code-block:: python

    from playhouse.postgres_ext import *

    ext_db = PostgresqlExtDatabase('peewee_test', user='postgres')

    class BaseExtModel(Model):
        class Meta:
            database = ext_db

.. _hstore:

hstore support
^^^^^^^^^^^^^^

`Postgresql hstore <http://www.postgresql.org/docs/current/static/hstore.html>`_
is an embedded key/value store. With hstore, you can store arbitrary key/value
pairs in your database alongside structured relational data.

To use ``hstore``, you need to specify an additional parameter when
instantiating your :py:class:`PostgresqlExtDatabase`:

.. code-block:: python

    # Specify "register_hstore=True":
    db = PostgresqlExtDatabase('my_db', register_hstore=True)

Currently the ``postgres_ext`` module supports the following operations:

* Store and retrieve arbitrary dictionaries
* Filter by key(s) or partial dictionary
* Update/add one or more keys to an existing dictionary
* Delete one or more keys from an existing dictionary
* Select keys, values, or zip keys and values
* Retrieve a slice of keys/values
* Test for the existence of a key
* Test that a key has a non-NULL value

Using hstore
^^^^^^^^^^^^

To start with, you will need to import the custom database class and the hstore
functions from ``playhouse.postgres_ext`` (see above code snippet). Then, it
is as simple as adding a :py:class:`HStoreField` to your model:

.. code-block:: python

    class House(BaseExtModel):
        address = CharField()
        features = HStoreField()

You can now store arbitrary key/value pairs on ``House`` instances:

.. code-block:: pycon

    >>> h = House.create(
    ...     address='123 Main St',
    ...     features={'garage': '2 cars', 'bath': '2 bath'})
    ...
    >>> h_from_db = House.get(House.id == h.id)
    >>> h_from_db.features
    {'bath': '2 bath', 'garage': '2 cars'}

You can filter by individual key, multiple keys or partial dictionary:

.. code-block:: pycon

    >>> query = House.select()
    >>> garage = query.where(House.features.contains('garage'))
    >>> garage_and_bath = query.where(House.features.contains(['garage', 'bath']))
    >>> twocar = query.where(House.features.contains({'garage': '2 cars'}))

Suppose you want to do an atomic update to the house:

.. code-block:: pycon

    >>> new_features = House.features.update({'bath': '2.5 bath', 'sqft': '1100'})
    >>> query = House.update(features=new_features)
    >>> query.where(House.id == h.id).execute()
    1
    >>> h = House.get(House.id == h.id)
    >>> h.features
    {'bath': '2.5 bath', 'garage': '2 cars', 'sqft': '1100'}

Or, alternatively an atomic delete:

.. code-block:: pycon

    >>> query = House.update(features=House.features.delete('bath'))
    >>> query.where(House.id == h.id).execute()
    1
    >>> h = House.get(House.id == h.id)
    >>> h.features
    {'garage': '2 cars', 'sqft': '1100'}

Multiple keys can be deleted at the same time:

.. code-block:: pycon

    >>> query = House.update(features=House.features.delete('garage', 'sqft'))

You can select just keys, just values, or zip the two:

.. code-block:: pycon

    >>> for h in House.select(House.address, House.features.keys().alias('keys')):
    ...     print(h.address, h.keys)

    123 Main St [u'bath', u'garage']

    >>> for h in House.select(House.address, House.features.values().alias('vals')):
    ...     print(h.address, h.vals)

    123 Main St [u'2 bath', u'2 cars']

    >>> for h in House.select(House.address, House.features.items().alias('mtx')):
    ...     print(h.address, h.mtx)

    123 Main St [[u'bath', u'2 bath'], [u'garage', u'2 cars']]

You can retrieve a slice of data, for example, all the garage data:

.. code-block:: pycon

    >>> query = House.select(House.address, House.features.slice('garage').alias('garage_data'))
    >>> for house in query:
    ...     print(house.address, house.garage_data)

    123 Main St {'garage': '2 cars'}

You can check for the existence of a key and filter rows accordingly:

.. code-block:: pycon

    >>> has_garage = House.features.exists('garage')
    >>> for house in House.select(House.address, has_garage.alias('has_garage')):
    ...     print(house.address, house.has_garage)

    123 Main St True

    >>> for house in House.select().where(House.features.exists('garage')):
    ...     print(house.address, house.features['garage'])  # <-- just houses w/garage data

    123 Main St 2 cars


Interval support
^^^^^^^^^^^^^^^^

Postgres supports durations through the ``INTERVAL`` data-type (`docs <https://www.postgresql.org/docs/current/static/datatype-datetime.html>`_).

.. py:class:: IntervalField([null=False, [...]])

    Field class capable of storing Python ``datetime.timedelta`` instances.

    Example:

    .. code-block:: python

        from datetime import timedelta

        from playhouse.postgres_ext import *

        db = PostgresqlExtDatabase('my_db')

        class Event(Model):
            location = CharField()
            duration = IntervalField()
            start_time = DateTimeField()

            class Meta:
                database = db

            @classmethod
            def get_long_meetings(cls):
                return cls.select().where(cls.duration > timedelta(hours=1))

.. _pgjson:

JSON Support
^^^^^^^^^^^^

peewee has basic support for Postgres' native JSON data type, in the form of
:py:class:`JSONField`. As of version 2.4.7, peewee also supports the Postgres
9.4 binary json ``jsonb`` type, via :py:class:`BinaryJSONField`.

.. warning::
  Postgres supports a JSON data type natively as of 9.2 (full support in 9.3).
  In order to use this functionality you must be using the correct version of
  Postgres with `psycopg2` version 2.5 or greater.

  To use :py:class:`BinaryJSONField`, which has many performance and querying
  advantages, you must have Postgres 9.4 or later.

.. note::
  You must be sure your database is an instance of
  :py:class:`PostgresqlExtDatabase` in order to use the `JSONField`.

Here is an example of how you might declare a model with a JSON field:

.. code-block:: python

    import json
    import urllib2
    from playhouse.postgres_ext import *

    db = PostgresqlExtDatabase('my_database')

    class APIResponse(Model):
        url = CharField()
        response = JSONField()

        class Meta:
            database = db

        @classmethod
        def request(cls, url):
            fh = urllib2.urlopen(url)
            return cls.create(url=url, response=json.loads(fh.read()))

    APIResponse.create_table()

    # Store a JSON response.
    offense = APIResponse.request('http://crime-api.com/api/offense/')
    booking = APIResponse.request('http://crime-api.com/api/booking/')

    # Query a JSON data structure using a nested key lookup:
    offense_responses = APIResponse.select().where(
        APIResponse.response['meta']['model'] == 'offense')

    # Retrieve a sub-key for each APIResponse. By calling .as_json(), the
    # data at the sub-key will be returned as Python objects (dicts, lists,
    # etc) instead of serialized JSON.
    q = (APIResponse
         .select(
           APIResponse.data['booking']['person'].as_json().alias('person'))
         .where(APIResponse.data['meta']['model'] == 'booking'))

    for result in q:
        print(result.person['name'], result.person['dob'])

The :py:class:`BinaryJSONField` works the same and supports the same operations
as the regular :py:class:`JSONField`, but provides several additional
operations for testing **containment**. Using the binary json field, you can
test whether your JSON data contains other partial JSON structures
(:py:meth:`~BinaryJSONField.contains`, :py:meth:`~BinaryJSONField.contains_any`,
:py:meth:`~BinaryJSONField.contains_all`), or whether it is a subset of a
larger JSON document (:py:meth:`~BinaryJSONField.contained_by`).

For more examples, see the :py:class:`JSONField` and
:py:class:`BinaryJSONField` API documents below.

.. _server_side_cursors:

Server-side cursors
^^^^^^^^^^^^^^^^^^^

When psycopg2 executes a query, normally all results are fetched and returned
to the client by the backend. This can cause your application to use a lot of
memory when making large queries. Using server-side cursors, results are
returned a little at a time (by default 2000 records). For the definitive
reference, please see the `psycopg2 documentation <http://initd.org/psycopg/docs/usage.html#server-side-cursors>`_.

.. note:: To use server-side (or named) cursors, you must be using :py:class:`PostgresqlExtDatabase`.

To execute a query using a server-side cursor, simply wrap your select query
using the :py:func:`ServerSide` helper:

.. code-block:: python

    large_query = PageView.select()  # Build query normally.

    # Iterate over large query inside a transaction.
    for page_view in ServerSide(large_query):
        # do some interesting analysis here.
        pass

    # Server-side resources are released.

If you would like all ``SELECT`` queries to automatically use a server-side
cursor, you can specify this when creating your :py:class:`PostgresqlExtDatabase`:

.. code-block:: python

    from postgres_ext import PostgresqlExtDatabase

    ss_db = PostgresqlExtDatabase('my_db', server_side_cursors=True)

.. note::
    Server-side cursors live only as long as the transaction, so for this reason
    peewee will not automatically call ``commit()`` after executing a ``SELECT``
    query. If you do not ``commit`` after you are done iterating, you will not
    release the server-side resources until the connection is closed (or the
    transaction is committed later). Furthermore, since peewee will by default
    cache rows returned by the cursor, you should always call ``.iterator()``
    when iterating over a large query.

    If you are using the :py:func:`ServerSide` helper, the transaction and
    call to ``iterator()`` will be handled transparently.


.. _pg_fts:

Full-text search
^^^^^^^^^^^^^^^^

Postgresql provides `sophisticated full-text search
<http://www.postgresql.org/docs/9.3/static/textsearch.html>`_ using special
data-types (``tsvector`` and ``tsquery``). Documents should be stored or
converted to the ``tsvector`` type, and search queries should be converted to
``tsquery``.

For simple cases, you can simply use the :py:func:`Match` function, which will
automatically perform the appropriate conversions, and requires no schema
changes:

.. code-block:: python

    def blog_search(query):
        return Blog.select().where(
            (Blog.status == Blog.STATUS_PUBLISHED) &
            Match(Blog.content, query))

The :py:func:`Match` function will automatically convert the left-hand operand
to a ``tsvector``, and the right-hand operand to a ``tsquery``. For better
performance, it is recommended you create a ``GIN`` index on the column you
plan to search:

.. code-block:: sql

    CREATE INDEX blog_full_text_search ON blog USING gin(to_tsvector(content));

Alternatively, you can use the :py:class:`TSVectorField` to maintain a
dedicated column for storing ``tsvector`` data:

.. code-block:: python

    class Blog(Model):
        content = TextField()
        search_content = TSVectorField()

You will need to explicitly convert the incoming text data to ``tsvector`` when
inserting or updating the ``search_content`` field:

.. code-block:: python

    content = 'Excellent blog post about peewee ORM.'
    blog_entry = Blog.create(
        content=content,
        search_content=fn.to_tsvector(content))

.. note:: If you are using the :py:class:`TSVectorField`, it will automatically be created with a GIN index.


postgres_ext API notes
^^^^^^^^^^^^^^^^^^^^^^

.. py:class:: PostgresqlExtDatabase(database[, server_side_cursors=False[, register_hstore=False[, ...]]])

    Identical to :py:class:`PostgresqlDatabase` but required in order to support:

    :param str database: Name of database to connect to.
    :param bool server_side_cursors: Whether ``SELECT`` queries should utilize
        server-side cursors.
    :param bool register_hstore: Register the HStore extension with the connection.

    * :ref:`server_side_cursors`
    * :py:class:`ArrayField`
    * :py:class:`DateTimeTZField`
    * :py:class:`JSONField`
    * :py:class:`BinaryJSONField`
    * :py:class:`HStoreField`
    * :py:class:`TSVectorField`

    If you wish to use the HStore extension, you must specify ``register_hstore=True``.

    If using ``server_side_cursors``, also be sure to wrap your queries with
    :py:func:`ServerSide`.

.. py:function:: ServerSide(select_query)

    :param select_query: a :py:class:`SelectQuery` instance.
    :rtype generator:

    Wrap the given select query in a transaction, and call it's
    :py:meth:`~SelectQuery.iterator` method to avoid caching row instances. In
    order for the server-side resources to be released, be sure to exhaust the
    generator (iterate over all the rows).

    Usage:

    .. code-block:: python

        large_query = PageView.select()
        for page_view in ServerSide(large_query):
            # Do something interesting.
            pass

        # At this point server side resources are released.

.. _pgarrays:

.. py:class:: ArrayField([field_class=IntegerField[, field_kwargs=None[, dimensions=1[, convert_values=False]]]])

    :param field_class: a subclass of :py:class:`Field`, e.g. :py:class:`IntegerField`.
    :param dict field_kwargs: arguments to initialize ``field_class``.
    :param int dimensions: dimensions of array.
    :param bool convert_values: apply ``field_class`` value conversion to array data.

    Field capable of storing arrays of the provided `field_class`.

    .. note::
        By default ArrayField will use a GIN index. To disable this, initialize
        the field with ``index=False``.

    You can store and retrieve lists (or lists-of-lists):

    .. code-block:: python

        class BlogPost(BaseModel):
            content = TextField()
            tags = ArrayField(CharField)


        post = BlogPost(content='awesome', tags=['foo', 'bar', 'baz'])

    Additionally, you can use the ``__getitem__`` API to query values or slices
    in the database:

    .. code-block:: python

        # Get the first tag on a given blog post.
        first_tag = (BlogPost
                     .select(BlogPost.tags[0].alias('first_tag'))
                     .where(BlogPost.id == 1)
                     .dicts()
                     .get())

        # first_tag = {'first_tag': 'foo'}

    Get a slice of values:

    .. code-block:: python

        # Get the first two tags.
        two_tags = (BlogPost
                    .select(BlogPost.tags[:2].alias('two'))
                    .dicts()
                    .get())
        # two_tags = {'two': ['foo', 'bar']}

    .. py:method:: contains(*items)

        :param items: One or more items that must be in the given array field.

        .. code-block:: python

            # Get all blog posts that are tagged with both "python" and "django".
            Blog.select().where(Blog.tags.contains('python', 'django'))

    .. py:method:: contains_any(*items)

        :param items: One or more items to search for in the given array field.

        Like :py:meth:`~ArrayField.contains`, except will match rows where the
        array contains *any* of the given items.

        .. code-block:: python

            # Get all blog posts that are tagged with "flask" and/or "django".
            Blog.select().where(Blog.tags.contains_any('flask', 'django'))

.. py:class:: DateTimeTZField(*args, **kwargs)

    A timezone-aware subclass of :py:class:`DateTimeField`.

.. py:class:: HStoreField(*args, **kwargs)

    A field for storing and retrieving arbitrary key/value pairs. For details
    on usage, see :ref:`hstore`.

    .. attention::
        To use the :py:class:`HStoreField` you will need to be sure the
        *hstore* extension is registered with the connection. To accomplish
        this, instantiate the :py:class:`PostgresqlExtDatabase` with
        ``register_hstore=True``.

    .. note::
        By default ``HStoreField`` will use a *GiST* index. To disable this,
        initialize the field with ``index=False``.

    .. py:method:: keys()

        Returns the keys for a given row.

        .. code-block:: pycon

            >>> for h in House.select(House.address, House.features.keys().alias('keys')):
            ...     print(h.address, h.keys)

            123 Main St [u'bath', u'garage']

    .. py:method:: values()

        Return the values for a given row.

        .. code-block:: pycon

            >>> for h in House.select(House.address, House.features.values().alias('vals')):
            ...     print(h.address, h.vals)

            123 Main St [u'2 bath', u'2 cars']

    .. py:method:: items()

        Like python's ``dict``, return the keys and values in a list-of-lists:

        .. code-block:: pycon

            >>> for h in House.select(House.address, House.features.items().alias('mtx')):
            ...     print(h.address, h.mtx)

            123 Main St [[u'bath', u'2 bath'], [u'garage', u'2 cars']]

    .. py:method:: slice(*args)

        Return a slice of data given a list of keys.

        .. code-block:: pycon

            >>> for h in House.select(House.address, House.features.slice('garage').alias('garage_data')):
            ...     print(h.address, h.garage_data)

            123 Main St {'garage': '2 cars'}

    .. py:method:: exists(key)

        Query for whether the given key exists.

        .. code-block:: pycon

            >>> for h in House.select(House.address, House.features.exists('garage').alias('has_garage')):
            ...     print(h.address, h.has_garage)

            123 Main St True

            >>> for h in House.select().where(House.features.exists('garage')):
            ...     print(h.address, h.features['garage']) # <-- just houses w/garage data

            123 Main St 2 cars

    .. py:method:: defined(key)

        Query for whether the given key has a value associated with it.

    .. py:method:: update(**data)

        Perform an atomic update to the keys/values for a given row or rows.

        .. code-block:: pycon

            >>> query = House.update(features=House.features.update(
            ...     sqft=2000,
            ...     year_built=2012))
            >>> query.where(House.id == 1).execute()

    .. py:method:: delete(*keys)

        Delete the provided keys for a given row or rows.

        .. note:: We will use an ``UPDATE`` query.

        .. code-block:: pycon

        >>> query = House.update(features=House.features.delete(
        ...     'sqft', 'year_built'))
        >>> query.where(House.id == 1).execute()

    .. py:method:: contains(value)

        :param value: Either a ``dict``, a ``list`` of keys, or a single key.

        Query rows for the existence of either:

        * a partial dictionary.
        * a list of keys.
        * a single key.

        .. code-block:: pycon

            >>> query = House.select()
            >>> has_garage = query.where(House.features.contains('garage'))
            >>> garage_bath = query.where(House.features.contains(['garage', 'bath']))
            >>> twocar = query.where(House.features.contains({'garage': '2 cars'}))

    .. py:method:: contains_any(*keys)

        :param keys: One or more keys to search for.

        Query rows for the existince of *any* key.

.. py:class:: JSONField(dumps=None, *args, **kwargs)

    :param dumps: The default is to call json.dumps() or the dumps function.
        You can override this method to create a customized JSON wrapper.

    Field class suitable for storing and querying arbitrary JSON. When using
    this on a model, set the field's value to a Python object (either a
    ``dict`` or a ``list``). When you retrieve your value from the database it
    will be returned as a Python data structure.

    .. note:: You must be using Postgres 9.2 / psycopg2 2.5 or greater.

    .. note::
        If you are using Postgres 9.4, strongly consider using the
        :py:class:`BinaryJSONField` instead as it offers better performance and
        more powerful querying options.

    Example model declaration:

    .. code-block:: python

        db = PostgresqlExtDatabase('my_db')

        class APIResponse(Model):
            url = CharField()
            response = JSONField()

            class Meta:
                database = db

    Example of storing JSON data:

    .. code-block:: python

        url = 'http://foo.com/api/resource/'
        resp = json.loads(urllib2.urlopen(url).read())
        APIResponse.create(url=url, response=resp)

        APIResponse.create(url='http://foo.com/baz/', response={'key': 'value'})

    To query, use Python's ``[]`` operators to specify nested key or array lookups:

    .. code-block:: python

        APIResponse.select().where(
            APIResponse.response['key1']['nested-key'] == 'some-value')

    To illustrate the use of the ``[]`` operators, imagine we have the
    following data stored in an ``APIResponse``:

    .. code-block:: javascript

        {
          "foo": {
            "bar": ["i1", "i2", "i3"],
            "baz": {
              "huey": "mickey",
              "peewee": "nugget"
            }
          }
        }

    Here are the results of a few queries:

    .. code-block:: python

        def get_data(expression):
            # Helper function to just retrieve the results of a
            # particular expression.
            query = (APIResponse
                     .select(expression.alias('my_data'))
                     .dicts()
                     .get())
            return query['my_data']

        # Accessing the foo -> bar subkey will return a JSON
        # representation of the list.
        get_data(APIResponse.data['foo']['bar'])
        # '["i1", "i2", "i3"]'

        # In order to retrieve this list as a Python list,
        # we will call .as_json() on the expression.
        get_data(APIResponse.data['foo']['bar'].as_json())
        # ['i1', 'i2', 'i3']

        # Similarly, accessing the foo -> baz subkey will
        # return a JSON representation of the dictionary.
        get_data(APIResponse.data['foo']['baz'])
        # '{"huey": "mickey", "peewee": "nugget"}'

        # Again, calling .as_json() will return an actual
        # python dictionary.
        get_data(APIResponse.data['foo']['baz'].as_json())
        # {'huey': 'mickey', 'peewee': 'nugget'}

        # When dealing with simple values, either way works as
        # you expect.
        get_data(APIResponse.data['foo']['bar'][0])
        # 'i1'

        # Calling .as_json() when the result is a simple value
        # will return the same thing as the previous example.
        get_data(APIResponse.data['foo']['bar'][0].as_json())
        # 'i1'

.. py:class:: BinaryJSONField(dumps=None, *args, **kwargs)

    :param dumps: The default is to call json.dumps() or the dumps function.
      You can override this method to create a customized JSON wrapper.

    Store and query arbitrary JSON documents. Data should be stored using
    normal Python ``dict`` and ``list`` objects, and when data is returned from
    the database, it will be returned using ``dict`` and ``list`` as well.

    For examples of basic query operations, see the above code samples for
    :py:class:`JSONField`. The example queries below will use the same
    ``APIResponse`` model described above.

    .. note::
        By default BinaryJSONField will use a GiST index. To disable this,
        initialize the field with ``index=False``.

    .. note:: You must be using Postgres 9.4 / psycopg2 2.5 or newer. If you are using Postgres 9.2 or 9.3, you can use the regular :py:class:`JSONField` instead.

    .. py:method:: contains(other)

        Test whether the given JSON data contains the given JSON fragment or key.

        Example:

        .. code-block:: python

            search_fragment = {
                'foo': {'bar': ['i2']}
            }
            query = (APIResponse
                     .select()
                     .where(APIResponse.data.contains(search_fragment)))

            # If we're searching for a list, the list items do not need to
            # be ordered in a particular way:
            query = (APIResponse
                     .select()
                     .where(APIResponse.data.contains({
                         'foo': {'bar': ['i2', 'i1']}})))

        We can pass in simple keys as well. To find APIResponses that contain the key ``foo`` at the top-level:

        .. code-block:: python

            APIResponse.select().where(APIResponse.data.contains('foo'))

        We can also search sub-keys using square-brackets:

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data['foo']['bar'].contains(['i2', 'i1']))

    .. py:method:: contains_any(*items)

        Search for the presence of one or more of the given items.

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data.contains_any('foo', 'baz', 'nugget'))

        Like :py:meth:`~BinaryJSONField.contains`, we can also search sub-keys:

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data['foo']['bar'].contains_any('i2', 'ix'))

    .. py:method:: contains_all(*items)

        Search for the presence of all of the given items.

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data.contains_all('foo'))

        Like :py:meth:`~BinaryJSONField.contains_any`, we can also search sub-keys:

        .. code-block:: python

            APIResponse.select().where(
                APIResponse.data['foo']['bar'].contains_all('i1', 'i2', 'i3'))

    .. py:method:: contained_by(other)

        Test whether the given JSON document is contained by (is a subset of) the given JSON document. This method is the inverse of :py:meth:`~BinaryJSONField.contains`.

        .. code-block:: python

            big_doc = {
                'foo': {
                    'bar': ['i1', 'i2', 'i3'],
                    'baz': {
                        'huey': 'mickey',
                        'peewee': 'nugget',
                    }
                },
                'other_key': ['nugget', 'bear', 'kitten'],
            }
            APIResponse.select().where(
                APIResponse.data.contained_by(big_doc))


.. py:function:: Match(field, query)

    Generate a full-text search expression, automatically converting the
    left-hand operand to a ``tsvector``, and the right-hand operand to a
    ``tsquery``.

    Example:

    .. code-block:: python

        def blog_search(query):
            return Blog.select().where(
                (Blog.status == Blog.STATUS_PUBLISHED) &
                Match(Blog.content, query))

.. py:class:: TSVectorField

    Field type suitable for storing ``tsvector`` data. This field will
    automatically be created with a ``GIN`` index for improved search
    performance.

    .. note::
        Data stored in this field will still need to be manually converted to
        the ``tsvector`` type.

    .. note::
        By default TSVectorField will use a GIN index. To disable this,
        initialize the field with ``index=False``.

     Example usage:

     .. code-block:: python

          class Blog(Model):
              content = TextField()
              search_content = TSVectorField()

          content = 'this is a sample blog entry.'
          blog_entry = Blog.create(
              content=content,
              search_content=fn.to_tsvector(content))  # Note `to_tsvector()`.


.. _mysql_ext:

MySQL Extensions
----------------

Peewee provides an alternate database implementation for using the
`mysql-connector <https://dev.mysql.com/doc/connector-python/en/>`_ driver. The
implementation can be found in ``playhouse.mysql_ext``.

Example usage:

.. code-block:: python

    from playhouse.mysql_ext import MySQLConnectorDatabase

    # MySQL database implementation that utilizes mysql-connector driver.
    db = MySQLConnectorDatabase('my_database', host='1.2.3.4', user='mysql')

.. _dataset:

DataSet
-------

The *dataset* module contains a high-level API for working with databases
modeled after the popular `project of the same name <https://dataset.readthedocs.io/en/latest/index.html>`_.
The aims of the *dataset* module are to provide:

* A simplified API for working with relational data, along the lines of working with JSON.
* An easy way to export relational data as JSON or CSV.
* An easy way to import JSON or CSV data into a relational database.

A minimal data-loading script might look like this:

.. code-block:: python

    from playhouse.dataset import DataSet

    db = DataSet('sqlite:///:memory:')

    table = db['sometable']
    table.insert(name='Huey', age=3)
    table.insert(name='Mickey', age=5, gender='male')

    huey = table.find_one(name='Huey')
    print huey
    # {'age': 3, 'gender': None, 'id': 1, 'name': 'Huey'}

    for obj in table:
        print obj
    # {'age': 3, 'gender': None, 'id': 1, 'name': 'Huey'}
    # {'age': 5, 'gender': 'male', 'id': 2, 'name': 'Mickey'}

You can export or import data using :py:meth:`~DataSet.freeze` and
:py:meth:`~DataSet.thaw`:

.. code-block:: python

    # Export table content to the `users.json` file.
    db.freeze(table.all(), format='json', filename='users.json')

    # Import data from a CSV file into a new table. Columns will be automatically
    # created for each field in the CSV file.
    new_table = db['stats']
    new_table.thaw(format='csv', filename='monthly_stats.csv')

Getting started
^^^^^^^^^^^^^^^

:py:class:`DataSet` objects are initialized by passing in a database URL of the
format ``dialect://user:password@host/dbname``. See the :ref:`db_url` section
for examples of connecting to various databases.

.. code-block:: python

    # Create an in-memory SQLite database.
    db = DataSet('sqlite:///:memory:')

Storing data
^^^^^^^^^^^^

To store data, we must first obtain a reference to a table. If the table does
not exist, it will be created automatically:

.. code-block:: python

    # Get a table reference, creating the table if it does not exist.
    table = db['users']

We can now :py:meth:`~Table.insert` new rows into the table. If the columns do
not exist, they will be created automatically:

.. code-block:: python

    table.insert(name='Huey', age=3, color='white')
    table.insert(name='Mickey', age=5, gender='male')

To update existing entries in the table, pass in a dictionary containing the
new values and filter conditions. The list of columns to use as filters is
specified in the *columns* argument. If no filter columns are specified, then
all rows will be updated.

.. code-block:: python

    # Update the gender for "Huey".
    table.update(name='Huey', gender='male', columns=['name'])

    # Update all records. If the column does not exist, it will be created.
    table.update(favorite_orm='peewee')

Importing data
^^^^^^^^^^^^^^

To import data from an external source, such as a JSON or CSV file, you can use
the :py:meth:`~Table.thaw` method. By default, new columns will be created for
any attributes encountered. If you wish to only populate columns that are
already defined on a table, you can pass in ``strict=True``.

.. code-block:: python

    # Load data from a JSON file containing a list of objects.
    table = dataset['stock_prices']
    table.thaw(filename='stocks.json', format='json')
    table.all()[:3]

    # Might print...
    [{'id': 1, 'ticker': 'GOOG', 'price': 703},
     {'id': 2, 'ticker': 'AAPL', 'price': 109},
     {'id': 3, 'ticker': 'AMZN', 'price': 300}]


Using transactions
^^^^^^^^^^^^^^^^^^

DataSet supports nesting transactions using a simple context manager.

.. code-block:: python

    table = db['users']
    with db.transaction() as txn:
        table.insert(name='Charlie')

        with db.transaction() as nested_txn:
            # Set Charlie's favorite ORM to Django.
            table.update(name='Charlie', favorite_orm='django', columns=['name'])

            # jk/lol
            nested_txn.rollback()

Inspecting the database
^^^^^^^^^^^^^^^^^^^^^^^

You can use the :py:meth:`tables` method to list the tables in the current
database:

.. code-block:: pycon

    >>> print db.tables
    ['sometable', 'user']

And for a given table, you can print the columns:

.. code-block:: pycon

    >>> table = db['user']
    >>> print table.columns
    ['id', 'age', 'name', 'gender', 'favorite_orm']

We can also find out how many rows are in a table:

.. code-block:: pycon

    >>> print len(db['user'])
    3

Reading data
^^^^^^^^^^^^

To retrieve all rows, you can use the :py:meth:`~Table.all` method:

.. code-block:: python

    # Retrieve all the users.
    users = db['user'].all()

    # We can iterate over all rows without calling `.all()`
    for user in db['user']:
        print user['name']

Specific objects can be retrieved using :py:meth:`~Table.find` and
:py:meth:`~Table.find_one`.

.. code-block:: python

    # Find all the users who like peewee.
    peewee_users = db['user'].find(favorite_orm='peewee')

    # Find Huey.
    huey = db['user'].find_one(name='Huey')

Exporting data
^^^^^^^^^^^^^^

To export data, use the :py:meth:`~DataSet.freeze` method, passing in the query
you wish to export:

.. code-block:: python

    peewee_users = db['user'].find(favorite_orm='peewee')
    db.freeze(peewee_users, format='json', filename='peewee_users.json')

API
^^^

.. py:class:: DataSet(url)

    :param str url: A database URL. See :ref:`db_url` for examples.

    The *DataSet* class provides a high-level API for working with relational
    databases.

    .. py:attribute:: tables

        Return a list of tables stored in the database. This list is computed
        dynamically each time it is accessed.

    .. py:method:: __getitem__(table_name)

        Provide a :py:class:`Table` reference to the specified table. If the
        table does not exist, it will be created.

    .. py:method:: query(sql[, params=None[, commit=True]])

        :param str sql: A SQL query.
        :param list params: Optional parameters for the query.
        :param bool commit: Whether the query should be committed upon execution.
        :return: A database cursor.

        Execute the provided query against the database.

    .. py:method:: transaction()

        Create a context manager representing a new transaction (or savepoint).

    .. py:method:: freeze(query[, format='csv'[, filename=None[, file_obj=None[, **kwargs]]]])

        :param query: A :py:class:`SelectQuery`, generated using :py:meth:`~Table.all` or `~Table.find`.
        :param format: Output format. By default, *csv* and *json* are supported.
        :param filename: Filename to write output to.
        :param file_obj: File-like object to write output to.
        :param kwargs: Arbitrary parameters for export-specific functionality.

    .. py:method:: thaw(table[, format='csv'[, filename=None[, file_obj=None[, strict=False[, **kwargs]]]]])

        :param str table: The name of the table to load data into.
        :param format: Input format. By default, *csv* and *json* are supported.
        :param filename: Filename to read data from.
        :param file_obj: File-like object to read data from.
        :param bool strict: Whether to store values for columns that do not already exist on the table.
        :param kwargs: Arbitrary parameters for import-specific functionality.

    .. py:method:: connect()

        Open a connection to the underlying database. If a connection is not
        opened explicitly, one will be opened the first time a query is
        executed.

    .. py:method:: close()

        Close the connection to the underlying database.

.. py:class:: Table(dataset, name, model_class)

    Provides a high-level API for working with rows in a given table.

    .. py:attribute:: columns

        Return a list of columns in the given table.

    .. py:attribute:: model_class

        A dynamically-created :py:class:`Model` class.

    .. py:method:: create_index(columns[, unique=False])

        Create an index on the given columns:

        .. code-block:: python

            # Create a unique index on the `username` column.
            db['users'].create_index(['username'], unique=True)

    .. py:method:: insert(**data)

        Insert the given data dictionary into the table, creating new columns
        as needed.

    .. py:method:: update(columns=None, conjunction=None, **data)

        Update the table using the provided data. If one or more columns are
        specified in the *columns* parameter, then those columns' values in the
        *data* dictionary will be used to determine which rows to update.

        .. code-block:: python

            # Update all rows.
            db['users'].update(favorite_orm='peewee')

            # Only update Huey's record, setting his age to 3.
            db['users'].update(name='Huey', age=3, columns=['name'])

    .. py:method:: find(**query)

        Query the table for rows matching the specified equality conditions. If
        no query is specified, then all rows are returned.

        .. code-block:: python

            peewee_users = db['users'].find(favorite_orm='peewee')

    .. py:method:: find_one(**query)

        Return a single row matching the specified equality conditions. If no
        matching row is found then ``None`` will be returned.

        .. code-block:: python

            huey = db['users'].find_one(name='Huey')

    .. py:method:: all()

        Return all rows in the given table.

    .. py:method:: delete(**query)

        Delete all rows matching the given equality conditions. If no query is
        provided, then all rows will be deleted.

        .. code-block:: python

            # Adios, Django!
            db['users'].delete(favorite_orm='Django')

            # Delete all the secret messages.
            db['secret_messages'].delete()

    .. py:method:: freeze([format='csv'[, filename=None[, file_obj=None[, **kwargs]]]])

        :param format: Output format. By default, *csv* and *json* are supported.
        :param filename: Filename to write output to.
        :param file_obj: File-like object to write output to.
        :param kwargs: Arbitrary parameters for export-specific functionality.

    .. py:method:: thaw([format='csv'[, filename=None[, file_obj=None[, strict=False[, **kwargs]]]]])

        :param format: Input format. By default, *csv* and *json* are supported.
        :param filename: Filename to read data from.
        :param file_obj: File-like object to read data from.
        :param bool strict: Whether to store values for columns that do not already exist on the table.
        :param kwargs: Arbitrary parameters for import-specific functionality.

.. _extra-fields:

Fields
------

These fields can be found in the ``playhouse.fields`` module.

.. py:class:: CompressedField([compression_level=6[, algorithm='zlib'[, **kwargs]]])

    :param int compression_level: A value from 0 to 9.
    :param str algorithm: Either ``'zlib'`` or ``'bz2'``.

    Stores compressed data using the specified algorithm. This field extends
    :py:class:`BlobField`, transparently storing a compressed representation of
    the data in the database.

.. py:class:: PickleField()

    Stores arbitrary Python data by transparently pickling and un-pickling data
    stored in the field. This field extends :py:class:`BlobField`. If the
    ``cPickle`` module is available, it will be used.

.. _hybrid:

Hybrid Attributes
-----------------

Hybrid attributes encapsulate functionality that operates at both the Python
*and* SQL levels. The idea for hybrid attributes comes from a feature of the
`same name in SQLAlchemy <http://docs.sqlalchemy.org/en/improve_toc/orm/extensions/hybrid.html>`_.
Consider the following example:

.. code-block:: python

    class Interval(Model):
        start = IntegerField()
        end = IntegerField()

        @hybrid_property
        def length(self):
            return self.end - self.start

        @hybrid_method
        def contains(self, point):
            return (self.start <= point) & (point < self.end)

The *hybrid attribute* gets its name from the fact that the ``length``
attribute will behave differently depending on whether it is accessed via the
``Interval`` class or an ``Interval`` instance.

If accessed via an instance, then it behaves just as you would expect.

If accessed via the ``Interval.length`` class attribute, however, the length
calculation will be expressed as a SQL expression. For example:

.. code-block:: python

    query = Interval.select().where(Interval.length > 5)

This query will be equivalent to the following SQL:

.. code-block:: sql

    SELECT "t1"."id", "t1"."start", "t1"."end"
    FROM "interval" AS t1
    WHERE (("t1"."end" - "t1"."start") > 5)

The ``playhouse.hybrid`` module also contains a decorator for implementing
hybrid methods which can accept parameters. As with hybrid properties, when
accessed via a model instance, then the function executes normally as-written.
When the hybrid method is called on the class, however, it will generate a SQL
expression.

Example:

.. code-block:: python

    query = Interval.select().where(Interval.contains(2))

This query is equivalent to the following SQL:

.. code-block:: sql

    SELECT "t1"."id", "t1"."start", "t1"."end"
    FROM "interval" AS t1
    WHERE (("t1"."start" <= 2) AND (2 < "t1"."end"))

There is an additional API for situations where the python implementation differs slightly from the SQL implementation. Let's add a ``radius`` method to the ``Interval`` model. Because this method calculates an absolute value, we will use the Python ``abs()`` function for the instance portion and the ``fn.ABS()`` SQL function for the class portion.

.. code-block:: python

    class Interval(Model):
        start = IntegerField()
        end = IntegerField()

        @hybrid_property
        def length(self):
            return self.end - self.start

        @hybrid_property
        def radius(self):
            return abs(self.length) / 2

        @radius.expression
        def radius(cls):
            return fn.ABS(cls.length) / 2

What is neat is that both the ``radius`` implementations refer to the
``length`` hybrid attribute! When accessed via an ``Interval`` instance, the
radius calculation will be executed in Python. When invoked via an ``Interval``
class, we will get the appropriate SQL.

Example:

.. code-block:: python

    query = Interval.select().where(Interval.radius < 3)

This query is equivalent to the following SQL:

.. code-block:: sql

    SELECT "t1"."id", "t1"."start", "t1"."end"
    FROM "interval" AS t1
    WHERE ((abs("t1"."end" - "t1"."start") / 2) < 3)

Pretty neat, right? Thanks for the cool idea, SQLAlchemy!

Hybrid API
^^^^^^^^^^

.. py:class:: hybrid_method(func[, expr=None])

    Method decorator that allows the definition of a Python object method with
    both instance-level and class-level behavior.

    Example:

    .. code-block:: python

        class Interval(Model):
            start = IntegerField()
            end = IntegerField()

            @hybrid_method
            def contains(self, point):
                return (self.start <= point) & (point < self.end)

    When called with an ``Interval`` instance, the ``contains`` method will
    behave as you would expect. When called as a classmethod, though, a SQL
    expression will be generated:

    .. code-block:: python

        query = Interval.select().where(Interval.contains(2))

    Would generate the following SQL:

    .. code-block:: sql

        SELECT "t1"."id", "t1"."start", "t1"."end"
        FROM "interval" AS t1
        WHERE (("t1"."start" <= 2) AND (2 < "t1"."end"))

    .. py:method:: expression(expr)

        Method decorator for specifying the SQL-expression producing method.

.. py:class:: hybrid_property(fget[, fset=None[, fdel=None[, expr=None]]])

    Method decorator that allows the definition of a Python object property
    with both instance-level and class-level behavior.

    Examples:

    .. code-block:: python

        class Interval(Model):
            start = IntegerField()
            end = IntegerField()

            @hybrid_property
            def length(self):
                return self.end - self.start

            @hybrid_property
            def radius(self):
                return abs(self.length) / 2

            @radius.expression
            def radius(cls):
                return fn.ABS(cls.length) / 2

    When accessed on an ``Interval`` instance, the ``length`` and ``radius``
    properties will behave as you would expect. When accessed as class
    attributes, though, a SQL expression will be generated instead:

    .. code-block:: python

        query = (Interval
                 .select()
                 .where(
                     (Interval.length > 6) &
                     (Interval.radius >= 3)))

    Would generate the following SQL:

    .. code-block:: sql

        SELECT "t1"."id", "t1"."start", "t1"."end"
        FROM "interval" AS t1
        WHERE (
            (("t1"."end" - "t1"."start") > 6) AND
            ((abs("t1"."end" - "t1"."start") / 2) >= 3)
        )

.. _kv:

Key/Value Store
---------------

The ``playhouse.kv`` module contains the implementation of a persistent
dictionary.

.. py:class:: KeyValue([key_field=None[, value_field=None[, ordered=False[, database=None[, table_name='keyvalue']]]]])

    :param Field key_field: field to use for key. Defaults to
        :py:class:`CharField`. **Must have** ``primary_key=True``.
    :param Field value_field: field to use for value. Defaults to
        :py:class:`PickleField`.
    :param bool ordered: data should be returned in key-sorted order.
    :param Database database: database where key/value data is stored. If not
        specified, an in-memory SQLite database will be used.
    :param str table_name: table name for data storage.

    Dictionary-like API for storing key/value data. Like dictionaries, supports
    the expected APIs, but also has the added capability of accepting
    expressions for getting, setting and deleting items.

    Table is created automatically (if it doesn't exist) when the ``KeyValue``
    is instantiated.

    Basic examples:

    .. code-block:: python

        # Create a key/value store, which uses an in-memory SQLite database
        # for data storage.
        KV = KeyValue()

        # Set (or overwrite) the value for "k1".
        KV['k1'] = 'v1'

        # Set (or update) multiple keys at once.
        KV.update(k2='v2', k3='v3')

        # Getting values works as you'd expect.
        assert KV['k2'] == 'v2'

        # We can also do this:
        for value in KV[KV.key > 'k1']:
            print(value)

        # 'v2'
        # 'v3'

        # Update multiple values at once using expression:
        KV[KV.key > 'k1'] = 'vx'

        # What's stored in the KV?
        print(dict(KV))

        # {'k1': 'v1', 'k2': 'vx', 'k3': 'vx'}

        # Delete a single item.
        del KV['k2']

        # How many items are stored in the KV?
        print(len(KV))
        # 2

        # Delete items that match the given condition.
        del KV[KV.key > 'k1']

    .. py:method:: __contains__(expr)

        :param expr: a single key or an expression
        :returns: Boolean whether key/expression exists.

        Example:

        .. code-block:: pycon

            >>> kv = KeyValue()
            >>> kv.update(k1='v1', k2='v2')

            >>> 'k1' in kv
            True
            >>> 'kx' in kv
            False

            >>> (KV.key < 'k2') in KV
            True
            >>> (KV.key > 'k2') in KV
            False

    .. py:method:: __len__()

        :returns: Count of items stored.

    .. py:method:: __getitem__(expr)

        :param expr: a single key or an expression.
        :returns: value(s) corresponding to key/expression.
        :raises: ``KeyError`` if single key given and not found.

        Examples:

        .. code-block:: pycon

            >>> KV = KeyValue()
            >>> KV.update(k1='v1', k2='v2', k3='v3')

            >>> KV['k1']
            'v1'
            >>> KV['kx']
            KeyError: "kx" not found

            >>> KV[KV.key > 'k1']
            ['v2', 'v3']
            >>> KV[KV.key < 'k1']
            []

    .. py:method:: __setitem__(expr, value)

        :param expr: a single key or an expression.
        :param value: value to set for key(s)

        Set value for the given key. If ``expr`` is an expression, then any
        keys matching the expression will have their value updated.

        Example:

        .. code-block:: pycon

            >>> KV = KeyValue()
            >>> KV.update(k1='v1', k2='v2', k3='v3')

            >>> KV['k1'] = 'v1-x'
            >>> print(KV['k1'])
            'v1-x'

            >>> KV[KV.key >= 'k2'] = 'v99'
            >>> dict(KV)
            {'k1': 'v1-x', 'k2': 'v99', 'k3': 'v99'}

    .. py:method:: __delitem__(expr)

        :param expr: a single key or an expression.

        Delete the given key. If an expression is given, delete all keys that
        match the expression.

        Example:

        .. code-block:: pycon

            >>> KV = KeyValue()
            >>> KV.update(k1=1, k2=2, k3=3)

            >>> del KV['k1']  # Deletes "k1".
            >>> del KV['k1']
            KeyError: "k1" does not exist

            >>> del KV[KV.key > 'k2']  # Deletes "k3".
            >>> del KV[KV.key > 'k99']  # Nothing deleted, no keys match.

    .. py:method:: keys()

        :returns: an iterable of all keys in the table.

    .. py:method:: values()

        :returns: an iterable of all values in the table.

    .. py:method:: items()

        :returns: an iterable of all key/value pairs in the table.

    .. py:method:: update([__data=None[, **mapping]])

        Efficiently bulk-insert or replace the given key/value pairs.

        Example:

        .. code-block:: pycon

            >>> KV = KeyValue()
            >>> KV.update(k1=1, k2=2)  # Sets 'k1'=1, 'k2'=2.

            >>> dict(KV)
            {'k1': 1, 'k2': 2}

            >>> KV.update(k2=22, k3=3)  # Updates 'k2'->22, sets 'k3'=3.

            >>> dict(KV)
            {'k1': 1, 'k2': 22, 'k3': 3}

            >>> KV.update({'k2': -2, 'k4': 4})  # Also can pass a dictionary.

            >>> dict(KV)
            {'k1': 1, 'k2': -2, 'k3': 3, 'k4': 4}

        .. attention::
            Because Postgresql does not support INSERT + REPLACE, the
            :py:meth:`KeyValue.update` method is not supported for Postgresql
            databases (as it cannot be implemented efficiently).

    .. py:method:: get(expr[, default=None])

        :param expr: a single key or an expression.
        :param default: default value if key not found.
        :returns: value of given key/expr or default if single key not found.

        Get the value at the given key. If the key does not exist, the default
        value is returned, unless the key is an expression in which case an
        empty list will be returned.

    .. py:method:: pop(expr[, default=Sentinel])

        :param expr: a single key or an expression.
        :param default: default value if key does not exist.
        :returns: value of given key/expr or default if single key not found.

        Get value and delete the given key. If the key does not exist, the
        default value is returned, unless the key is an expression in which
        case an empty list is returned.

    .. py:method:: clear()

        Remove all items from the key-value table.


.. _shortcuts:

Shortcuts
---------

This module contains helper functions for expressing things that would
otherwise be somewhat verbose or cumbersome using peewee's APIs. There are also
helpers for serializing models to dictionaries and vice-versa.

.. py:function:: model_to_dict(model[, recurse=True[, backrefs=False[, only=None[, exclude=None[, extra_attrs=None[, fields_from_query=None[, max_depth=None[, manytomany=False]]]]]]]])

    :param bool recurse: Whether foreign-keys should be recursed.
    :param bool backrefs: Whether lists of related objects should be recursed.
    :param only: A list (or set) of field instances which should be included in the result dictionary.
    :param exclude: A list (or set) of field instances which should be excluded from the result dictionary.
    :param extra_attrs: A list of attribute or method names on the instance which should be included in the dictionary.
    :param Select fields_from_query: The :py:class:`SelectQuery` that created this model instance. Only the fields and values explicitly selected by the query will be serialized.
    :param int max_depth: Maximum depth when recursing.
    :param bool manytomany: Process many-to-many fields.

    Convert a model instance (and optionally any related instances) to
    a dictionary.

    Examples:

    .. code-block:: pycon

        >>> user = User.create(username='charlie')
        >>> model_to_dict(user)
        {'id': 1, 'username': 'charlie'}

        >>> model_to_dict(user, backrefs=True)
        {'id': 1, 'tweets': [], 'username': 'charlie'}

        >>> t1 = Tweet.create(user=user, message='tweet-1')
        >>> t2 = Tweet.create(user=user, message='tweet-2')
        >>> model_to_dict(user, backrefs=True)
        {
          'id': 1,
          'tweets': [
            {'id': 1, 'message': 'tweet-1'},
            {'id': 2, 'message': 'tweet-2'},
          ],
          'username': 'charlie'
        }

        >>> model_to_dict(t1)
        {
          'id': 1,
          'message': 'tweet-1',
          'user': {
            'id': 1,
            'username': 'charlie'
          }
        }

        >>> model_to_dict(t2, recurse=False)
        {'id': 1, 'message': 'tweet-2', 'user': 1}

.. py:function:: dict_to_model(model_class, data[, ignore_unknown=False])

    :param Model model_class: The model class to construct.
    :param dict data: A dictionary of data. Foreign keys can be included as nested dictionaries, and back-references as lists of dictionaries.
    :param bool ignore_unknown: Whether to allow unrecognized (non-field) attributes.

    Convert a dictionary of data to a model instance, creating related
    instances where appropriate.

    Examples:

    .. code-block:: pycon

        >>> user_data = {'id': 1, 'username': 'charlie'}
        >>> user = dict_to_model(User, user_data)
        >>> user
        <__main__.User at 0x7fea8fa4d490>

        >>> user.username
        'charlie'

        >>> note_data = {'id': 2, 'text': 'note text', 'user': user_data}
        >>> note = dict_to_model(Note, note_data)
        >>> note.text
        'note text'
        >>> note.user.username
        'charlie'

        >>> user_with_notes = {
        ...     'id': 1,
        ...     'username': 'charlie',
        ...     'notes': [{'id': 1, 'text': 'note-1'}, {'id': 2, 'text': 'note-2'}]}
        >>> user = dict_to_model(User, user_with_notes)
        >>> user.notes[0].text
        'note-1'
        >>> user.notes[0].user.username
        'charlie'


.. py:function:: update_model_from_dict(instance, data[, ignore_unknown=False])

    :param Model instance: The model instance to update.
    :param dict data: A dictionary of data. Foreign keys can be included as nested dictionaries, and back-references as lists of dictionaries.
    :param bool ignore_unknown: Whether to allow unrecognized (non-field) attributes.

    Update a model instance with the given data dictionary.

.. _signals:

Signal support
--------------

Models with hooks for signals (a-la django) are provided in
``playhouse.signals``. To use the signals, you will need all of your project's
models to be a subclass of ``playhouse.signals.Model``, which overrides the
necessary methods to provide support for the various signals.

.. code-block:: python

    from playhouse.signals import Model, post_save


    class MyModel(Model):
        data = IntegerField()

    @post_save(sender=MyModel)
    def on_save_handler(model_class, instance, created):
        put_data_in_cache(instance.data)

.. warning::
    For what I hope are obvious reasons, Peewee signals do not work when you
    use the :py:meth:`Model.insert`, :py:meth:`Model.update`, or
    :py:meth:`Model.delete` methods. These methods generate queries that
    execute beyond the scope of the ORM, and the ORM does not know about which
    model instances might or might not be affected when the query executes.

    Signals work by hooking into the higher-level peewee APIs like
    :py:meth:`Model.save` and :py:meth:`Model.delete_instance`, where the
    affected model instance is known ahead of time.

The following signals are provided:

``pre_save``
    Called immediately before an object is saved to the database. Provides an
    additional keyword argument ``created``, indicating whether the model is being
    saved for the first time or updated.
``post_save``
    Called immediately after an object is saved to the database. Provides an
    additional keyword argument ``created``, indicating whether the model is being
    saved for the first time or updated.
``pre_delete``
    Called immediately before an object is deleted from the database when :py:meth:`Model.delete_instance`
    is used.
``post_delete``
    Called immediately after an object is deleted from the database when :py:meth:`Model.delete_instance`
    is used.
``pre_init``
    Called when a model class is first instantiated


Connecting handlers
^^^^^^^^^^^^^^^^^^^

Whenever a signal is dispatched, it will call any handlers that have been
registered. This allows totally separate code to respond to events like model
save and delete.

The :py:class:`Signal` class provides a :py:meth:`~Signal.connect` method,
which takes a callback function and two optional parameters for "sender" and
"name". If specified, the "sender" parameter should be a single model class
and allows your callback to only receive signals from that one model class.
The "name" parameter is used as a convenient alias in the event you wish to
unregister your signal handler.

Example usage:

.. code-block:: python

    from playhouse.signals import *

    def post_save_handler(sender, instance, created):
        print '%s was just saved' % instance

    # our handler will only be called when we save instances of SomeModel
    post_save.connect(post_save_handler, sender=SomeModel)

All signal handlers accept as their first two arguments ``sender`` and
``instance``, where ``sender`` is the model class and ``instance`` is the
actual model being acted upon.

If you'd like, you can also use a decorator to connect signal handlers. This
is functionally equivalent to the above example:

.. code-block:: python

    @post_save(sender=SomeModel)
    def post_save_handler(sender, instance, created):
        print '%s was just saved' % instance


Signal API
^^^^^^^^^^

.. py:class:: Signal()

    Stores a list of receivers (callbacks) and calls them when the "send"
    method is invoked.

    .. py:method:: connect(receiver[, sender=None[, name=None]])

        :param callable receiver: a callable that takes at least two parameters,
            a "sender", which is the Model subclass that triggered the signal, and
            an "instance", which is the actual model instance.
        :param Model sender: if specified, only instances of this model class will
            trigger the receiver callback.
        :param string name: a short alias

        Add the receiver to the internal list of receivers, which will be called
        whenever the signal is sent.

        .. code-block:: python

            from playhouse.signals import post_save
            from project.handlers import cache_buster

            post_save.connect(cache_buster, name='project.cache_buster')

    .. py:method:: disconnect([receiver=None[, name=None]])

        :param callable receiver: the callback to disconnect
        :param string name: a short alias

        Disconnect the given receiver (or the receiver with the given name alias)
        so that it no longer is called. Either the receiver or the name must be
        provided.

        .. code-block:: python

            post_save.disconnect(name='project.cache_buster')

    .. py:method:: send(instance, *args, **kwargs)

        :param instance: a model instance

        Iterates over the receivers and will call them in the order in which
        they were connected. If the receiver specified a sender, it will only
        be called if the instance is an instance of the sender.


    .. py:method __call__([sender=None[, name=None]])

        Function decorator that is an alias for a signal's connect method:

        .. code-block:: python

            from playhouse.signals import connect, post_save

            @post_save(name='project.cache_buster')
            def cache_bust_handler(sender, instance, *args, **kwargs):
                # bust the cache for this instance
                cache.delete(cache_key_for(instance))

.. _pwiz:

pwiz, a model generator
-----------------------

``pwiz`` is a little script that ships with peewee and is capable of
introspecting an existing database and generating model code suitable for
interacting with the underlying data. If you have a database already, pwiz can
give you a nice boost by generating skeleton code with correct column
affinities and foreign keys.

If you install peewee using ``setup.py install``, pwiz will be installed as a
"script" and you can just run:

.. code-block:: console

    python -m pwiz -e postgresql -u postgres my_postgres_db

This will print a bunch of models to standard output. So you can do this:

.. code-block:: console

    python -m pwiz -e postgresql my_postgres_db > mymodels.py
    python # <-- fire up an interactive shell

.. code-block:: pycon

    >>> from mymodels import Blog, Entry, Tag, Whatever
    >>> print [blog.name for blog in Blog.select()]


======    ========================= ============================================
Option    Meaning                   Example
======    ========================= ============================================
-h        show help
-e        database backend          -e mysql
-H        host to connect to        -H remote.db.server
-p        port to connect on        -p 9001
-u        database user             -u postgres
-P        database password         -P secret
-s        postgres schema           -s public
======    ========================= ============================================

The following are valid parameters for the engine:

* sqlite
* mysql
* postgresql

.. _migrate:

Schema Migrations
-----------------

Peewee now supports schema migrations, with well-tested support for Postgresql,
SQLite and MySQL. Unlike other schema migration tools, peewee's migrations do
not handle introspection and database "versioning". Rather, peewee provides a
number of helper functions for generating and running schema-altering
statements. This engine provides the basis on which a more sophisticated tool
could some day be built.

Migrations can be written as simple python scripts and executed from the
command-line. Since the migrations only depend on your applications
:py:class:`Database` object, it should be easy to manage changing your model
definitions and maintaining a set of migration scripts without introducing
dependencies.

Example usage
^^^^^^^^^^^^^

Begin by importing the helpers from the `migrate` module:

.. code-block:: python

    from playhouse.migrate import *

Instantiate a ``migrator``. The :py:class:`SchemaMigrator` class is responsible
for generating schema altering operations, which can then be run sequentially
by the :py:func:`migrate` helper.

.. code-block:: python

    # Postgres example:
    my_db = PostgresqlDatabase(...)
    migrator = PostgresqlMigrator(my_db)

    # SQLite example:
    my_db = SqliteDatabase('my_database.db')
    migrator = SqliteMigrator(my_db)

Use :py:func:`migrate` to execute one or more operations:

.. code-block:: python

    title_field = CharField(default='')
    status_field = IntegerField(null=True)

    migrate(
        migrator.add_column('some_table', 'title', title_field),
        migrator.add_column('some_table', 'status', status_field),
        migrator.drop_column('some_table', 'old_column'),
    )

.. warning::
    Migrations are not run inside a transaction. If you wish the migration to
    run in a transaction you will need to wrap the call to `migrate` in a
    transaction block, e.g.

    .. code-block:: python

        with my_db.transaction():
            migrate(...)

Supported Operations
^^^^^^^^^^^^^^^^^^^^

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


Migrations API
^^^^^^^^^^^^^^

.. py:function:: migrate(*operations)

    Execute one or more schema altering operations.

    Usage:

    .. code-block:: python

        migrate(
            migrator.add_column('some_table', 'new_column', CharField(default='')),
            migrator.create_index('some_table', ('new_column',)),
        )

.. py:class:: SchemaMigrator(database)

    :param database: a :py:class:`Database` instance.

    The :py:class:`SchemaMigrator` is responsible for generating schema-altering
    statements.

    .. py:method:: add_column(table, column_name, field)

        :param str table: Name of the table to add column to.
        :param str column_name: Name of the new column.
        :param Field field: A :py:class:`Field` instance.

        Add a new column to the provided table. The ``field`` provided will be used
        to generate the appropriate column definition.

        .. note:: If the field is not nullable it must specify a default value.

        .. note::
            For non-null fields, the field will initially be added as a null field,
            then an ``UPDATE`` statement will be executed to populate the column
            with the default value. Finally, the column will be marked as not null.

    .. py:method:: drop_column(table, column_name[, cascade=True])

        :param str table: Name of the table to drop column from.
        :param str column_name: Name of the column to drop.
        :param bool cascade: Whether the column should be dropped with `CASCADE`.

    .. py:method:: rename_column(table, old_name, new_name)

        :param str table: Name of the table containing column to rename.
        :param str old_name: Current name of the column.
        :param str new_name: New name for the column.

    .. py:method:: add_not_null(table, column)

        :param str table: Name of table containing column.
        :param str column: Name of the column to make not nullable.

    .. py:method:: drop_not_null(table, column)

        :param str table: Name of table containing column.
        :param str column: Name of the column to make nullable.

    .. py:method:: rename_table(old_name, new_name)

        :param str old_name: Current name of the table.
        :param str new_name: New name for the table.

    .. py:method:: add_index(table, columns[, unique=False])

        :param str table: Name of table on which to create the index.
        :param list columns: List of columns which should be indexed.
        :param bool unique: Whether the new index should specify a unique constraint.

    .. py:method:: drop_index(table, index_name)

        :param str table Name of the table containing the index to be dropped.
        :param str index_name: Name of the index to be dropped.

.. py:class:: PostgresqlMigrator(database)

    Generate migrations for Postgresql databases.

    .. py:method:: set_search_path(schema_name)

        :param str schema_name: Schema to use.

        Set the search path (schema) for the subsequent operations.

.. py:class:: SqliteMigrator(database)

    Generate migrations for SQLite databases.

.. py:class:: MySQLMigrator(database)

    Generate migrations for MySQL databases.


.. _reflection:

Reflection
----------

The reflection module contains helpers for introspecting existing databases.
This module is used internally by several other modules in the playhouse,
including :ref:`dataset` and :ref:`pwiz`.

.. py:class:: Introspector(metadata[, schema=None])

    Metadata can be extracted from a database by instantiating an
    :py:class:`Introspector`. Rather than instantiating this class directly, it
    is recommended to use the factory method
    :py:meth:`~Introspector.from_database`.

    .. py:classmethod:: from_database(database[, schema=None])

        :param database: a :py:class:`Database` instance.
        :param str schema: an optional schema (supported by some databases).

        Creates an :py:class:`Introspector` instance suitable for use with the
        given database.

        Usage:

        .. code-block:: python

            db = SqliteDatabase('my_app.db')
            introspector = Introspector.from_database(db)
            models = introspector.generate_models()

            # User and Tweet (assumed to exist in the database) are
            # peewee Model classes generated from the database schema.
            User = models['user']
            Tweet = models['tweet']

    .. py:method:: generate_models([skip_invalid=False[, table_names=None[, literal_column_names=False[, bare_fields=False]]]])

        :param bool skip_invalid: Skip tables whose names are invalid python
            identifiers.
        :param list table_names: List of table names to generate. If
            unspecified, models are generated for all tables.
        :param bool literal_column_names: Use column-names as-is. By default,
            column names are "python-ized", i.e. mixed-case becomes lower-case.
        :param bare_fields: **SQLite-only**. Do not specify data-types for
            introspected columns.
        :return: A dictionary mapping table-names to model classes.

        Introspect the database, reading in the tables, columns, and foreign
        key constraints, then generate a dictionary mapping each database table
        to a dynamically-generated :py:class:`Model` class.


.. _db_url:

Database URL
------------

This module contains a helper function to generate a database connection from a
URL connection string.

.. py:function:: connect(url, **connect_params)

    Create a :py:class:`Database` instance from the given connection URL.

    Examples:

    * *sqlite:///my_database.db* will create a :py:class:`SqliteDatabase` instance for the file ``my_database.db`` in the current directory.
    * *sqlite:///:memory:* will create an in-memory :py:class:`SqliteDatabase` instance.
    * *postgresql://postgres:my_password@localhost:5432/my_database* will create a :py:class:`PostgresqlDatabase` instance. A username and password are provided, as well as the host and port to connect to.
    * *mysql://user:passwd@ip:port/my_db* will create a :py:class:`MySQLDatabase` instance for the local MySQL database *my_db*.
    * *mysql+pool://user:passwd@ip:port/my_db?max_connections=20&stale_timeout=300* will create a :py:class:`PooledMySQLDatabase` instance for the local MySQL database *my_db* with max_connections set to 20 and a stale_timeout setting of 300 seconds.

    Supported schemes:

    * ``apsw``: :py:class:`APSWDatabase`
    * ``mysql``: :py:class:`MySQLDatabase`
    * ``mysql+pool``: :py:class:`PooledMySQLDatabase`
    * ``postgres``: :py:class:`PostgresqlDatabase`
    * ``postgres+pool``: :py:class:`PooledPostgresqlDatabase`
    * ``postgresext``: :py:class:`PostgresqlExtDatabase`
    * ``postgresext+pool``: :py:class:`PooledPostgresqlExtDatabase`
    * ``sqlite``: :py:class:`SqliteDatabase`
    * ``sqliteext``: :py:class:`SqliteExtDatabase`
    * ``sqlite+pool``: :py:class:`PooledSqliteDatabase`
    * ``sqliteext+pool``: :py:class:`PooledSqliteExtDatabase`

    Usage:

    .. code-block:: python

        import os
        from playhouse.db_url import connect

        # Connect to the database URL defined in the environment, falling
        # back to a local Sqlite database if no database URL is specified.
        db = connect(os.environ.get('DATABASE') or 'sqlite:///default.db')

.. py:function:: parse(url)

    Parse the information in the given URL into a dictionary containing
    ``database``, ``host``, ``port``, ``user`` and/or ``password``. Additional
    connection arguments can be passed in the URL query string.

    If you are using a custom database class, you can use the ``parse()``
    function to extract information from a URL which can then be passed in to
    your database object.

.. py:function:: register_database(db_class, *names)

    :param db_class: A subclass of :py:class:`Database`.
    :param names: A list of names to use as the scheme in the URL, e.g. 'sqlite' or 'firebird'

    Register additional database class under the specified names. This function
    can be used to extend the ``connect()`` function to support additional
    schemes. Suppose you have a custom database class for ``Firebird`` named
    ``FirebirdDatabase``.

    .. code-block:: python

        from playhouse.db_url import connect, register_database

        register_database(FirebirdDatabase, 'firebird')
        db = connect('firebird://my-firebird-db')

.. _pool:

Connection pool
---------------

The ``pool`` module contains a number of :py:class:`Database` classes that
provide connection pooling for PostgreSQL, MySQL and SQLite databases. The pool
works by overriding the methods on the :py:class:`Database` class that open and
close connections to the backend. The pool can specify a timeout after which
connections are recycled, as well as an upper bound on the number of open
connections.

In a multi-threaded application, up to `max_connections` will be opened. Each
thread (or, if using gevent, greenlet) will have it's own connection.

In a single-threaded application, only one connection will be created. It will
be continually recycled until either it exceeds the stale timeout or is closed
explicitly (using `.manual_close()`).

**By default, all your application needs to do is ensure that connections are
closed when you are finished with them, and they will be returned to the
pool**. For web applications, this typically means that at the beginning of a
request, you will open a connection, and when you return a response, you will
close the connection.

Simple Postgres pool example code:

.. code-block:: python

    # Use the special postgresql extensions.
    from playhouse.pool import PooledPostgresqlExtDatabase

    db = PooledPostgresqlExtDatabase(
        'my_app',
        max_connections=32,
        stale_timeout=300,  # 5 minutes.
        user='postgres')

    class BaseModel(Model):
        class Meta:
            database = db

That's it! If you would like finer-grained control over the pool of
connections, check out the :ref:`advanced_connection_management` section.

Pool APIs
^^^^^^^^^

.. py:class:: PooledDatabase(database[, max_connections=20[, stale_timeout=None[, timeout=None[, **kwargs]]]])

    :param str database: The name of the database or database file.
    :param int max_connections: Maximum number of connections. Provide ``None`` for unlimited.
    :param int stale_timeout: Number of seconds to allow connections to be used.
    :param int timeout: Number of seconds block when pool is full. By default peewee does not block when the pool is full but simply throws an exception. To block indefinitely set this value to ``0``.
    :param kwargs: Arbitrary keyword arguments passed to database class.

    Mixin class intended to be used with a subclass of :py:class:`Database`.

    .. note:: Connections will not be closed exactly when they exceed their `stale_timeout`. Instead, stale connections are only closed when a new connection is requested.

    .. note:: If the number of open connections exceeds `max_connections`, a `ValueError` will be raised.

    .. py:method:: _connect(*args, **kwargs)

        Request a connection from the pool. If there are no available connections a new one will be opened.

    .. py:method:: _close(conn[, close_conn=False])

        By default `conn` will not be closed and instead will be returned to the pool of available connections. If `close_conn=True`, then `conn` will be closed and *not* be returned to the pool.

    .. py:method:: manual_close()

        Close the currently-open connection without returning it to the pool.

.. py:class:: PooledPostgresqlDatabase

    Subclass of :py:class:`PostgresqlDatabase` that mixes in the :py:class:`PooledDatabase` helper.

.. py:class:: PooledPostgresqlExtDatabase

    Subclass of :py:class:`PostgresqlExtDatabase` that mixes in the :py:class:`PooledDatabase` helper. The :py:class:`PostgresqlExtDatabase` is a part of the
    :ref:`postgres_ext` module and provides support for many Postgres-specific
    features.

.. py:class:: PooledMySQLDatabase

    Subclass of :py:class:`MySQLDatabase` that mixes in the :py:class:`PooledDatabase` helper.

.. py:class:: PooledSqliteDatabase

    Persistent connections for SQLite apps.

.. py:class:: PooledSqliteExtDatabase

    Persistent connections for SQLite apps, using the :ref:`sqlite_ext` advanced database driver :py:class:`SqliteExtDatabase`.

.. _test_utils:

Test Utils
----------

Contains utilities helpful when testing peewee projects.

.. py:class:: count_queries([only_select=False])

    Context manager that will count the number of queries executed within
    the context.

    :param bool only_select: Only count *SELECT* queries.

    .. code-block:: python

        with count_queries() as counter:
            huey = User.get(User.username == 'huey')
            huey_tweets = [tweet.message for tweet in huey.tweets]

        assert counter.count == 2

    .. py:attribute:: count

        The number of queries executed.

    .. py:method:: get_queries()

        Return a list of 2-tuples consisting of the SQL query and a list of
        parameters.


.. py:function:: assert_query_count(expected[, only_select=False])

    Function or method decorator that will raise an ``AssertionError`` if the
    number of queries executed in the decorated function does not equal the
    expected number.

    .. code-block:: python

        class TestMyApp(unittest.TestCase):
            @assert_query_count(1)
            def test_get_popular_blogs(self):
                popular_blogs = Blog.get_popular()
                self.assertEqual(
                    [blog.title for blog in popular_blogs],
                    ["Peewee's Playhouse!", "All About Huey", "Mickey's Adventures"])

    This function can also be used as a context manager:

    .. code-block:: python

        class TestMyApp(unittest.TestCase):
            def test_expensive_operation(self):
                with assert_query_count(1):
                    perform_expensive_operation()


.. _flask_utils:

Flask Utils
-----------

The ``playhouse.flask_utils`` module contains several helpers for integrating
peewee with the `Flask <http://flask.pocoo.org/>`_ web framework.

Database Wrapper
^^^^^^^^^^^^^^^^

The :py:class:`FlaskDB` class is a wrapper for configuring and referencing a
Peewee database from within a Flask application. Don't let it's name fool you:
it is **not the same thing as a peewee database**. ``FlaskDB`` is designed to
remove the following boilerplate from your flask app:

* Dynamically create a Peewee database instance based on app config data.
* Create a base class from which all your application's models will descend.
* Register hooks at the start and end of a request to handle opening and
  closing a database connection.

Basic usage:

.. code-block:: python

    import datetime
    from flask import Flask
    from peewee import *
    from playhouse.flask_utils import FlaskDB

    DATABASE = 'postgresql://postgres:password@localhost:5432/my_database'

    app = Flask(__name__)
    app.config.from_object(__name__)

    db_wrapper = FlaskDB(app)

    class User(db_wrapper.Model):
        username = CharField(unique=True)

    class Tweet(db_wrapper.Model):
        user = ForeignKeyField(User, backref='tweets')
        content = TextField()
        timestamp = DateTimeField(default=datetime.datetime.now)

The above code example will create and instantiate a peewee
:py:class:`PostgresqlDatabase` specified by the given database URL. Request
hooks will be configured to establish a connection when a request is received,
and automatically close the connection when the response is sent. Lastly, the
:py:class:`FlaskDB` class exposes a :py:attr:`FlaskDB.Model` property which can
be used as a base for your application's models.

Here is how you can access the wrapped Peewee database instance that is
configured for you by the ``FlaskDB`` wrapper:

.. code-block:: python

    # Obtain a reference to the Peewee database instance.
    peewee_db = db_wrapper.database

    @app.route('/transfer-funds/', methods=['POST'])
    def transfer_funds():
        with peewee_db.atomic():
            # ...

        return jsonify({'transfer-id': xid})

.. note:: The actual peewee database can be accessed using the ``FlaskDB.database`` attribute.

Here is another way to configure a Peewee database using ``FlaskDB``:

.. code-block:: python

    app = Flask(__name__)
    db_wrapper = FlaskDB(app, 'sqlite:///my_app.db')

While the above examples show using a database URL, for more advanced usages
you can specify a dictionary of configuration options, or simply pass in a
peewee :py:class:`Database` instance:

.. code-block:: python

    DATABASE = {
        'name': 'my_app_db',
        'engine': 'playhouse.pool.PooledPostgresqlDatabase',
        'user': 'postgres',
        'max_connections': 32,
        'stale_timeout': 600,
    }

    app = Flask(__name__)
    app.config.from_object(__name__)

    wrapper = FlaskDB(app)
    pooled_postgres_db = wrapper.database

Using a peewee :py:class:`Database` object:

.. code-block:: python

    peewee_db = PostgresqlExtDatabase('my_app')
    app = Flask(__name__)
    db_wrapper = FlaskDB(app, peewee_db)


Database with Application Factory
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you prefer to use the `application factory pattern <http://flask.pocoo.org/docs/0.10/patterns/appfactories/>`_,
the :py:class:`FlaskDB` class implements an ``init_app()`` method.

Using as a factory:

.. code-block:: python

    db_wrapper = FlaskDB()

    # Even though the database is not yet initialized, you can still use the
    # `Model` property to create model classes.
    class User(db_wrapper.Model):
        username = CharField(unique=True)


    def create_app():
        app = Flask(__name__)
        app.config['DATABASE'] = 'sqlite:////home/code/apps/my-database.db'
        db_wrapper.init_app(app)
        return app

Query utilities
^^^^^^^^^^^^^^^

The ``flask_utils`` module provides several helpers for managing queries in your web app. Some common patterns include:

.. py:function:: get_object_or_404(query_or_model, *query)

    :param query_or_model: Either a :py:class:`Model` class or a pre-filtered :py:class:`SelectQuery`.
    :param query: An arbitrarily complex peewee expression.

    Retrieve the object matching the given query, or return a 404 not found
    response. A common use-case might be a detail page for a weblog. You want
    to either retrieve the post matching the given URL, or return a 404.

    Example:

    .. code-block:: python

        @app.route('/blog/<slug>/')
        def post_detail(slug):
            public_posts = Post.select().where(Post.published == True)
            post = get_object_or_404(public_posts, (Post.slug == slug))
            return render_template('post_detail.html', post=post)

.. py:function:: object_list(template_name, query[, context_variable='object_list'[, paginate_by=20[, page_var='page'[, check_bounds=True[, **kwargs]]]]])

    :param template_name: The name of the template to render.
    :param query: A :py:class:`SelectQuery` instance to paginate.
    :param context_variable: The context variable name to use for the paginated object list.
    :param paginate_by: Number of objects per-page.
    :param page_var: The name of the ``GET`` argument which contains the page.
    :param check_bounds: Whether to check that the given page is a valid page. If ``check_bounds`` is ``True`` and an invalid page is specified, then a 404 will be returned.
    :param kwargs: Arbitrary key/value pairs to pass into the template context.

    Retrieve a paginated list of objects specified by the given query. The
    paginated object list will be dropped into the context using the given
    ``context_variable``, as well as metadata about the current page and total
    number of pages, and finally any arbitrary context data passed as
    keyword-arguments.

    The page is specified using the ``page`` ``GET`` argument, e.g.
    ``/my-object-list/?page=3`` would return the third page of objects.

    Example:

    .. code-block:: python

        @app.route('/blog/')
        def post_index():
            public_posts = (Post
                            .select()
                            .where(Post.published == True)
                            .order_by(Post.timestamp.desc()))

            return object_list(
                'post_index.html',
                query=public_posts,
                context_variable='post_list',
                paginate_by=10)

    The template will have the following context:

    * ``post_list``, which contains a list of up to 10 posts.
    * ``page``, which contains the current page based on the value of the ``page`` ``GET`` parameter.
    * ``pagination``, a :py:class:`PaginatedQuery` instance.

.. py:class:: PaginatedQuery(query_or_model, paginate_by[, page_var='page'[, check_bounds=False]])

    :param query_or_model: Either a :py:class:`Model` or a :py:class:`SelectQuery` instance containing the collection of records you wish to paginate.
    :param paginate_by: Number of objects per-page.
    :param page_var: The name of the ``GET`` argument which contains the page.
    :param check_bounds: Whether to check that the given page is a valid page. If ``check_bounds`` is ``True`` and an invalid page is specified, then a 404 will be returned.

    Helper class to perform pagination based on ``GET`` arguments.

    .. py:method:: get_page()

        Return the currently selected page, as indicated by the value of the
        ``page_var`` ``GET`` parameter. If no page is explicitly selected, then
        this method will return 1, indicating the first page.

    .. py:method:: get_page_count()

        Return the total number of possible pages.

    .. py:method:: get_object_list()

        Using the value of :py:meth:`~PaginatedQuery.get_page`, return the page
        of objects requested by the user. The return value is a
        :py:class:`SelectQuery` with the appropriate ``LIMIT`` and ``OFFSET``
        clauses.

        If ``check_bounds`` was set to ``True`` and the requested page contains
        no objects, then a 404 will be raised.
