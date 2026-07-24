.. _sqlite:

SQLite
======

The core :class:`SqliteDatabase` handles pragmas, user-defined functions,
WAL mode, full-text search and JSON. Because the full-text search and JSON
fields are specific to SQLite, these features are provided by ``playhouse.sqlite_ext``.

.. contents:: On this page
   :local:
   :depth: 1

Implementations
---------------

:class:`SqliteDatabase`
   Core SQLite implementation. Provides:

   * Pragma support (including WAL-mode)
   * User-defined functions
   * ATTACH / DETACH databases
   * Full-text search
   * JSON

   Full-text search and JSON implementations available in
   ``playhouse.sqlite_ext``.

:class:`~playhouse.cysqlite_ext.CySqliteDatabase` (``playhouse.cysqlite_ext``)
   Extends :class:`SqliteDatabase`, uses `cysqlite <https://cysqlite.readthedocs.io/en/latest/>`__ driver.

   * All above functionality
   * Table-value functions
   * Commit / Rollback / Update / Progress / Trace hooks
   * BLOB I/O
   * Online backups
   * Supports fully self-contained builds.
   * Can be built `with encryption <https://cysqlite.readthedocs.io/en/latest/installation.html#sqlcipher>`__.

:class:`~playhouse.apsw_ext.APSWDatabase` (``playhouse.apsw_ext``)
   Extends :class:`SqliteDatabase`, uses `apsw <https://github.com/rogerbinns/apsw/>`__ driver.

   APSW is a thin C-level driver that exposes the full range of SQLite
   functionality.

:class:`~playhouse.sqlcipher_ext.SqlCipherDatabase` (``playhouse.sqlcipher_ext``)
   Extends :class:`SqliteDatabase`, uses `sqlcipher3 <https://github.com/coleifer/sqlcipher3>`__ driver.

   SQLCipher provides transparent full-database encryption using 256-bit AES,
   ensuring data on-disk is secure.

:class:`~playhouse.sqliteq.SqliteQueueDatabase` (``playhouse.sqliteq``)
   Extends :class:`SqliteDatabase`.

   Provides a SQLite database implementation with a long-lived background
   writer thread. All write operations are managed by a single write
   connection, preventing timeouts and database locking issues. This
   implementation is useful when using Sqlite in multi-threaded environments
   with frequent writes.

.. _sqlite-pragma:

PRAGMA statements
-----------------

SQLite allows run-time configuration through ``PRAGMA`` statements (`SQLite documentation <https://www.sqlite.org/pragma.html>`_).
These statements are typically run when a new database connection is created.

To specify default ``PRAGMA`` statements for connections:

.. code-block:: python

   db = SqliteDatabase('my_app.db', pragmas={
       'journal_mode': 'wal',
       'cache_size': 10000,  # 10000 pages, or ~40MB
       'foreign_keys': 1,  # Enforce foreign-key constraints
   })

PRAGMAs may also be configured dynamically using either the :meth:`~SqliteDatabase.pragma`
method or the special properties exposed on the :class:`SqliteDatabase` object:

.. code-block:: python

   # Set cache size to 64MB for *current connection*.
   db.pragma('cache_size', -64000)

   # Same as above.
   db.cache_size = -64000

   # Read the value of several pragmas:
   print('cache_size:', db.cache_size)
   print('foreign_keys:', db.foreign_keys)
   print('journal_mode:', db.journal_mode)
   print('page_size:', db.page_size)

   # Set foreign_keys pragma on current connection *AND* on all
   # connections opened subsequently.
   db.pragma('foreign_keys', 1, permanent=True)

.. attention::
   Pragmas set using the :meth:`~SqliteDatabase.pragma` method are not
   re-applied when a new connection opens. To configure a pragma to be
   run whenever a new connection is opened, specify ``permanent=True``.

   .. code-block:: python

      db.pragma('foreign_keys', 1, permanent=True)

.. seealso::
   SQLite PRAGMA documentation: https://sqlite.org/pragma.html

.. _sqlite-user-functions:

User-Defined Functions
----------------------

SQLite can be extended with user-defined Python code. The
:class:`SqliteDatabase` class supports a variety of user-defined extensions:

Functions
   User-defined functions accept any number of parameters and return a single
   value.

   * :meth:`SqliteDatabase.register_function`
   * :meth:`SqliteDatabase.func` - decorator.

Aggregates
   Aggregate values across multiple rows and return a single value.

   * :meth:`SqliteDatabase.register_aggregate`
   * :meth:`SqliteDatabase.aggregate` - decorator.

Window Functions
   Aggregates which support operating on sliding windows of data.

   * :meth:`SqliteDatabase.register_window_function`
   * :meth:`SqliteDatabase.window_function` - decorator.

Collations
   Control how values are ordered and sorted.

   * :meth:`SqliteDatabase.register_collation`
   * :meth:`SqliteDatabase.collation` - decorator.

Table Functions
   User-defined tables (requires ``cysqlite``).

   * :meth:`.CySqliteDatabase.register_table_function`
   * :meth:`.CySqliteDatabase.table_function` - decorator.

Shared Libraries
   Load an extension from a shared library.

   * :meth:`SqliteDatabase.load_extension`
   * :meth:`SqliteDatabase.unload_extension`

Function example
^^^^^^^^^^^^^^^^

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

Aggregate example
^^^^^^^^^^^^^^^^^

User-defined aggregates must define two methods:

* ``step(*values)`` - called once for each row being aggregated.
* ``finalize()`` - called only once to produce final aggregate value.

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

Window function example
^^^^^^^^^^^^^^^^^^^^^^^

User-defined window functions are aggregates with two additional methods:

* ``step(*values)`` - called for each row being aggregated.
* ``inverse(*values)`` - "invert" the effect of a call to ``step(*values)``.
* ``value()`` - return the current value of the aggregate.
* ``finalize()`` - return final aggregate value.

.. code-block:: python

   @db.window_function('mysum')
   class MySum(object):
       def __init__(self):
           self._value = 0
       def step(self, value):
           self._value += (value or 0)
       def inverse(self, value):
           self._value -= (value or 0)  # Do opposite of "step()".
       def value(self):
           return self._value
       def finalize(self):
           return self._value

   # e.g., aggregate sum of employee salaries over their department.
   query = (Employee
            .select(
                Employee.department,
                Employee.salary,
                fn.mysum(Employee.salary).over(
                    partition_by=[Employee.department]))
            .order_by(Employee.id))

Collation example
^^^^^^^^^^^^^^^^^

Collations accept two values and provide a value indicating how they should be
ordered (e.g. ``cmp(lhs, rhs)``).

.. code-block:: python

   @db.collation('ireverse')
   def collate_reverse(s1, s2):
       # Case-insensitive reverse.
       s1, s2 = s1.lower(), s2.lower()
       return (s1 < s2) - (s1 > s2)  # Equivalent to -cmp(s1, s2)

   # To use this collation to sort books in reverse order...
   Book.select().order_by(collate_reverse.collation(Book.title))

   # Or...
   Book.select().order_by(Book.title.asc(collation='ireverse'))

Table function example
^^^^^^^^^^^^^^^^^^^^^^

The simplest table function is a plain function or generator. It is called
once per query with the SQL arguments and returns an iterable of row tuples.
Parameters are taken from the function signature. A parameter with a Python
default is optional in SQL.

.. code-block:: python

   from playhouse.cysqlite_ext import CySqliteDatabase

   db = CySqliteDatabase('my_app.db')

   @db.table_function(columns=['value'])
   def series(start, stop, step=1):
       i = start
       while i < stop:
           yield (i,)
           i += step

   cursor = db.execute_sql('SELECT value FROM series(0, 5, 2)')
   print([value for value, in cursor])
   # [0, 2, 4]

   # step falls back to its default of 1.
   cursor = db.execute_sql('SELECT value FROM series(0, 3)')
   print([value for value, in cursor])
   # [0, 1, 2]

For writable tables, ``with_rowid``, or full control over the per-query
lifecycle, subclass ``cysqlite.TableFunction`` (see `cysqlite TableFunction
docs <https://cysqlite.readthedocs.io/en/latest/api.html#tablefunction>`_) and
register it the same way. The equivalent of the above:

.. code-block:: python

   from cysqlite import TableFunction

   @db.table_function('series')
   class Series(TableFunction):
       columns = ['value']
       params = ['start', 'stop', 'step']

       def initialize(self, start=0, stop=None, step=1):
           # Called once per query, with the SQL arguments.
           self.start = self.current = start
           self.stop = stop if stop is not None else float('Inf')
           self.step = step

       def iterate(self, idx):
           # Called for each row. Raise StopIteration when done.
           if ((self.step > 0 and self.current > self.stop) or
               (self.step < 0 and self.current < self.stop)):
               raise StopIteration

           ret, self.current = self.current, self.current + self.step
           return (ret,)

Shared Libraries
^^^^^^^^^^^^^^^^

Example:

   .. code-block:: python

      # Load `closure.so` shared library in the current directory.
      db = SqliteDatabase('my_app.db')
      db.load_extension('closure')

To support shared libraries, your SQLite3 will need to have been compiled with
support for run-time loadable extensions.

.. _sqlite-locking-mode:

Locking Mode for Transactions
-----------------------------

SQLite transactions can be opened in three different modes:

* *Deferred* (**default**) - only acquires lock when a read or write is
  performed. The first read creates a `shared lock <https://sqlite.org/lockingv3.html#locking>`_
  and the first write creates a `reserved lock <https://sqlite.org/lockingv3.html#locking>`_.
  Because the acquisition of the lock is deferred until actually needed, it is
  possible that another thread or process could create a separate transaction
  and write to the database.
* *Immediate* - a `reserved lock <https://sqlite.org/lockingv3.html#locking>`_
  is acquired immediately. In this mode, no other connection may write to the
  database or open an *immediate* or *exclusive* transaction. Other processes
  can continue to read from the database, however.
* *Exclusive* - opens an `exclusive lock <https://sqlite.org/lockingv3.html#locking>`_
  which prevents all (except for read uncommitted) connections from accessing
  the database until the transaction is complete.

Example specifying the locking mode:

.. code-block:: python

    db = SqliteDatabase('app.db')

    with db.atomic('EXCLUSIVE'):
        read()
        write()


    @db.atomic('IMMEDIATE')
    def some_other_function():
        # This function is wrapped in an "IMMEDIATE" transaction.
        do_something_else()

For more information, see the SQLite `locking documentation <https://sqlite.org/lockingv3.html#locking>`_.
To learn more about transactions in Peewee, see the :ref:`transactions`
documentation.

.. danger::
   Do not alter the ``isolation_level`` property of the ``sqlite3.Connection``
   object. Peewee requires the ``sqlite3`` driver be in autocommit-mode, which
   is handled automatically by :class:`SqliteDatabase`.


.. _cysqlite-ext:

CySqlite
--------

.. module:: playhouse.cysqlite_ext

:class:`CySqliteDatabase` uses the `cysqlite <https://cysqlite.readthedocs.io>`_
driver, a high-performance alternative to the standard library ``sqlite3``
module. ``cysqlite`` provides additional features and hooks not available with
in the standard library ``sqlite3`` driver.

Installation:

.. code-block:: shell

   pip install cysqlite

Detailed instructions on building self-contained ``cysqlite`` modules and
encryption support are described on the `cysqlite install guide <https://cysqlite.readthedocs.io/en/latest/installation.html>`_.

Usage:

.. code-block:: python

   from playhouse.cysqlite_ext import CySqliteDatabase

   db = CySqliteDatabase('my_app.db', pragmas={
       'cache_size': -64000,
       'journal_mode': 'wal',
       'foreign_keys': 1,
   })

.. class:: CySqliteDatabase(database, **kwargs)

   :param pragmas: A dict (or list of 2-tuples) of pragma key/value pairs to
       set every time a connection is opened.
   :param timeout: Set the busy-timeout on the SQLite driver (in seconds).
   :param bool rank_functions: Make search result ranking functions available.
       Recommended only when using FTS4.
   :param bool regexp_function: Make the REGEXP function available.

   .. seealso::
      ``CySqliteDatabase`` extends :class:`SqliteDatabase` and inherits all
      methods for declaring user-defined functions, aggregates, window
      functions, collations, pragmas, etc.

   Example:

   .. code-block:: python

       db = CySqliteDatabase('app.db', pragmas={'journal_mode': 'wal'})

   .. method:: table_function(name=None, columns=None, params=None)

      Decorator for registering a table function. Table functions are
      user-defined functions that, rather than returning a single, scalar
      value, can return any number of rows of tabular data. Accepts a plain
      callable or generator, or a ``cysqlite.TableFunction`` subclass for
      writable tables and full control over the per-query lifecycle. For a
      plain callable ``columns`` is required, and the SQL parameters are
      taken from the function signature.

      See `Table function example`_ above, and `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#tablefunction>`__
      for the full ``TableFunction`` API.

   .. method:: register_table_function(klass, name=None, columns=None, params=None)

      Non-decorator form of :meth:`CySqliteDatabase.table_function`.
      Registrations are replayed each time a new connection is opened.

   .. method:: unregister_table_function(name)

      :param name: Name of the user-defined table function.
      :returns: True or False, depending on whether the function was removed.

      Unregister the user-defined table function.

   .. method:: on_commit(fn)

      :param fn: callable or ``None`` to clear the current hook.

      Register a callback to be executed whenever a transaction is committed
      on the current connection. The callback accepts no parameters and the
      return value is ignored.

      If the callback raises a :class:`ValueError`, the transaction is
      aborted and rolled back.

      Example:

      .. code-block:: python

         db = CySqliteDatabase(':memory:')

         @db.on_commit
         def on_commit():
             logger.info('COMMITing changes')

   .. method:: on_rollback(fn)

      :param fn: callable or ``None`` to clear the current hook.

      Register a callback to be executed whenever a transaction is rolled
      back on the current connection. The callback accepts no parameters and
      the return value is ignored.

      Example:

      .. code-block:: python

         @db.on_rollback
         def on_rollback():
             logger.info('Rolling back changes')

   .. method:: on_update(fn)

      :param fn: callable or ``None`` to clear the current hook.

      Register a callback to be executed whenever the database is written to
      (via an *UPDATE*, *INSERT* or *DELETE* query). The callback should
      accept the following parameters:

      * ``query`` - the type of query, either *INSERT*, *UPDATE* or *DELETE*.
      * database name - the default database is named *main*.
      * table name - name of table being modified.
      * rowid - the rowid of the row being modified.

      The callback's return value is ignored.

      Example:

      .. code-block:: python

         db = CySqliteDatabase(':memory:')

         @db.on_update
         def on_update(query_type, db, table, rowid):
             # e.g. INSERT row 3 into table users.
             logger.info('%s row %s into table %s', query_type, rowid, table)

   .. method:: authorizer(fn)

      :param fn: callable or ``None`` to clear the current authorizer.

      Register an authorizer callback. Authorizer callbacks must accept 5
      parameters, which vary depending on the operation being checked.

      * op: operation code, e.g. ``cysqlite.SQLITE_INSERT``.
      * p1: operation-specific value, e.g. table name for ``SQLITE_INSERT``.
      * p2: operation-specific value.
      * p3: database name, e.g. ``"main"``.
      * p4: inner-most trigger or view responsible for the access attempt if
        applicable, else ``None``.

      See `sqlite authorizer documentation <https://www.sqlite.org/c3ref/c_alter_table.html>`_
      for description of authorizer codes and values for parameters p1 and p2.

      The authorizer callback must return one of:

      * ``cysqlite.SQLITE_OK``: allow operation.
      * ``cysqlite.SQLITE_IGNORE``: allow statement compilation but prevent
        the operation from occuring.
      * ``cysqlite.SQLITE_DENY``: prevent statement compilation.

      More details can be found in the `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#Connection.authorizer>`__.

   .. method:: trace(fn, mask=2, expand_sql=True)

      :param fn: callable or ``None`` to clear the current trace hook.
      :param int mask: mask of what types of events to trace. Default value
          corresponds to ``SQLITE_TRACE_PROFILE``.
      :param bool expand_sql: Pass callback the ``sqlite3_expanded_sql()``
          from ``sqlite3_stmt`` (expands bound parameters)

      Register a trace hook (``sqlite3_trace_v2``). Trace callback must
      accept 4 parameters, which vary depending on the operation being
      traced.

      * event: type of event, e.g. ``SQLITE_TRACE_PROFILE``.
      * sid: memory address of statement (only ``SQLITE_TRACE_CLOSE``), else -1.
      * sql: SQL string. If ``expand_sql`` then bound parameters will be
        expanded (for ``SQLITE_TRACE_CLOSE``, ``sql=None``).
      * ns: estimated number of nanoseconds the statement took to run (only
        ``SQLITE_TRACE_PROFILE``), else -1.

      Any return value from callback is ignored.

      More details can be found in the `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#Connection.trace>`__.

   .. method:: slow_query_log(threshold_ms=50, logger=None, level=logging.WARNING, expand_sql=True)

      :param threshold_ms: estimated millisecond threshold to log slow queries.
      :param logger: logging namespace, defaults to ``'peewee.cysqlite_ext'``.
      :param int level: level for slow query log.
      :param bool expand_sql: expand bound parameters in SQL query.

      Register a ``sqlite3_trace_v2`` callback that will log slow queries to
      the given logger. Overrides previously-registered :py:meth:`~CySqliteDatabase.trace`
      callback. Automatically re-registered when new connection is opened.

   .. method:: progress(fn, n=1)

      :param fn: callable or ``None`` to clear the current progress handler.
      :param int n: approximate number of VM instructions to execute between
        calls to the progress handler.

      Register a progress handler (``sqlite3_progress_handler``). Callback
      takes no arguments and returns 0 to allow progress to continue or any
      non-zero value to interrupt progress.

      More details can be found in the `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#Connection.progress>`__.

   .. method:: begin(lock_type='deferred')

      Begin a transaction, optionally specifying the lock type, one of
      ``deferred``, ``immediate`` or ``exclusive``. See
      :ref:`sqlite-locking-mode`.

   .. attribute:: autocommit

      Property which returns a boolean indicating if autocommit is enabled.
      By default, this value will be ``True`` except when inside a
      transaction (or :meth:`~Database.atomic` block).

      Example:

      .. code-block:: pycon

         >>> db = CySqliteDatabase(':memory:')
         >>> db.autocommit
         True
         >>> with db.atomic():
         ...     print(db.autocommit)
         ...
         False
         >>> db.autocommit
         True

   .. method:: backup(destination, pages=None, name=None, progress=None)

      :param CySqliteDatabase destination: Database object to serve as
          destination for the backup.
      :param int pages: Number of pages per iteration. Default value of -1
          indicates all pages should be backed-up in a single step.
      :param str name: Name of source database (may differ if you used ATTACH
          DATABASE to load multiple databases). Defaults to "main".
      :param progress: Progress callback, called with three parameters: the
          number of pages remaining, the total page count, and whether the
          backup is complete.

      Example:

      .. code-block:: python

         master = CySqliteDatabase('master.db')
         replica = CySqliteDatabase('replica.db')

         # Backup the contents of master to replica.
         master.backup(replica)

   .. method:: backup_to_file(filename, pages=None, name=None, progress=None)

      :param filename: Filename to store the database backup.
      :param int pages: Number of pages per iteration. Default value of -1
          indicates all pages should be backed-up in a single step.
      :param str name: Name of source database (may differ if you used ATTACH
          DATABASE to load multiple databases). Defaults to "main".
      :param progress: Progress callback, called with three parameters: the
          number of pages remaining, the total page count, and whether the
          backup is complete.

      Backup the current database to a file. The backed-up data is not a
      database dump, but an actual SQLite database file.

      Example:

      .. code-block:: python

         db = CySqliteDatabase('app.db')

         def nightly_backup():
             filename = 'backup-%s.db' % (datetime.date.today())
             db.backup_to_file(filename)

   .. method:: blob_open(table, column, rowid, read_only=False, dbname=None)

      :param str table: Name of table containing data.
      :param str column: Name of column containing data.
      :param int rowid: ID of row to retrieve.
      :param bool read_only: Open the blob for reading only.
      :param str dbname: Database name (e.g. if multiple databases attached).
      :returns: ``cysqlite.Blob`` instance which provides efficient access to
          the underlying binary data.
      :rtype: cysqlite.Blob

      See `cysqlite documentation <https://cysqlite.readthedocs.io/en/latest/api.html#blob>`_ for
      more details.

      Example:

      .. code-block:: python

          class Image(Model):
              filename = TextField()
              data = BlobField()

          buf_size = 1024 * 1024 * 8  # Allocate 8MB for storing file.
          rowid = Image.insert({
              Image.filename: 'thefile.jpg',
              Image.data: fn.zeroblob(buf_size),
          }).execute()

          # Open the blob, returning a file-like object.
          blob = db.blob_open('image', 'data', rowid)

          # Write some data to the blob.
          blob.write(image_data)
          img_size = blob.tell()

          # Read the data back out of the blob.
          blob.seek(0)
          image_data = blob.read(img_size)

   .. attribute:: server_version

      Version tuple of the SQLite library linked at runtime, e.g.
      ``(3, 54, 0)``.

   .. attribute:: memory_used

      2-tuple of current and highwater memory usage of the SQLite library,
      in bytes. Reads as zeros when the linked SQLite was built without
      memory statistics.

   .. attribute:: cache_used

      Bytes of heap memory used by the current connection's page cache.

   .. attribute:: cache_hit

      Number of page-cache hits on the current connection.

   .. attribute:: cache_miss

      Number of page-cache misses on the current connection.

   .. attribute:: cache_write

      Number of dirty cache entries written to disk on the current
      connection.


.. class:: PooledCySqliteDatabase(database, **kwargs)

   Connection-pooling variant of :class:`CySqliteDatabase`. See
   :ref:`connection-pooling`.

.. _apsw:

APSW
----

.. module:: playhouse.apsw_ext

`APSW <https://rogerbinns.github.io/apsw/>`__ is a thin C wrapper over
SQLite's C API that exposes nearly every SQLite feature including virtual
tables, virtual filesystems, and BLOB I/O.

Installation:

.. code-block:: shell

   pip install apsw

Usage:

.. code-block:: python

   from playhouse.apsw_ext import APSWDatabase

   db = APSWDatabase('my_app.db')

   class BaseModel(Model):
       class Meta:
           database = db

Use the ``Field`` subclasses from ``playhouse.apsw_ext`` rather than those
from ``peewee`` to ensure correct type adaptation. For example, use
``playhouse.apsw_ext.DateTimeField`` instead of ``peewee.DateTimeField``.


.. class:: APSWDatabase(database, **connect_kwargs)

   Subclass of :class:`SqliteDatabase` using the APSW driver.

   :param string database: filename of sqlite database
   :param connect_kwargs: keyword arguments passed to apsw when opening a connection

   .. method:: register_module(mod_name, mod_inst)

      Register a virtual table module globally. See the `APSW virtual table
      documentation <https://rogerbinns.github.io/apsw/vtable.html>`_.

      :param string mod_name: name to use for module
      :param object mod_inst: an object implementing the `Virtual Table <http://rogerbinns.github.io/apsw/vtable.html#vttable-class>`_ interface

   .. method:: unregister_module(mod_name)

      Unregister a previously registered module.


.. _sqlcipher:

SQLCipher
---------

.. module:: playhouse.sqlcipher_ext

`SQLCipher <https://www.zetetic.net/sqlcipher/>`__ is an encrypted wrapper
around SQLite. Peewee exposes it through :class:`SqlCipherDatabase`, which
is API-identical to :class:`SqliteDatabase` except for its constructor.

Installation:

.. code-block:: shell

   pip install sqlcipher3

Usage:

.. code-block:: python

   from playhouse.sqlcipher_ext import SqlCipherDatabase

   db = SqlCipherDatabase(
       'app.db',
       passphrase=os.environ['PASSPHRASE'],
       pragmas={'cache_size': -64000})

Example usage with deferred initialization and passphrase prompt:

.. code-block:: python

   db = SqlCipherDatabase(None)

   class BaseModel(Model):
       class Meta:
           database = db

   class Secret(BaseModel):
       value = TextField()

   # Prompt the user and initialize the database with their passphrase.
   while True:
       db.init('my_app.db', passphrase=input('Passphrase: '))
       try:
           db.get_tables()  # Will raise if passphrase is wrong.
           break
       except DatabaseError as exc:
           print('Wrong passphrase.')
           db.init(None)

Pragma configuration (e.g. increasing PBKDF2 iterations):

.. code-block:: python

   db = SqlCipherDatabase('my_app.db',
                          passphrase='s3cr3t',
                          pragmas={'kdf_iter': 1_000_000})

SQLCipher can be configured using a number of extension PRAGMAs. The list
of PRAGMAs and their descriptions can be found in the `SQLCipher documentation <https://www.zetetic.net/sqlcipher/sqlcipher-api/>`__.

.. class:: SqlCipherDatabase(database, passphrase, **kwargs)

   :param str database: Path to the encrypted database file.
   :param str passphrase: Encryption passphrase, 8 characters minimum.
       Enforce stronger requirements in your application.

   If the database file does not exist, it is created and encrypted with a
   key derived from ``passphrase``. If it does exist, ``passphrase`` must
   match the one used when the file was created.

   If the passphrase is incorrect, an error will be raised when first
   attempting to access the database (typically ``DatabaseError: file is not a
   database``).

   .. method:: rekey(passphrase)

      Change the encryption passphrase for the open database.

.. _sqliteq:

SqliteQueueDatabase
-------------------

.. module:: playhouse.sqliteq

:class:`SqliteQueueDatabase` serializes all write queries through a
single long-lived connection on a dedicated background thread. This allows
multiple application threads to write to a SQLite database concurrently
without conflict or timeout errors.

``SqliteQueueDatabase`` can be used as a drop-in replacement for the regular
:class:`SqliteDatabase` if you want simple **read and write** access to a
SQLite database from multiple threads, and do not need transactions.

.. code-block:: python

   from playhouse.sqliteq import SqliteQueueDatabase

   db = SqliteQueueDatabase(
       'my_app.db',
       use_gevent=False,    # Use stdlib threading (default).
       autostart=True,      # Start the writer thread immediately.
       queue_max_size=64,   # Max pending writes before blocking.
       results_timeout=5.0, # Seconds to wait for a write to complete.
       pragmas={'journal_mode': 'wal'})

If you set ``autostart=False``, start the writer thread explicitly:

.. code-block:: python

   db.start()

Stop the writer thread on application shutdown (waits for pending writes):

.. code-block:: python

   import atexit

   @atexit.register
   def _stop():
       db.stop()

Read queries work as normal. Open and close the connection per-request as you
would with any other database. Only writes are funneled through the queue.

**Transactions are not supported.** Because writes from different threads
are interleaved, there is no way to guarantee that the statements in a
transaction from one thread execute atomically without statements from
another thread appearing between them. The ``atomic()`` and
``transaction()`` methods raise a ``ValueError`` if called.

To write directly, bypassing the queue (for example, a bulk import through
a separate connection), use :meth:`~SqliteQueueDatabase.pause` and
:meth:`~SqliteQueueDatabase.unpause`. While paused the writer thread is
disconnected, and writes submitted through the queue raise ``WriterPaused``.

.. class:: SqliteQueueDatabase(database, use_gevent=False, autostart=True, queue_max_size=None, results_timeout=None, **kwargs)

   :param str database: database filename.
   :param bool use_gevent: use gevent instead of ``threading``.
   :param bool autostart: automatically start writer background thread.
   :param int queue_max_size: maximum size of pending writes queue.
   :param float results_timeout: timeout for waiting for query results from
       write thread (seconds).

   .. method:: start()

      Start the background writer thread.

   .. method:: stop()

      Signal the writer thread to stop. Blocks until all pending writes
      are flushed.

   .. method:: is_stopped()

      Return ``True`` if the writer thread is not running.

   .. method:: pause()

      Block until the writer thread finishes its current work, then
      disconnect it so another connection may write to the database
      directly. While paused, writes submitted through the queue raise
      ``WriterPaused``. Must be followed by a call to
      :meth:`~SqliteQueueDatabase.unpause`.

   .. method:: unpause()

      Resume the writer thread and reconnect the queue.


.. _sqlite-fields:

SQLite-Specific Fields
----------------------

.. module:: playhouse.sqlite_ext

These field classes live in ``playhouse.sqlite_ext`` and can be used with:

* :class:`SqliteDatabase`
* :class:`.CySqliteDatabase`
* :class:`.APSWDatabase`
* :class:`.SqlCipherDatabase`
* :class:`.SqliteQueueDatabase`

.. class:: RowIDField()

   Primary-key field mapped to SQLite's implicit ``rowid`` column.

   For more information, see the SQLite documentation on `rowid tables <https://www.sqlite.org/rowidtable.html>`_.

   .. code-block:: python

      class Note(Model):
          rowid = RowIDField()  # Implied primary_key=True.
          content = TextField()
          timestamp = TimestampField()

   The field must be named ``rowid``. Any other name raises ``ValueError``.

.. class:: AutoIncrementField()

   Integer primary key that uses SQLite's ``AUTOINCREMENT`` keyword,
   guaranteeing the primary key is always strictly increasing even after
   deletions. Has a small performance cost versus the default
   :class:`PrimaryKeyField` or :class:`RowIDField`.

   See the `SQLite AUTOINCREMENT documentation <https://sqlite.org/autoinc.html>`_ for details.

.. class:: ISODateTimeField()

   Subclass of :class:`DateTimeField` that preserves UTC offset
   information for timezone-aware datetimes when storing to SQLite's
   text-based datetime representation.

.. class:: TDecimalField(max_digits=10, decimal_places=5, auto_round=False, rounding=None, *args, **kwargs)

   Subclass of :class:`DecimalField` that stores decimal values in a
   ``TEXT`` column to avoid any potential loss of precision that may occur when
   storing in a ``REAL`` (double-precision floating point) column. SQLite does
   not have a true numeric type, so this field ensures no precision is lost
   when using Decimals.

.. _sqlite-json:

SQLite JSON
-----------

:class:`~playhouse.sqlite_ext.JSONField` enables storing and querying JSON data
in SQLite using the `SQLite json functions <https://sqlite.org/json1.html>`_.

.. warning::
   This field is deprecated. New code should use the cross-backend :ref:`core JSONField <json-field>`.

.. class:: JSONField(json_dumps=None, json_loads=None, **kwargs)

   :param json_dumps: Custom JSON serializer. Defaults to ``json.dumps``.
   :param json_loads: Custom JSON deserializer. Defaults to ``json.loads``.

   Stores and retrieves JSON data transparently and provides efficient
   implementations for in-place modification and querying. Data is
   automatically serialized on write, deserialized on read.

   Example model:

   .. code-block:: python

      from peewee import *
      from playhouse.sqlite_ext import JSONField

      db = SqliteDatabase(':memory:')

      class Config(db.Model):
          data = JSONField()

      Config.create_table()

      # Create two rows.
      Config.create(data={'timeout': 30, 'retry': {'max': 5}})
      Config.create(data={'timeout': 10, 'retry': {'max': 10}})

   To access or modify specific object keys or array indexes in a JSON
   structure, you can treat the :class:`JSONField` as if it were a
   dictionary/list:

   .. code-block:: python

      # Select or order by a JSON value:
      query = (Config
               .select(Config, Config.data['timeout'].alias('timeout'))
               .order_by(Config.data['timeout'].desc()))

      # Aggregate on nested value:
      avg = (Config
             .select(fn.SUM(Config.data['timeout']) / fn.COUNT(Config.id))
             .scalar())

      # Filter by nested value:
      Config.select().where(Config.data['retry']['max'] < 8)

   Data can be atomically updated, written and removed in-place:

   .. code-block:: python

      # In-place update (preserves other keys):
      (Config
       .update(data=Config.data.update({'timeout': 60}))
       .where(Config.data['timeout'] >= 30)
       .execute())

      # Set a specific path:
      (Config
       .update(data=Config.data['timeout'].set(120))
       .where(Config.data['retry']['max'] == 5)
       .execute())

      # Update a specific path with an object. Existing field ("max") will be
      # preserved in this example.
      (Config
       .update(data=Config.data['retry'].update({'backoff': 1}))
       .execute())

      # To overwrite a specific path with an object, use set():
      (Config
       .update(data=Config.data['retry'].set({'allowed': 10}))
       .execute())

      # Remove a key atomically:
      (Config
       .update(data=Config.data.update({'retry': None}))
       .where(Config.id == 1)
       .execute())

      # Another way to remove atomically:
      (Config
       .update(data=Config.data['retry'].remove())
       .where(Config.id == 2)
       .execute())

   Helpers for other JSON scenarios:

   .. code-block:: python

      # Query JSON types:
      query = (Config
               .select(Config.data.json_type(), Config.data['timeout'].json_type())
               .tuples())
      # [('object', 'integer'), ('object', 'integer')]

      # Query length of an array:
      cfg1 = Config.create(data={'statuses': [1, 99, 1, 1]})
      cfg2 = Config.create(data={'statuses': [1, 1]})

      query = (Config
               .select(
                   Config.data['statuses'],
                   Config.data['statuses'].length())
               .where(Config.id.in_([cfg1.id, cfg2.id]))
               .tuples())

      # [([1, 99, 1, 1], 4), ([1, 1], 2)]

   Let's add a nested value and then see how to iterate through its contents
   recursively using the :meth:`~JSONField.tree` method:

   .. code-block:: python

      cfg = Config.create(data={'x1': {'y1': 'z1', 'y2': 'z2'}, 'x2': [1, 2]})

      tree = Config.data.tree().alias('tree')
      query = (Config
               .select(tree.c.fullkey, tree.c.value)
               .from_(Config, tree)
               .where(Config.id == cfg.id))

      for row in query.tuples():
          print(row)

      ('$', '{"x1":{"y1":"z1","y2":"z2"},"x2":[1,2]}')
      ('$.x1', '{"y1":"z1","y2":"z2"}')
      ('$.x1.y1', 'z1')
      ('$.x1.y2', 'z2')
      ('$.x2', '[1,2]')
      ('$.x2[0]', 1)
      ('$.x2[1]', 2)

   For more on :meth:`~JSONField.tree` and :meth:`~JSONField.children`, see
   the `json1 extension documentation <http://sqlite.org/json1.html#jtree>`_.

   .. method:: __getitem__(item)

      :param item: Access a specific key or array index in the JSON data.
      :return: a special object exposing access to the JSON data.
      :rtype: JSONPath

      Access a specific key or array index in the JSON data. Returns a
      :class:`JSONPath` object, which exposes methods for reading or
      modifying a particular part of a JSON object.

      Example:

      .. code-block:: python

         # If metadata contains {"tags": ["list", "of", "tags"]}, we can
         # extract the first tag in this way:
         Post.select(Post, Post.metadata['tags'][0].alias('first_tag'))

      For more examples see the :class:`JSONPath` API documentation.

   .. method:: extract(*paths)

      :param paths: One or more JSON paths to extract.

      Extract one or more JSON path values. Returns a list when multiple
      paths are given.

   .. method:: extract_json(path)

      :param str path: JSON path

      Extract the value at the specified path as a JSON data-type. This
      corresponds to the ``->`` operator added in Sqlite 3.38.

   .. method:: extract_text(path)

      :param str path: JSON path

      Extract the value at the specified path as a SQL data-type. This
      corresponds to the ``->>`` operator added in Sqlite 3.38.

   .. method:: set(value, as_json=None)

      :param value: a scalar value, list, or dictionary.
      :param bool as_json: force the value to be treated as JSON, in which
          case it will be serialized as JSON in Python beforehand. By
          default, lists and dictionaries are treated as JSON to be
          serialized, while strings and integers are passed as-is.

      Set the value stored in a :class:`JSONField`.

      Uses the `json_set() <http://sqlite.org/json1.html#jset>`_ function
      from the json1 extension.

   .. method:: replace(value, as_json=None)

      :param value: a scalar value, list, or dictionary.
      :param bool as_json: force the value to be treated as JSON, in which
          case it will be serialized as JSON in Python beforehand. By
          default, lists and dictionaries are treated as JSON to be
          serialized, while strings and integers are passed as-is.

      Replace the existing value stored in a :class:`JSONField`. Will not
      create if does not exist.

      Uses the `json_replace() <http://sqlite.org/json1.html#jset>`_ function
      from the json1 extension.

   .. method:: insert(value, as_json=None)

      :param value: a scalar value, list, or dictionary.
      :param bool as_json: force the value to be treated as JSON, in which
          case it will be serialized as JSON in Python beforehand. By
          default, lists and dictionaries are treated as JSON to be
          serialized, while strings and integers are passed as-is.

      Insert value into :class:`JSONField`. Will not overwrite existing.

      Uses the `json_insert() <http://sqlite.org/json1.html#jset>`_ function
      from the json1 extension.

   .. method:: append(value, as_json=None)

      :param value: a scalar value, list, or dictionary.
      :param bool as_json: force the value to be treated as JSON, in which
          case it will be serialized as JSON in Python beforehand. By
          default, lists and dictionaries are treated as JSON to be
          serialized, while strings and integers are passed as-is.

      Append to the array stored in a :class:`JSONField`.

      Uses the `json_set() <http://sqlite.org/json1.html#jset>`_ function
      from the json1 extension.

   .. method:: update(data)

      :param data: a scalar value, list or dictionary to merge with the data
          currently stored in a :class:`JSONField`. To remove a particular
          key, set that key to ``None`` in the updated data.

      Merge new data into the JSON value using the RFC-7396 MergePatch
      algorithm to apply a patch (``data`` parameter) against the column
      data. MergePatch can add, modify, or delete elements of a JSON object,
      which means :meth:`~JSONField.update` is a generalized replacement
      for both :meth:`~JSONField.set` and :meth:`~JSONField.remove`.
      MergePatch treats JSON array objects as atomic, so ``update()`` cannot
      append to an array, nor modify individual elements of an array.

      For more information as well as examples, see the SQLite `json_patch() <http://sqlite.org/json1.html#jpatch>`_
      function documentation.

   .. method:: remove()

      Remove the data stored in the :class:`JSONField`.

      Uses the `json_remove <https://www.sqlite.org/json1.html#jrm>`_ function
      from the json1 extension.

   .. method:: json_type()

      Return a string identifying the type of value stored in the column.

      The type returned will be one of:

      * object
      * array
      * integer
      * real
      * true
      * false
      * text
      * null  <-- the string "null" means an actual NULL value
      * NULL  <-- an actual NULL value means the path was not found

      Uses the `json_type <https://www.sqlite.org/json1.html#jtype>`_
      function from the json1 extension.

   .. method:: length()

      Return the length of the array stored in the column.

      Uses the `json_array_length <https://www.sqlite.org/json1.html#jarraylen>`_
      function from the json1 extension.

   .. method:: children()

      The ``children`` function corresponds to ``json_each``, a table-valued
      function that walks the JSON value provided and returns the immediate
      children of the top-level array or object. If a path is specified, then
      that path is treated as the top-most element.

      The rows returned by calls to ``children()`` have the following
      attributes:

      * ``key``: the key of the current element relative to its parent.
      * ``value``: the value of the current element.
      * ``type``: one of the data-types (see :meth:`~JSONField.json_type`).
      * ``atom``: the scalar value for primitive types, ``NULL`` for arrays and objects.
      * ``id``: a unique ID referencing the current node in the tree.
      * ``parent``: the ID of the containing node.
      * ``fullkey``: the full path describing the current element.
      * ``path``: the path to the container of the current row.

      Internally this method uses the `json_each <https://www.sqlite.org/json1.html#jeach>`_
      (documentation link) function from the json1 extension.

      Example usage (compare to :meth:`~JSONField.tree` method):

      .. code-block:: python

          class KeyData(Model):
              key = TextField()
              data = JSONField()

          KeyData.create(key='a', data={'k1': 'v1', 'x1': {'y1': 'z1'}})
          KeyData.create(key='b', data={'x1': {'y1': 'z1', 'y2': 'z2'}})

          # We will query the KeyData model for the key and all the
          # top-level keys and values in its data field.
          kd = KeyData.data.children().alias('children')
          query = (KeyData
                   .select(KeyData.key, kd.c.key, kd.c.value, kd.c.fullkey)
                   .from_(KeyData, kd)
                   .order_by(kd.c.key)
                   .tuples())
          print(query[:])

          # PRINTS:
          [('a', 'k1', 'v1',                    '$.k1'),
           ('a', 'x1', '{"y1":"z1"}',           '$.x1'),
           ('b', 'x1', '{"y1":"z1","y2":"z2"}', '$.x1')]

   .. method:: tree()

      The ``tree`` function corresponds to ``json_tree``, a table-valued
      function that recursively walks the JSON value provided and returns
      information about the keys at each level. If a path is specified, then
      that path is treated as the top-most element.

      The rows returned by calls to ``tree()`` have the same attributes as
      rows returned by calls to :meth:`~JSONField.children`:

      * ``key``: the key of the current element relative to its parent.
      * ``value``: the value of the current element.
      * ``type``: one of the data-types (see :meth:`~JSONField.json_type`).
      * ``atom``: the scalar value for primitive types, ``NULL`` for arrays and objects.
      * ``id``: a unique ID referencing the current node in the tree.
      * ``parent``: the ID of the containing node.
      * ``fullkey``: the full path describing the current element.
      * ``path``: the path to the container of the current row.

      Internally this method uses the `json_tree <https://www.sqlite.org/json1.html#jtree>`_
      (documentation link) function from the json1 extension.

      Example usage:

      .. code-block:: python

          class KeyData(Model):
              key = TextField()
              data = JSONField()

          KeyData.create(key='a', data={'k1': 'v1', 'x1': {'y1': 'z1'}})
          KeyData.create(key='b', data={'x1': {'y1': 'z1', 'y2': 'z2'}})

          # We will query the KeyData model for the key and all the
          # keys and values in its data field, recursively.
          kd = KeyData.data.tree().alias('tree')
          query = (KeyData
                   .select(KeyData.key, kd.c.key, kd.c.value, kd.c.fullkey)
                   .from_(KeyData, kd)
                   .order_by(kd.c.key)
                   .tuples())
          print(query[:])

          # PRINTS:
          [('a',  None,  '{"k1":"v1","x1":{"y1":"z1"}}', '$'),
           ('b',  None,  '{"x1":{"y1":"z1","y2":"z2"}}', '$'),
           ('a',  'k1',  'v1',                           '$.k1'),
           ('a',  'x1',  '{"y1":"z1"}',                  '$.x1'),
           ('b',  'x1',  '{"y1":"z1","y2":"z2"}',        '$.x1'),
           ('a',  'y1',  'z1',                           '$.x1.y1'),
           ('b',  'y1',  'z1',                           '$.x1.y1'),
           ('b',  'y2',  'z2',                           '$.x1.y2')]


.. class:: JSONPath(field, path=None)

   :param JSONField field: the field object we intend to access.
   :param tuple path: Components comprising the JSON path.

   A Pythonic way of representing JSON paths for use with
   :class:`JSONField`. Implements the same methods as :class:`JSONField` but
   designed for operating on nested items, e.g.:

   .. code-block:: python

      Config.create(data={'timeout': 30, 'retries': {'max': 5}})

      # Both Config.data['timeout'] and Config.data['retries']['max']
      # are instances of JSONPath:
      query = (Config
               .select(Config.data['timeout'])
               .where(Config.data['retries']['max'] < 10))

.. class:: JSONBField(json_dumps=None, json_loads=None, **kwargs)

   Extends :class:`JSONField` and stores data in the binary ``jsonb`` format
   (SQLite 3.45.0+). When reading raw column values the data is in its
   encoded binary form use the :meth:`~JSONBField.json` method to decode:

   .. code-block:: python

      # Raw read returns binary:
      kv = KV.get(KV.key == 'a')
      kv.value   # b"l'k1'v1"

      # Use .json() to get a Python object:
      kv = KV.select(KV.value.json()).get()
      kv.value   # {'k1': 'v1'}

   .. method:: json()

      Indicate the JSONB field-data should be deserialized and returned as
      JSON (as opposed to the SQLite binary format).


.. _sqlite-fts:

Full-text search
-----------------

SQLite can maintain a full-text index over one or more columns of text, and
query it using the ``MATCH`` operator. Peewee exposes an index as a
:class:`Model`, where each column is a :class:`SearchField`.

:ref:`FTS5 <sqlite-fts5>` should be used wherever possible. Legacy
:ref:`FTS3 and FTS4 <sqlite-fts4>` support is available for older databases.

Using a search index has three parts:

1. Define an index model with one or more :class:`SearchField` columns.
2. Write to the index whenever the source data changes.
3. Query the index, joining back to the source rows using the ``rowid``.

.. _sqlite-fts5:

FTS5
^^^^

:class:`FTS5Model` stores data in a full-text search index using SQLite
`FTS5 <https://www.sqlite.org/fts5.html>`_ (SQLite 3.9.0+) and provides
built-in BM25 result ranking.

``FTS5Model`` caveats:

* Only ``MATCH`` and lookups on the ``rowid`` column can be performed
  efficiently with FTS tables. All other queries require a full table scan.
* Constraints, foreign-keys, and indexes are not supported.
* The primary key is the implicit ``rowid``, which may be declared explicitly
  using :class:`RowIDField`.
* Besides the implicit ``rowid``, all columns **must** be instances of
  :class:`SearchField`.

Because there are no secondary indexes, it usually makes sense to treat the
``rowid`` as a foreign-key to a row in an ordinary table, and to store the
canonical data there.

Defining an index
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from peewee import *
   from playhouse.sqlite_ext import FTS5Model, SearchField, RowIDField

   db = SqliteDatabase('app.db')

   class Document(Model):
       # Canonical source of data, stored in an ordinary table.
       author = TextField()
       title = TextField()
       content = TextField()
       timestamp = DateTimeField()

       class Meta:
           database = db

   class DocumentIndex(FTS5Model):
       rowid = RowIDField()  # If not provided will be added implicitly.
       title = SearchField()
       content = SearchField()
       author = SearchField(unindexed=True)  # Stored but not searchable.

       class Meta:
           database = db
           # Use the porter stemming algorithm and unicode tokenizers, and
           # optimize prefix matches of 3 or 4 characters (e.g. typeahead).
           options = {'tokenize': 'porter unicode61', 'prefix': [3, 4]}

Columns declared ``unindexed=True`` are stored and returned by ``SELECT``, but
are not searchable. They are useful for metadata you want alongside search
results.

``Meta.options`` declares how the indexed text is stored via the ``content``
key. The choice determines what can be read back out of the index and how it is
kept up to date:

* **Default** (no ``content`` option): the index keeps its own copy of the
  text, and is read and written like any other table.
* :ref:`External content <sqlite-fts-external-content>` (``content=Model``):
  only the search structures are stored. The searchable text itself is read
  from the content table on demand, so ``SELECT`` and the highlighting
  functions still work. In exchange, every change to the content table must be
  mirrored into the index, normally with triggers.
* :ref:`Contentless <sqlite-fts5-contentless>` (``content=''``): searchable
  text is indexed and discarded. A search returns matching ``rowid``\s, but no
  column can be read back, and rows can only be inserted, never changed or
  removed (two newer options relax this).

Prefer the default, which the rest of this section assumes. Choose external
content when storing a second copy of the text would be prohibitively
expensive, and choose contentless when the text never needs to be read back
through the index.

Writing to the index
~~~~~~~~~~~~~~~~~~~~

With the default storage mode the index is an ordinary table as far as writes
are concerned. Set the ``rowid`` to the id of the source row so results can be
joined back to it:

.. code-block:: python

   DocumentIndex.create(
       rowid=document.id,
       title=document.title,
       content=document.content,
       author=document.author)

   # Replace acts as an upsert, for re-indexing a row that may or may not
   # already be present:
   (DocumentIndex
    .replace(rowid=document.id,
             title=document.title,
             content=document.content,
             author=document.author)
    .execute())

Searching
~~~~~~~~~

Three methods deal with the search string:

* :meth:`~FTS5Model.match` builds a ``MATCH`` expression from a string of FTS5
  query syntax, passed through unchanged.
* :meth:`~FTS5Model.search` matches the same way, after scrubbing most syntax
  characters from the string, and orders the results by relevance.
* :meth:`~FTS5Model.web_query` translates "web search" style queries into FTS5
  syntax, **always** producing a valid query for use with :meth:`~FTS5Model.match`
  and :meth:`~FTS5Model.search`.

FTS5 query syntax is unforgiving, and most punctuation means something in
it, so text typed by a user will frequently fail to parse. Compare the same
strings passed through unchanged, scrubbed, and translated:

=========================  =========================================  =============================  ============================
Input                      :meth:`~FTS5Model.match`                   :meth:`~FTS5Model.search`      :meth:`~FTS5Model.web_query`
=========================  =========================================  =============================  ============================
``python sqlite``          both terms                                 both terms                     both terms
``"sqlite fts5"``          the phrase                                 the phrase                     the phrase
``title: python``          the term, in ``title``                     the term, in ``title``         the term, in ``title``
``python OR sqlite``       either term                                either term                    either term
``covid-19``               ``OperationalError: no such column: 19``   the phrase "covid 19"          the term "covid-19"
``o'brien``                ``OperationalError: syntax error``         the phrase "o brien"           the term "o'brien"
``python -sqlite``         ``OperationalError: no such column``       both terms, exclusion lost     "python", excluding "sqlite"
``python AND NOT sqlite``  ``OperationalError: syntax error``         ``OperationalError``           "python", excluding "sqlite"
``(python OR``             ``OperationalError: syntax error``         ``OperationalError``           "python"
(empty)                    ``OperationalError: syntax error``         ``OperationalError``           matches nothing
=========================  =========================================  =============================  ============================

A search box should pass the user's text through :meth:`~FTS5Model.web_query`.
This example fetches documents matching a user search query ``phrase``:

.. code-block:: python

   def search(phrase):
       return (Document
               .select(Document, DocumentIndex.rank().alias('score'))
               .join(DocumentIndex, on=(Document.id == DocumentIndex.rowid))
               .where(DocumentIndex.match(DocumentIndex.web_query(phrase)))
               .order_by(DocumentIndex.rank()))

Use :meth:`~FTS5Model.match` directly when the query is trusted to be a valid
FTS5 query.

.. code-block:: python

   # Search a single column.
   query = DocumentIndex.select().where(DocumentIndex.title.match('python'))

   # Terms within 5 tokens of each other.
   query = DocumentIndex.select().where(
       DocumentIndex.match('NEAR(python sqlite, 5)'))

Ranking and highlighting
~~~~~~~~~~~~~~~~~~~~~~~~

FTS5 ranks matches using BM25, exposed as :meth:`~FTS5Model.rank`. Lower
scores are better, so results sort ascending. :meth:`~FTS5Model.search`
applies the ordering for you, and can return the score and weight columns
individually:

.. code-block:: python

   # Ordered by relevance, title matches weighted twice as heavily.
   results = DocumentIndex.search(
       DocumentIndex.web_query('cysqlite OR (peewee AND sqlite)'),
       weights={'title': 2.0, 'content': 1.0},
       with_score=True,
       score_alias='relevance')

   for r in results:
       print(r.title, r.relevance)

:meth:`~SearchField.highlight` and :meth:`~SearchField.snippet` return the
matched text with the matching terms wrapped in the delimiters you provide,
the latter returning only an excerpt:

.. code-block:: python

   query = (DocumentIndex
            .search(DocumentIndex.web_query('python'))
            .select(DocumentIndex.title.highlight('[', ']').alias('hi'),
                    DocumentIndex.content.snippet('[', ']').alias('snip')))

   for r in query:
       print(r.hi)    # e.g. "Learn [python] the hard way"
       print(r.snip)  # e.g. "...chapter on [python] and sqlite..."

Because both functions rely on reading the stored text, they will return
``NULL`` on contentless FTS tables.

.. _sqlite-fts-external-content:

External content
~~~~~~~~~~~~~~~~

If the text being indexed already lives in another table, the ``content``
option tells SQLite to read it from there instead of storing a second copy.

The ``content`` option accepts a :class:`Model` class or a table-name string.
``content_rowid`` names the column holding the source table's primary key:

.. code-block:: python
   :emphasize-lines: 4, 10, 14

   class Blog(Model):
       title = TextField()
       pub_date = DateTimeField(default=datetime.datetime.now)
       content = TextField()  # We want to search this.

       class Meta:
           database = db

   class BlogIndex(FTS5Model):
       content = SearchField()  # Must match name of column(s) in source model.

       class Meta:
           database = db
           options = {'content': Blog, 'content_rowid': Blog.id}

   db.create_tables([Blog, BlogIndex])

   # Populate the search index from the content table.
   BlogIndex.rebuild()

SQLite maps the content table into the FTS table **by column name**: every
column declared on the index must exist in the content table, though the
order does not matter. The mapping is not checked when the table is created,
so a missing column surfaces later as a ``no such column`` error when the
index is rebuilt or queried. When the names do not line up, either declare the
search field with a matching ``column_name``, or point ``content`` at a view
that renames the columns:

.. code-block:: python

   class DocumentIndex(FTS5Model):
       # Model attribute "body", mapped to Document's "content" column.
       body = SearchField(column_name='content')

       class Meta:
           database = db
           options = {'content': Document, 'content_rowid': Document.id}

SQLite does not keep the index in sync for you, and writing the index has a
twist: to remove or change a row, the index needs the values that were
originally indexed, since it stores no text of its own to look them up in.
They are supplied with the special "delete" command, an ``INSERT`` naming
the table itself. Removing a row is one such ``INSERT``. Changing a row is a
removal followed by a plain ``INSERT`` of the new values:

.. code-block:: sql

   -- Remove one row, passing the values exactly as they were indexed.
   INSERT INTO blogindex(blogindex, rowid, content) VALUES ('delete', ?, ?);

In peewee the command is :meth:`~FTS5Model.delete_command`:

.. code-block:: python

   BlogIndex.delete_command(blog.id, content=old_content)

Ordinary ``UPDATE`` and ``DELETE`` statements are also accepted, but they
work by reading the old values out of the content table at that moment: once
the content row has been changed or removed they silently corrupt the index,
as do wrong values passed to "delete".

Keep the two in sync by re-indexing explicitly with :meth:`~FTS5Model.rebuild`,
issuing the statements before writes in application code, or installing triggers
on the content table, which perform them at exactly the right time:

.. code-block:: sql

   CREATE TRIGGER blog_ai AFTER INSERT ON blog BEGIN
     INSERT INTO blogindex(rowid, content) VALUES (new.id, new.content);
   END;
   CREATE TRIGGER blog_ad AFTER DELETE ON blog BEGIN
     INSERT INTO blogindex(blogindex, rowid, content)
       VALUES('delete', old.id, old.content);
   END;
   CREATE TRIGGER blog_au AFTER UPDATE ON blog BEGIN
     INSERT INTO blogindex(blogindex, rowid, content)
       VALUES('delete', old.id, old.content);
     INSERT INTO blogindex(rowid, content) VALUES (new.id, new.content);
   END;

.. warning::
   With SQLite's default ``recursive_triggers=off``, ``INSERT OR REPLACE``
   will not fire the delete trigger, which leaves stale rows in the index. If
   the content table is written using :meth:`Model.replace`,
   :meth:`Model.replace_many` or ``on_conflict('replace')``, enable the pragma
   on the database: ``SqliteDatabase('app.db', pragmas={'recursive_triggers':
   1})``.

To check whether an index has drifted out of sync with its content table, use
:meth:`~FTS5Model.integrity_check` with ``rank=1``. The default ``rank=0``
only verifies the index's internal structure and will not detect the drift.

.. _sqlite-fts5-contentless:

Contentless tables
~~~~~~~~~~~~~~~~~~

Specifying the empty string for ``content`` tells SQLite to index the text and
then discard it. Searching works as usual, but ``SELECT`` returns ``NULL`` for
every column except ``rowid``, as do auxiliary functions that return text.
Set the ``rowid`` explicitly so results can be tied back to a canonical table:

.. code-block:: python

   class NoteIndex(FTS5Model):
       content = SearchField()

       class Meta:
           database = db
           options = {'content': ''}

   # Index a note, linking the rowid back to the canonical row.
   NoteIndex.insert({'rowid': note.id, 'content': note.content}).execute()

Contentless tables accept ``INSERT`` only: ``UPDATE`` and ``DELETE`` raise an
``OperationalError``, because removing a row means removing the entries its
values produced, and a contentless table no longer has the values.
:meth:`~FTS5Model.delete_command` (the :ref:`"delete" command
<sqlite-fts-external-content>`) works if the original values can be
re-supplied, and :meth:`~FTS5Model.delete_all` clears the index outright. Two
independent options relax the restrictions further, and they
may be combined:

* ``contentless_delete=1`` (SQLite 3.43+) stores extra bookkeeping so SQLite
  can remove a row without being given its old values: ``DELETE`` works, as
  does ``UPDATE`` provided all indexed columns are assigned together
  (assigning a partial subset is an error). The practical choice when indexed
  rows change or disappear.
* ``contentless_unindexed=1`` (SQLite 3.47+) stores the values of
  ``UNINDEXED`` columns, which are then returned by ``SELECT`` and may be
  updated on their own. Useful for keeping a bit of metadata alongside an
  otherwise contentless index, for example a title to display with each hit
  without joining back to the source table.

Using both:

.. code-block:: python

   class NoteIndex(FTS5Model):
       content = SearchField()
       title = SearchField(unindexed=True)

       class Meta:
           database = db
           options = {
               'content': '',
               'contentless_delete': 1,
               'contentless_unindexed': 1}

   # The title is stored and comes back with each hit. The content is
   # indexed, then discarded, and selects as NULL.
   NoteIndex.insert({'rowid': note.id, 'content': note.content,
                     'title': note.title}).execute()

   # Updates must assign all indexed columns together, though the stored
   # title may also be updated on its own.
   (NoteIndex
    .update(content=new_content, title=new_title)
    .where(NoteIndex.rowid == note.id)
    .execute())
   NoteIndex.update(title='archived').where(NoteIndex.rowid == note.id).execute()

   NoteIndex.delete().where(NoteIndex.rowid == note.id).execute()

``SearchField``
~~~~~~~~~~~~~~~

.. class:: SearchField(unindexed=False, column_name=None)

   Field type for full-text search virtual tables. Raises an exception if
   constraints (``null=False``, ``unique=True``, etc.) are specified, since
   FTS tables do not support them.

   Pass ``unindexed=True`` to store metadata alongside the search index
   without indexing it:

   .. code-block:: python

      class DocumentIndex(FTS5Model):
          title = SearchField()
          content = SearchField()
          tags = SearchField()
          timestamp = SearchField(unindexed=True)

   .. method:: match(term)

      :param str term: full-text search query/terms.
      :return: a :class:`Expression` corresponding to the ``MATCH`` operator.

      Restrict a search to this column:

      .. code-block:: python

         # Search *only* the title field and return results ordered by
         # relevance.
         query = (DocumentIndex
                  .select(DocumentIndex, DocumentIndex.rank().alias('score'))
                  .where(DocumentIndex.title.match('python'))
                  .order_by(DocumentIndex.rank()))

      To search all indexed columns, use :meth:`FTS5Model.match`.

   .. method:: highlight(left, right)

      :param str left: opening tag for highlight, e.g. ``'<b>'``
      :param str right: closing tag for highlight, e.g. ``'</b>'``

      **FTS5 only.** Return the column's text with the terms matched by the
      search wrapped in the given delimiters:

      .. code-block:: python

         query = (DocumentIndex
                  .search(DocumentIndex.web_query('python'))
                  .select_extend(DocumentIndex.title.highlight('[', ']').alias('hi')))
         # e.g. result.hi = "Learn [python] the hard way"

      The highlighted text comes from the stored content, so this returns
      ``NULL`` for a :ref:`contentless table <sqlite-fts5-contentless>`.

   .. method:: snippet(left, right, over_length='...', max_tokens=16)

      :param str left: opening tag for highlight, e.g. ``'<b>'``
      :param str right: closing tag for highlight, e.g. ``'</b>'``
      :param str over_length: text to prepend or append when snippet exceeds
          the maximum number of tokens.
      :param int max_tokens: max tokens returned, between 1 and 64.

      **FTS5 only.** Like :meth:`~SearchField.highlight`, but returns a
      short excerpt of the column containing the match rather than the whole
      value. Returns ``NULL`` for a contentless table.

``FTS5Model``
~~~~~~~~~~~~~

.. class:: FTS5Model()

   Model class for working with SQLite FTS5 search indexes.

   Table options are declared in ``Meta.options`` and passed through to the
   ``CREATE VIRTUAL TABLE`` statement as-is, so any option FTS5 accepts may
   be used, including any not listed here. :class:`Model` and :class:`Field`
   values are resolved to the appropriate table or column name. The
   commonly-used options:

   * ``content``: :class:`Model` class (or table-name string) containing the
     external content, or empty string for "contentless".
   * ``content_rowid``: :class:`Field` (external content primary key)
   * ``contentless_delete``: set to ``1`` to allow ``DELETE`` and full-row
     ``UPDATE`` on a contentless table. Requires SQLite 3.43+.
   * ``contentless_unindexed``: set to ``1`` to store the values of
     ``UNINDEXED`` columns in a contentless table. Requires SQLite 3.47+.
   * ``prefix``: integer(s) to maintain a prefix index for. Ex: ``3`` or
     ``[3, 4]``
   * ``tokenize``: ``unicode61`` (default), ``ascii``, ``porter`` or
     ``trigram``. Ex: ``'porter unicode61'``
   * ``detail``: ``full`` (default), ``column`` or ``none``. Reduces index
     size at the cost of phrase queries (``none``) or per-column queries.

   Example:

   .. code-block:: python

      class DocumentIndex(FTS5Model):
          title = SearchField()
          content = SearchField()

          class Meta:
              database = db
              options = {
                  'tokenize': 'porter unicode61',
                  'prefix': [3, 4],
              }

   .. classmethod:: fts5_installed()

      Return ``True`` if FTS5 is available.

   .. classmethod:: match(term)

      :param term: Search term or expression. `FTS5 syntax documentation <https://sqlite.org/fts5.html#full_text_query_syntax>`__.

      Generate a SQL expression representing a search for the given term or
      expression in the table. SQLite uses the ``MATCH`` operator to indicate
      a full-text search.

      Invalid FTS5 syntax raises an ``OperationalError``.

      Example:

      .. code-block:: python

         # Search index for "search phrase" and return results ranked
         # by relevancy using the BM25 algorithm.
         query = (DocumentIndex
                  .select()
                  .where(DocumentIndex.match('search phrase'))
                  .order_by(DocumentIndex.rank()))

         for result in query:
             print('Result: %s' % result.title)

   .. classmethod:: search(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

      :param term: Search term or expression. `FTS5 syntax documentation <https://sqlite.org/fts5.html#full_text_query_syntax>`__.
      :param weights: A list of weights for the columns, ordered with respect
        to the column's position in the table. **Or**, a dictionary keyed by
        the field or field name and mapped to a value. Weights apply
        positionally across *all* columns, including ``UNINDEXED`` ones.
        Unrecognized keys are ignored.
      :param with_score: Whether the score should be returned as part of
        the ``SELECT`` statement.
      :param str score_alias: Alias to use for the calculated rank score.
        This is the attribute you will use to access the score
        if ``with_score=True``.
      :param bool explicit_ordering: Order using full SQL function to
          calculate rank, as opposed to referencing the score alias in the
          ORDER BY clause.

      Shorthand way of searching for a term and sorting results by the
      quality of the match using BM25.

      .. code-block:: python

          # Search on user input, best matches first.
          docs = DocumentIndex.search(DocumentIndex.web_query(user_input))
          for result in docs:
              print(result.title)

          # Weighted columns, returning the computed score.
          docs = DocumentIndex.search(
              DocumentIndex.web_query(user_input),
              weights={'title': 2.0, 'content': 1.0},
              with_score=True,
              score_alias='search_score')
          for result in docs:
              print(result.title, result.search_score)

      .. note::
         The term is FTS5 query syntax. Characters that FTS5 treats as
         syntax are removed from unquoted portions of the term (which also
         removes the ``^`` initial-token operator), but the result is not
         guaranteed to be valid: unbalanced quotes or parentheses still
         raise.

         Use :meth:`~FTS5Model.web_query` to convert common "web search" style
         queries into valid FTS5 syntax.

   .. classmethod:: web_query(query)

      :param str query: a "web search" style query, e.g. from a search box.
      :return: an equivalent FTS5 query, as a string.

      Translate the query syntax people expect from a web search engine into
      the `FTS5 query syntax <https://sqlite.org/fts5.html#full_text_query_syntax>`_.
      Pass the result to :meth:`~FTS5Model.search` or :meth:`~FTS5Model.match`:

      .. code-block:: python

         results = DocumentIndex.search(DocumentIndex.web_query(user_input))

      The supported syntax:

      ============================== ==========================================
      Input                          Meaning
      ============================== ==========================================
      ``python sqlite``              both terms (words are AND-ed)
      ``python OR sqlite``           either term
      ``python NOT sqlite``          the first term, excluding the second
      ``python -sqlite``             same, using the leading-minus form
      ``"full text search"``         the exact phrase
      ``pyth*``                      terms starting with "pyth"
      ``title: python``              the term, in the ``title`` column only
      ``{title content}: python``    the term, in either named column
      ``title: (python OR sqlite)``  the group, in the ``title`` column only
      ``(python OR sqlite) fast``    grouping with parentheses
      ============================== ==========================================

      Anything else is searched as ordinary text, so characters that are FTS5
      syntax do not have to be escaped: ``covid-19``, ``o'brien`` and ``c++``
      all search for what they say. Column filters naming a column the model
      does not have (or an ``UNINDEXED`` column, which can never match) are
      searched as text.

      The query is **always** valid, no matter what was typed. Unbalanced quotes
      and parentheses are repaired, operators with nothing to operate on are
      dropped, deeply-nested input is flattened, and a query with no terms in
      it becomes ``""``, which matches nothing. Empty input therefore returns
      no rows rather than raising.

      An exclusion applies to the terms it is AND-ed with, so
      ``python -sqlite`` excludes as expected, while in ``python OR -sqlite``
      the exclusion has nothing to apply to and is dropped.

      .. note::
         The minus sign has a different meaning here than in FTS5 itself. In
         FTS5, ``-title: python`` matches "python" in every column *except*
         the title. In a search box it means "exclude documents with python in
         the title", which is how :meth:`~FTS5Model.web_query` translates it.

      FTS5 features that have no search-box equivalent are searched as text
      rather than being passed through. That includes ``NEAR()`` groups, the
      ``^`` initial-token operator, and ``+`` phrase concatenation. Use
      :meth:`~FTS5Model.match` to write those queries directly.

   .. classmethod:: rank(col1_weight, col2_weight...coln_weight)

      :param float col_weight: (Optional) weight to give to the *ith* column
          of the model. By default all columns have a weight of ``1.0``.

      Generate an expression that will calculate and return the quality of
      the search match using the `BM25 algorithm <https://en.wikipedia.org/wiki/Okapi_BM25>`_.
      This value can be used to sort the search results.

      .. code-block:: python

         query = (DocumentIndex
                  .select(
                      DocumentIndex,
                      DocumentIndex.rank().alias('score'))
                  .where(DocumentIndex.match('search phrase'))
                  .order_by(DocumentIndex.rank()))

         for search_result in query:
             print(search_result.title, search_result.score)

   .. staticmethod:: clean_query(query, replace=chr(26))

      Replace characters that FTS5 treats as syntax with ``replace`` in the
      unquoted portions of ``query``. This is applied automatically by
      :meth:`~FTS5Model.search`. It does not guarantee a valid query, and
      :meth:`~FTS5Model.web_query` is usually the better choice.

   .. staticmethod:: validate_query(query)

      Return ``True`` if ``query`` contains no characters that FTS5 would
      treat as syntax outside of a quoted phrase. This only inspects the
      characters used and will not catch every malformed query.

   .. classmethod:: VocabModel(table_type='row'|'col'|'instance', table=None)

      :param str table_type: Either 'row', 'col' or 'instance'.
      :param table: Name for the vocab table. If not specified, defaults to
          the index's table name plus ``"_v"`` for the *row* type, and
          ``"_v_col"`` or ``"_v_instance"`` for the other two.

      Generate a model class suitable for accessing the `vocab table <http://sqlite.org/fts5.html#the_fts5vocab_virtual_table_module>`_
      corresponding to FTS5 search index. The columns depend on the table
      type:

      * *row* has ``term``, ``doc`` and ``cnt``
      * *col* has ``term``, ``col``, ``doc`` and ``cnt``
      * *instance* has ``term``, ``doc``, ``col`` and ``offset``

      A new class is returned on each call, and the table must be created
      before it can be queried:

      .. code-block:: python

         Vocab = DocumentIndex.VocabModel()
         db.create_tables([Vocab])

         # The 10 most common terms in the index.
         query = Vocab.select().order_by(Vocab.cnt.desc()).limit(10)
         for term in query:
             print(term.term, term.doc, term.cnt)

   .. classmethod:: rebuild()

      Discard and rebuild the search index from its content. Not valid for
      contentless tables, which have no content to rebuild from.

   .. classmethod:: optimize()

      Merge the index into as few b-tree segments as possible. This can be
      expensive on a large index, but improves query performance.

   .. classmethod:: merge(npages)

      Merge ``npages`` pages of index segments together.

   .. classmethod:: automerge(level)

      Configure the automerge level, between 0 and 64. Zero disables
      automatic merging.

   .. classmethod:: set_pgsz(pgsz)

      Set the page size used by the index.

   .. classmethod:: set_rank(rank_expression)

      Set the default ranking function used by the ``rank`` column, e.g.
      ``set_rank('bm25(10.0, 5.0)')``.

   .. classmethod:: delete_all()

      Remove all rows from the index. Only valid for contentless and
      external-content tables.

   .. classmethod:: delete_command(rowid, **values)

      :param rowid: the row to remove.
      :param values: the values of the indexed columns, keyed by field name
          (or column name), exactly as they were indexed.

      Remove a row using the fts5 "delete" command. This is how rows are
      removed from :ref:`external-content <sqlite-fts-external-content>` and
      :ref:`contentless <sqlite-fts5-contentless>` tables, which cannot look
      the old values up themselves. The command exists only for those two
      configurations. Default-storage and ``contentless_delete=1`` tables
      reject it and use ordinary ``DELETE`` statements.

      SQLite requires the values to match what was indexed, treating an
      omitted column as NULL. A mismatch leaves stale entries behind,
      detectable by :meth:`~FTS5Model.integrity_check` with ``rank=1`` on an
      external-content table and undetectable on a contentless one. A value
      is therefore required for every indexed column (pass ``None`` where
      NULL was indexed), and a missing or unrecognized column raises
      ``ValueError``.

   .. classmethod:: integrity_check(rank=0)

      Verify the index, raising ``DatabaseError`` if it is corrupt. Pass
      ``rank=1`` to also verify an external-content index against its content
      table, which is what detects an index that has drifted out of sync.

.. _sqlite-fts4:

FTS3 and FTS4 / ``FTSModel``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. note::
   FTS3 and FTS4 are the legacy full-text search extensions. Use :ref:`FTS5 <sqlite-fts5>`
   where possible.

:class:`FTSModel` stores data in an `FTS4 <https://www.sqlite.org/fts3.html>`_
index (to use FTS3, set ``Meta.extension_module = 'FTS3'``). It works the way
:class:`FTS5Model` does: all columns besides the implicit ``rowid`` primary
key are :class:`SearchField` instances, only ``MATCH`` and ``rowid`` lookups
are efficient, and the ``rowid`` is best treated as a foreign-key to an
ordinary table holding the canonical data. The differences:

* There is no built-in ranking. Peewee provides ranking functions,
  implemented in Python (or C), which must be registered by passing
  ``rank_functions=True`` to :class:`SqliteDatabase`. Without it,
  :meth:`~FTSModel.search` and the ranking functions fail with, e.g.,
  ``no such function: fts_rank``.
* :meth:`~FTSModel.search` ranks by simple term frequency, while
  :meth:`~FTSModel.search_bm25` uses BM25 (FTS4 only). Neither scrubs the
  search string.
* :meth:`~FTS5Model.web_query`, :meth:`~SearchField.highlight` and
  :meth:`~SearchField.snippet` are FTS5-only and cannot be used with FTS4.
* :ref:`External content <sqlite-fts-external-content>` differs in the
  details: FTS4 always uses the content table's ``rowid`` and rejects the
  ``content_rowid`` option, and there is no "delete" command. Plain
  ``UPDATE`` and ``DELETE`` read the old values from the content table, so
  sync triggers must be ``BEFORE`` triggers on the content table.
* The table options differ, see :class:`FTSModel`.

.. code-block:: python

   from playhouse.sqlite_ext import FTSModel, SearchField

   db = SqliteDatabase('app.db', rank_functions=True)

   class DocumentIndex(FTSModel):
       title = SearchField()
       content = SearchField()

       class Meta:
           database = db

   # Store a document, setting rowid to the id of the canonical row.
   DocumentIndex.create(rowid=document.id, title=document.title,
                        content=document.content)

   # Search, best matches first.
   results = DocumentIndex.search_bm25('python sqlite', with_score=True)
   for r in results:
       print(r.title, r.score)

``FTSModel``
~~~~~~~~~~~~

.. class:: FTSModel()

   Base Model class suitable for working with SQLite FTS3 / FTS4.

   Table options are declared in ``Meta.options`` and passed through to the
   ``CREATE VIRTUAL TABLE`` statement as-is, so any option FTS4 accepts may
   be used, whether or not it is listed here. The commonly-used options:

   * ``content``: :class:`Model` class (or table-name string) containing the
     external content, or empty string for "contentless".
   * ``prefix``: integer(s) to maintain a prefix index for. Ex: ``2`` or
     ``[2, 3]``
   * ``tokenize``: ``simple`` (default), ``porter`` or ``unicode61``. Ex:
     ``'porter'``
   * ``notindexed``: name of a column to omit from the index.
   * ``matchinfo``: set to ``fts3`` to store less match data, at the cost of
     the ranking functions that need it.
   * ``compress`` / ``uncompress``: names of registered functions used to
     compress the stored content.

   .. classmethod:: match(term)

      :param term: Search term or expression. `FTS syntax documentation <https://www.sqlite.org/fts3.html#full_text_index_queries>`__.

      Generate a SQL expression representing a search for the given term or
      expression in the table. SQLite uses the ``MATCH`` operator to indicate
      a full-text search. The term is passed through unmodified, so invalid
      syntax raises an ``OperationalError``.

   .. classmethod:: search(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

      :param term: Search term or expression. `FTS syntax documentation <https://www.sqlite.org/fts3.html#full_text_index_queries>`__.
      :param weights: A list of weights for the columns, ordered with respect
        to the column's position in the table. **Or**, a dictionary keyed by
        the field or field name and mapped to a value. Unrecognized keys are
        ignored.
      :param with_score: Whether the score should be returned as part of
        the ``SELECT`` statement.
      :param str score_alias: Alias to use for the calculated rank score.
        This is the attribute you will use to access the score
        if ``with_score=True``.
      :param bool explicit_ordering: Order using full SQL function to
          calculate rank, as opposed to referencing the score alias in the
          ORDER BY clause.

      Shorthand way of searching for a term and sorting results by the
      quality of the match. Requires ``rank_functions=True`` on the database.

      This method uses a simplified algorithm for determining the
      relevance rank of results. For more sophisticated result ranking,
      use the :meth:`~FTSModel.search_bm25` method.

      Unlike :meth:`FTS5Model.search`, the term is passed through unmodified.

   .. classmethod:: search_bm25(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

      Same as :meth:`~FTSModel.search`, but using the BM25 ranking algorithm.
      Requires ``rank_functions=True`` on the database.

      .. attention::
         The BM25 ranking algorithm is only available for FTS4 via a
         peewee-provided function. If you are using FTS3, use the
         :meth:`~FTSModel.search` method instead.

   .. classmethod:: search_bm25f(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

      Same as :meth:`FTSModel.search_bm25`, but using the BM25f variant
      of the BM25 ranking algorithm.

   .. classmethod:: search_lucene(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

      Same as :meth:`FTSModel.search_bm25`, but using the result ranking
      algorithm from the Lucene search engine.

   .. classmethod:: rank(col1_weight, col2_weight...coln_weight)

      :param float col_weight: (Optional) weight to give to the *ith* column
          of the model. By default all columns have a weight of ``1.0``.

      Generate an expression that will calculate and return the quality of
      the search match. This ``rank`` can be used to sort the search results.
      Requires ``rank_functions=True`` on the database.

      The algorithm used by :meth:`~FTSModel.rank` is simple and
      relatively quick. For more sophisticated result ranking, use:

      * :meth:`~FTSModel.bm25`
      * :meth:`~FTSModel.bm25f`
      * :meth:`~FTSModel.lucene`

   .. classmethod:: bm25(col1_weight, col2_weight...coln_weight)

      :param float col_weight: (Optional) weight to give to the *ith* column
          of the model. By default all columns have a weight of ``1.0``.

      Same as :meth:`~FTSModel.rank`, but using the `BM25 algorithm
      <https://en.wikipedia.org/wiki/Okapi_BM25>`_. Requires FTS4 and
      ``rank_functions=True`` on the database. If you are using FTS3, use
      :meth:`~FTSModel.rank` instead.

   .. classmethod:: bm25f(col1_weight, col2_weight...coln_weight)

      Identical to :meth:`~FTSModel.bm25`, except that it uses the BM25f
      variant of the BM25 ranking algorithm.

   .. classmethod:: lucene(col1_weight, col2_weight...coln_weight)

      Identical to :meth:`~FTSModel.bm25`, except that it uses the Lucene
      search result ranking algorithm.

   .. classmethod:: rebuild()

      Discard and rebuild the search index from its content.

   .. classmethod:: optimize()

      Merge the index into as few b-tree segments as possible.

   .. classmethod:: merge(blocks=200, segments=8)

      Merge ``blocks`` blocks of ``segments`` index segments together.

   .. classmethod:: automerge(state=True)

      Enable or disable automatic merging of index segments.

   .. classmethod:: integrity_check()

      Verify the index, raising ``DatabaseError`` if it is corrupt.


.. _sqlite-udf:

User-Defined Function Collection
---------------------------------

.. module:: playhouse.sqlite_udf

The ``playhouse.sqlite_udf`` contains a number of functions, aggregates, and
table-valued functions grouped into named collections.

.. code-block:: python

   from playhouse.sqlite_udf import register_all, register_groups
   from playhouse.sqlite_udf import DATE, STRING

   db = SqliteDatabase('my_app.db')

   register_all(db)                   # Register every function.
   register_groups(db, DATE, STRING)  # Register selected groups.

   # Register individual functions:
   from playhouse.sqlite_udf import gzip, gunzip
   db.register_function(gzip, 'gzip')
   db.register_function(gunzip, 'gunzip')

Once registered, call functions via Peewee's ``fn`` namespace or raw SQL:

.. code-block:: python

   # Find most common URL hostnames.
   query = (Link
            .select(fn.hostname(Link.url).alias('host'), fn.COUNT(Link.id))
            .group_by(fn.hostname(Link.url))
            .order_by(fn.COUNT(Link.id).desc())
            .tuples())

Available functions
^^^^^^^^^^^^^^^^^^^

**CONTROL_FLOW**

.. function:: if_then_else(cond, truthy, falsey=None)

   Simple ternary-type operator, where, depending on the truthiness of the
   ``cond`` parameter, either the ``truthy`` or ``falsey`` value will be
   returned.

**DATE**

.. function:: strip_tz(date_str)

   :param date_str: A datetime, encoded as a string.
   :returns: The datetime with any timezone info stripped off.

   The time is not adjusted. Only the timezone is removed.

.. function:: human_delta(nseconds, glue=', ')

   :param int nseconds: Number of seconds, total, in timedelta.
   :param str glue: Fragment to join values.
   :returns: Easy-to-read description of timedelta.

   Example, 86471 -> "1 day, 1 minute, 11 seconds"

.. function:: mintdiff(datetime_value)

   :param datetime_value: A date-time.
   :returns: Minimum difference between any two values in list.

   *Aggregate*: minimum difference between any two datetimes.

.. function:: avgtdiff(datetime_value)

   :param datetime_value: A date-time.
   :returns: Average difference between values in list.

   *Aggregate*: average difference between consecutive values.

.. function:: duration(datetime_value)

   :param datetime_value: A date-time.
   :returns: Duration from smallest to largest value in list, in seconds.

   *Aggregate*: duration from the smallest to the largest value, in seconds.

**FILE**

.. function:: file_ext(filename)

   :param str filename: Filename to extract extension from.
   :return: Returns the file extension, including the leading ".".

.. function:: file_read(filename)

   :param str filename: Filename to read.
   :return: Contents of the file.

**HELPER**

.. function:: gzip(data, compression=9)

   :param bytes data: Data to compress.
   :param int compression: Compression level (9 is max).
   :returns: Compressed binary data.

.. function:: gunzip(data)

   :param bytes data: Compressed data.
   :returns: Uncompressed binary data.

.. function:: hostname(url)

   :param str url: URL to extract hostname from.
   :returns: hostname portion of URL

.. function:: toggle(key)

   :param key: Key to toggle.

   Toggle a key between True/False state. Example:

   .. code-block:: pycon

      >>> toggle('my-key')
      True
      >>> toggle('my-key')
      False
      >>> toggle('my-key')
      True

.. function:: setting(key, value=None)

   :param key: Key to set/retrieve.
   :param value: Value to set.
   :returns: Value associated with key.

   Store/retrieve a setting in memory and persist during lifetime of
   application. To get the current value, specify key. To set a new
   value, call with key and new value.

.. function:: clear_toggles()

   Clears all state associated with the :func:`toggle` function.

.. function:: clear_settings()

   Clears all state associated with the :func:`setting` function.

**MATH**

.. function:: randomrange(start, stop=None, step=None)

   :param int start: Start of range (inclusive)
   :param int end: End of range(not inclusive)
   :param int step: Interval at which to return a value.

   Return a random integer between ``[start, end)``.

.. function:: gauss_distribution(mean, sigma)

   :param float mean: Mean value
   :param float sigma: Standard deviation

.. function:: sqrt(n)

   Calculate the square root of ``n``.

.. function:: tonumber(s)

   :param str s: String to convert to number.
   :returns: Integer, floating-point or NULL on failure.

.. function:: mode(val)

   :param val: Numbers in list.
   :returns: The mode, or most-common, number observed.

   *Aggregate*: calculates *mode* of values.

.. function:: minrange(val)

   :param val: Value
   :returns: Min difference between two values.

   *Aggregate*: minimum distance between two numbers in the sequence.

.. function:: avgrange(val)

   :param val: Value
   :returns: Average difference between values.

   *Aggregate*: average distance between consecutive numbers in the sequence.

.. function:: range(val)

   :param val: Value
   :returns: The range from the smallest to largest value in sequence.

   *Aggregate*: range of values observed.

.. function:: median(val)

   :param val: Value
   :returns: The median, or middle, value in a sequence.

   *Aggregate*: median value of a sequence.

   .. note:: Only available if you compiled the ``_sqlite_udf`` extension.

**STRING**

.. function:: substr_count(haystack, needle)

   Returns number of times ``needle`` appears in ``haystack``.

.. function:: strip_chars(haystack, chars)

   Strips any characters in ``chars`` from beginning and end of ``haystack``.

.. function:: damerau_levenshtein_dist(s1, s2)

   Computes the edit distance from s1 to s2 using the damerau variant of the
   levenshtein algorithm.

   .. note:: Only available if you compiled the ``_sqlite_udf`` extension.

.. function:: levenshtein_dist(s1, s2)

   Computes the edit distance from s1 to s2 using the levenshtein algorithm.

   .. note:: Only available if you compiled the ``_sqlite_udf`` extension.

.. function:: str_dist(s1, s2)

   Computes the edit distance from s1 to s2 using the standard library
   SequenceMatcher's algorithm.

   .. note:: Only available if you compiled the ``_sqlite_udf`` extension.

