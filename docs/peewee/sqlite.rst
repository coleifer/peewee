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

:class:`CySqliteDatabase` (``playhouse.cysqlite_ext``)
   Extends :class:`SqliteDatabase`, uses `cysqlite <https://cysqlite.readthedocs.io/en/latest/>`__ driver.

   * All above functionality
   * Table-value functions
   * Commit / Rollback / Update / Progress / Trace hooks
   * BLOB I/O
   * Online backups
   * Can be built `with encryption <https://cysqlite.readthedocs.io/en/latest/installation.html#sqlcipher>`__.

:class:`APSWDatabase` (``playhouse.apsw_ext``)
   Extends :class:`SqliteDatabase`, uses `apsw <https://github.com/rogerbinns/apsw/>`__ driver.

   APSW is a thin C-level driver that exposes the full range of SQLite
   functionality.

:class:`SqlCipherDatabase` (``playhouse.sqlcipher_ext``)
   Extends :class:`SqliteDatabase`, uses `sqlcipher3 <https://github.com/coleifer/sqlcipher3>`__ driver.

   SQLCipher provides transparent full-database encryption using 256-bit AES,
   ensuring data on-disk is secure.

:class:`SqliteQueueDatabase` (``playhouse.sqliteq``)
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
   User-defined tables (requres ``cysqlite``).

   * :meth:`CySqliteDatabase.register_table_function`
   * :meth:`CySqliteDatabase.table_function` - decorator.

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

User-defined window functions are simply aggregates with two additional
methods:

* ``step(*values)`` - called for each row being aggregated.
* ``inverse(*values)`` - "invert" the effect of a call to ``step(*values)``.
* ``value()`` - return the current value of the aggregate.
* ``finalize()`` - return final aggregate value.

.. code-block:: python

   # Window functions are normal aggregates with two additional methods:
   # inverse(value) - Perform the inverse of step(value).
   # value() - Report value at current step.
   @db.aggregate('mysum')
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
   Book.select().order_by(Book.title.asc(collation='reverse'))

Table function example
^^^^^^^^^^^^^^^^^^^^^^

Example user-defined table-value function (see `cysqlite TableFunction docs <https://cysqlite.readthedocs.io/en/latest/api.html#tablefunction>`_
for full details on ``TableFunction``).

.. code-block:: python

   from cysqlite import TableFunction
   from playhouse.cysqlite_ext import CySqliteDatabase

   db = CySqliteDatabase('my_app.db')

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

Shared Libraries
^^^^^^^^^^^^^^^^

Example:

   .. code-block:: python

      # Load `closure.so` shared library in the current directory.
      db = SqliteDatabase('my_app.db')
      db.load_extension('closure')

.. note::
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

:class:`CySqliteDatabase` uses the `cysqlite <https://cysqlite.readthedocs.io>`_
driver, a high-performance alternative to the standard library ``sqlite3``
module. ``cysqlite`` provides additional features and hooks not available with
in the standard library ``sqlite3`` driver.

Installation:

.. code-block:: shell

   pip install cysqlite

Usage:

.. code-block:: python

   from playhouse.cysqlite_ext import CySqliteDatabase

   db = CySqliteDatabase('my_app.db', pragmas={
       'cache_size': -64000,
       'journal_mode': 'wal',
       'foreign_keys': 1,
   })

.. class:: CySqliteDatabase(database, **kwargs)

   :param list pragmas: A list of 2-tuples containing pragma key and value to
       set every time a connection is opened.
   :param timeout: Set the busy-timeout on the SQLite driver (in seconds).
   :param bool rank_functions: Make search result ranking functions available.
       Recommended only when using FTS4.
   :param bool regexp_function: Make the REGEXP function available.

   .. seealso::
      CySqliteDatabase extends :class:`SqliteDatabase` and inherits all
      methods for declaring user-defined functions, aggregates, window
      functions, collations, pragmas, etc.

   Example:

   .. code-block:: python

       db = CySqliteDatabase('app.db', pragmas={'journal_mode': 'wal'})

   .. method:: table_function(name)

      Class-decorator for registering a ``cysqlite.TableFunction``. Table
      functions are user-defined functions that, rather than returning a
      single, scalar value, can return any number of rows of tabular data.

      See `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#tablefunction>`__ for details on
      ``TableFunction`` API.

      .. code-block:: python

         from cysqlite import TableFunction

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

         cursor = db.execute_sql('SELECT * FROM series(?, ?, ?)', (0, 5, 2))
         for (value,) in cursor:
             print(value)

         # Prints:
         # 0
         # 2
         # 4

   .. method:: unregister_table_function(name)

      :param name: Name of the user-defined table function.
      :returns: True or False, depending on whether the function was removed.

      Unregister the user-defined scalar function.

   .. method:: on_commit(fn)

      :param fn: callable or ``None`` to clear the current hook.

      Register a callback to be executed whenever a transaction is committed
      on the current connection. The callback accepts no parameters and the
      return value is ignored.

      However, if the callback raises a :class:`ValueError`, the
      transaction will be aborted and rolled-back.

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

   .. method:: trace(fn, mask=2):

      :param fn: callable or ``None`` to clear the current trace hook.
      :param int mask: mask of what types of events to trace. Default value
          corresponds to ``SQLITE_TRACE_PROFILE``.

      Register a trace hook (``sqlite3_trace_v2``). Trace callback must
      accept 4 parameters, which vary depending on the operation being
      traced.

      * event: type of event, e.g. ``SQLITE_TRACE_PROFILE``.
      * sid: memory address of statement (only ``SQLITE_TRACE_CLOSE``), else -1.
      * sql: SQL string (only ``SQLITE_TRACE_STMT``), else None.
      * ns: estimated number of nanoseconds the statement took to run (only
        ``SQLITE_TRACE_PROFILE``), else -1.

      Any return value from callback is ignored.

      More details can be found in the `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#Connection.trace>`__.

   .. method:: progress(fn, n=1)

      :param fn: callable or ``None`` to clear the current progress handler.
      :param int n: approximate number of VM instructions to execute between
        calls to the progress handler.

      Register a progress handler (``sqlite3_progress_handler``). Callback
      takes no arguments and returns 0 to allow progress to continue or any
      non-zero value to interrupt progress.

      More details can be found in the `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#Connection.progress>`__.

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

   .. method:: backup_to_file(filename, pages, name, progress)

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

   .. method:: blob_open(table, column, rowid, read_only=False)

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


.. class:: PooledCySqliteDatabase(database, **kwargs)

   Connection-pooling variant of :class:`CySqliteDatabase`.

.. _apsw:

APSW
----

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

.. warning::
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

.. note::
   SQLCipher can be configured using a number of extension PRAGMAs. The list
   of PRAGMAs and their descriptions can be found in the `SQLCipher documentation <https://www.zetetic.net/sqlcipher/sqlcipher-api/>`__.

.. class:: SqlCipherDatabase(database, passphrase, **kwargs)

   :param str database: Path to the encrypted database file.
   :param str passphrase: Encryption passphrase (should be 8 character minimum;
       enforce stronger requirements in your application).

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

.. warning::
   **Transactions are not supported.** Because writes from different threads
   are interleaved, there is no way to guarantee that the statements in a
   transaction from one thread execute atomically without statements from
   another thread appearing between them. The ``atomic()`` and
   ``transaction()`` methods raise a ``ValueError`` if called.

   If you need to temporarily bypass the queue and write directly (for
   example, during a batch import), use :meth:`~SqliteQueueDatabase.pause`
   and :meth:`~SqliteQueueDatabase.unpause`.

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
      disconnect it. The calling thread takes over direct database access.
      Must be followed by a call to :meth:`~SqliteQueueDatabase.unpause`.

   .. method:: unpause()

      Resume the writer thread and reconnect the queue.


.. _sqlite-fields:

SQLite-Specific Fields
----------------------

These field classes live in ``playhouse.sqlite_ext`` and can be used with:

* :class:`SqliteDatabase`
* :class:`CySqliteDatabase`
* :class:`APSWDatabase`
* :class:`SqlCipherDatabase`
* :class:`SqliteQueueDatabase`

.. class:: RowIDField()

   Primary-key field mapped to SQLite's implicit ``rowid`` column.

   For more information, see the SQLite documentation on `rowid tables <https://www.sqlite.org/rowidtable.html>`_.

   .. code-block:: python

      class Note(Model):
          rowid = RowIDField()  # Implied primary_key=True.
          content = TextField()
          timestamp = TimestampField()

   RowIDField can be mapped to a different field name, but it's underlying
   column name will always be ``rowid``.

   .. code-block:: python

      class Note(Model):
          id = RowIDField()
          ...

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

:class:`JSONField` enables storing and querying JSON data in SQLite using
the `SQLite json functions <https://sqlite.org/json1.html>`_.

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
               .tuples())

      # [([1, 99, 1, 1], 4), ([1, 1], 2)]

   Let's add a nested value and then see how to iterate through it's contents
   recursively using the :meth:`~JSONField.tree` method:

   .. code-block:: python

      Config.create(data={'x1': {'y1': 'z1', 'y2': 'z2'}, 'x2': [1, 2]})

      tree = Config.data.tree().alias('tree')
      query = (Config
               .select(Config.id, tree.c.fullkey, tree.c.value)
               .from_(Config, tree))

      for row in query.tuples():
          print(row)

      (1, '$', {'x1': {'y1': 'z1', 'y2': 'z2'}, 'x2': [1, 2]}),
      (1, '$.x2', [1, 2]),
      (1, '$.x2[0]', 1),
      (1, '$.x2[1]', 2),
      (1, '$.x1', {'y1': 'z1', 'y2': 'z2'}),
      (1, '$.x1.y1', 'z1'),
      (1, '$.x1.y2', 'z2')]

   The :meth:`~JSONField.tree` and :meth:`~JSONField.children` methods
   are powerful. For more information on how to utilize them, see the
   `json1 extension documentation <http://sqlite.org/json1.html#jtree>`_.

   .. method:: __getitem__(item)

      :param item: Access a specific key or array index in the JSON data.
      :return: a special object exposing access to the JSON data.
      :rtype: JSONPath

      Access a specific key or array index in the JSON data. Returns a
      :class:`JSONPath` object, which exposes convenient methods for
      reading or modifying a particular part of a JSON object.

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
          # top-level keys and values in it's data field.
          kd = KeyData.data.children().alias('children')
          query = (KeyData
                   .select(kd.c.key, kd.c.value, kd.c.fullkey)
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
          # keys and values in it's data field, recursively.
          kd = KeyData.data.tree().alias('tree')
          query = (KeyData
                   .select(kd.c.key, kd.c.value, kd.c.fullkey)
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

   A convenient, Pythonic way of representing JSON paths for use with
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


.. _sqlite-fts:

Full-Text Search
-----------------

Peewee supports :ref:`FTS3, FTS4 <sqlite-fts4>` (legacy, widely available) and
:ref:`FTS5 <sqlite-fts5>` full-text search extensions.

The general pattern is:

1. Define a :class:`FTSModel` or :class:`FTS5Model` subclass with one or more
   :class:`SearchField` columns.
2. When a row is created or updated in the source table, insert or update
   the corresponding row in the search index.
3. Query the index using :meth:`~FTSModel.match` and rank results with
   :meth:`~FTSModel.bm25` (or :meth:`~FTSModel.rank` for FTS5).

Consult the SQLite documentation for FTS query syntax diagrams:

* `FTS3 and FTS4 <https://www.sqlite.org/fts3.html#full_text_index_queries>`__
* `FTS5 <https://sqlite.org/fts5.html#full_text_query_syntax>`__

.. class:: SearchField(unindexed=False, column_name=None)

   Field type for full-text search virtual tables. Raises an exception if
   constraints (``null=False``, ``unique=True``, etc.) are specified, since
   FTS tables do not support them.

   Pass ``unindexed=True`` to store metadata alongside the search index
   without indexing it:

   .. code-block:: python

      class DocumentIndex(FTSModel):
          title = SearchField()
          content = SearchField()
          tags = SearchField()
          timestamp = SearchField(unindexed=True)

   .. method:: match(term)

      :param str term: full-text search query/terms.
      :return: a :class:`Expression` corresponding to the ``MATCH``
          operator.

      Sqlite's full-text search supports searching either the full table,
      including all indexed columns, **or** searching individual columns. The
      :meth:`~SearchField.match` method can be used to restrict search to
      a single column:

      .. code-block:: python

         # Search *only* the title field and return results ordered by
         # relevance, using bm25.
         query = (DocumentIndex
                  .select(DocumentIndex, DocumentIndex.bm25().alias('score'))
                  .where(DocumentIndex.title.match('python'))
                  .order_by(DocumentIndex.bm25()))

      To search *all* indexed columns, use the :meth:`FTSModel.match` method:

      .. code-block:: python
         :emphasize-lines: 5

         # Searches *both* the title and body and return results ordered by
         # relevance, using bm25.
         query = (DocumentIndex
                  .select(DocumentIndex, DocumentIndex.bm25().alias('score'))
                  .where(DocumentIndex.match('python'))
                  .order_by(DocumentIndex.bm25()))

   .. method:: highlight(left, right)

      :param str left: opening tag for highlight, e.g. ``'<b>'``
      :param str right: closing tag for highlight, e.g. ``'</b>'``

      When performing a search using the ``MATCH`` operator, FTS5 can return
      text highlighting matches in a given column.

      .. code-block:: python

         # Search for items matching string 'python' and return the title
         # highlighted with square brackets.
         query = (SearchIndex
                  .search('python')
                  .select(SearchIndex.title.highlight('[', ']').alias('hi')))

         for result in query:
             print(result.hi)

         # For example, might print:
         # Learn [python] the hard way

   .. method:: snippet(left, right, over_length='...', max_tokens=16)

      :param str left: opening tag for highlight, e.g. ``'<b>'``
      :param str right: closing tag for highlight, e.g. ``'</b>'``
      :param str over_length: text to prepend or append when snippet exceeds
          the maximum number of tokens.
      :param int max_tokens: max tokens returned, **must be 1 - 64**.

      When performing a search using the ``MATCH`` operator, FTS5 can return
      text with a snippet containing the highlighted match in a given column.

      .. code-block:: python

         # Search for items matching string 'python' and return the title
         # highlighted with square brackets.
         query = (SearchIndex
                  .search('python')
                  .select(SearchIndex.title.snippet('[', ']').alias('snip')))

         for result in query:
             print(result.snip)

.. _sqlite-fts4:

FTS4 / ``FTSModel``
^^^^^^^^^^^^^^^^^^^

FTSModel enables Peewee applications to store data in an efficient full-text
search index using SQLite `FTS4 <https://www.sqlite.org/fts3.html>`_.

FTSModel caveats:

* All queries **except** ``MATCH`` and ``rowid`` lookup require a full table scan.
* Constraints, foreign-keys, and indexes are not supported.
* All columns are treated as ``TEXT``.
* No built-in ranking. Peewee provides several implementations which can be
  automatically registered by passing ``rank_functions=True`` to ``SqliteDatabase(...)``.
* FTSModel ``rowid`` primary key may be declared using :class:`RowIDField`.
  Lookups on the ``rowid`` are very efficient.

Given these constraints all fields besides ``rowid`` should be instances of
:class:`SearchField` to ensure correctness.

.. tip::
   Because of the lack of secondary indexes, it usually makes sense to treat
   the ``FTSModel.rowid`` primary key as a foreign-key to a row in a normal
   SQLite table.

Example:

.. code-block:: python

   from peewee import *
   from playhouse.sqlite_ext import FTSModel, SearchField

   db = SqliteDatabase('app.db', rank_functions=True)

   class Document(Model):
       # Canonical source of data, stored in a normal table.
       author = ForeignKeyField(User, backref='documents')
       title = TextField(null=False, unique=True)
       content = TextField(null=False)
       timestamp = DateTimeField()

       class Meta:
           database = db

   class DocumentIndex(FTSModel):
       # Full-text search index.
       rowid = RowIDField()
       title = SearchField()
       content = SearchField()
       author = SearchField(unindexed=True)

       class Meta:
           database = db
           # Use the porter stemming algorithm to tokenize content, optimize
           # prefix searches of 3 or 4 characters.
           options = {'tokenize': 'porter unicode61', 'prefix': [3, 4]}

Store data by inserting it into the FTS table:

.. code-block:: python

   # Store a document in the index:
   DocumentIndex.create(
       rowid=document.id,  # Set rowid to match Document's id.
       title=document.title,
       content=document.content,
       author=document.author.get_full_name())

   # Equivalent:
   (DocumentIndex
    .insert({
        'rowid': document.id,
        'title': document.title,
        'content': document.content,
        'author': document.author.get_full_name()})
    .execute())

:class:`FTSModel` provides several shortcuts for full-text search queries:

.. code-block:: python

   # Simple search using basic ranking algorithm.
   results = DocumentIndex.search('python sqlite')

   # BM25 search With score and per-column weighting:
   results = DocumentIndex.search_bm25(
       'python sqlite',
       weights={'title': 2.0, 'content': 1.0},
       with_score=True,
       score_alias='relevance')

   for r in results:
       print(r.title, r.relevance)

.. tip::
   An important method of searching relies on the ``rowid`` of the indexed
   data matching the document's canonical id. Using this technique we can
   apply additional filters and retrieve the matching ``Document`` objects
   efficiently:

   .. code-block:: python

      # Search and ensure we only retrieve articles from the last 30 days.
      cutoff = datetime.datetime.now() - datetime.timedelta(days=30)

      query = (Document
               .select()
               .join(
                   DocumentIndex,
                   on=(Document.id == DocumentIndex.rowid))
               .where(
                   (Document.timestamp >= cutoff) &
                   DocumentIndex.match('python sqlite'))
               .order_by(DocumentIndex.bm25()))

.. warning::
   All SQL queries on ``FTSModel`` classes will be full-table scans
   **except** full-text searches and ``rowid`` lookups.

.. _sqlite-fts4-external-content:

.. topic:: External Content

   If the primary source of the content you are indexing exists in a separate
   table, you can save some disk space by instructing SQLite to not store an
   additional copy of the search index content.

   To accomplish this, you can specify a table using the ``content`` option.
   The `FTS4 documentation <https://www.sqlite.org/fts3.html#the_content_option_>`_
   and `FTS5 documentation <https://www.sqlite.org/fts5.html#external_content_and_contentless_tables>`_
   have more information.

   Here is a short example illustrating how to implement this with peewee:

   .. code-block:: python

      class Blog(Model):
          title = TextField()
          pub_date = DateTimeField(default=datetime.datetime.now)
          content = TextField()  # We want to search this.

          class Meta:
              database = db

      class BlogIndex(FTSModel):  # or FTS5Model.
          content = SearchField()

          class Meta:
              database = db
              options = {
                  'content': Blog,  # Data source.
                  'content_rowid': Blog.id,  # FTS5 only.
              }

      db.create_tables([Blog, BlogIndex])

      # Now, we can manage content in the BlogIndex. To populate the
      # search index:
      BlogIndex.rebuild()

      # Optimize the index.
      BlogIndex.optimize()

   The ``content`` option accepts a :class:`Model` and can reduce the amount of
   storage used by the database at the expense of requiring more care and
   attention to keeping data synchronized.


.. class:: FTSModel()

   Base Model class suitable for working with SQLite FTS3 / FTS4.

   Supports the following options:

   * ``content``: :class:`Model` containing external content, or empty string
     for "contentless"
   * ``prefix``: integer(s). Ex: '2' or '2,3,4'
   * ``tokenize``: simple, porter, unicode61. Ex: 'porter'

   Example:

   .. code-block:: python

      class DocumentIndex(FTSModel):
          title = SearchField()
          body = SearchField()

          class Meta:
              database = db
              options = {
                  'tokenize': 'porter unicode61',
                  'prefix': '3',
              }

   .. classmethod:: match(term)

      :param term: Search term or expression. `FTS syntax documentation <https://www.sqlite.org/fts3.html#full_text_index_queries>`__.

      Generate a SQL expression representing a search for the given term or
      expression in the table. SQLite uses the ``MATCH`` operator to indicate
      a full-text search.

      Example:

      .. code-block:: python

         # Search index for "search phrase" and return results ranked
         # by relevancy using the BM25 algorithm.
         query = (DocumentIndex
                  .select()
                  .where(DocumentIndex.match('search phrase'))
                  .order_by(DocumentIndex.bm25()))

         for result in query:
             print('Result: %s' % result.title)

   .. classmethod:: search(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

      :param term: Search term or expression. `FTS syntax documentation <https://www.sqlite.org/fts3.html#full_text_index_queries>`__.
      :param weights: A list of weights for the columns, ordered with respect
        to the column's position in the table. **Or**, a dictionary keyed by
        the field or field name and mapped to a value.
      :param with_score: Whether the score should be returned as part of
        the ``SELECT`` statement.
      :param str score_alias: Alias to use for the calculated rank score.
        This is the attribute you will use to access the score
        if ``with_score=True``.
      :param bool explicit_ordering: Order using full SQL function to
          calculate rank, as opposed to simply referencing the score alias
          in the ORDER BY clause.

      Shorthand way of searching for a term and sorting results by the
      quality of the match.

      .. note::
         This method uses a simplified algorithm for determining the
         relevance rank of results. For more sophisticated result ranking,
         use the :meth:`~FTSModel.search_bm25` method.

      .. code-block:: python

         # Simple search.
         docs = DocumentIndex.search('search term')
         for result in docs:
             print(result.title)

         # More complete example.
         docs = DocumentIndex.search(
             'search term',
             weights={'title': 2.0, 'content': 1.0},
             with_score=True,
             score_alias='search_score')
         for result in docs:
             print(result.title, result.search_score)

   .. classmethod:: search_bm25(term, weights=None, with_score=False, score_alias='score', explicit_ordering=False)

      :param term: Search term or expression. `FTS syntax documentation <https://www.sqlite.org/fts3.html#full_text_index_queries>`__.
      :param weights: A list of weights for the columns, ordered with respect
        to the column's position in the table. **Or**, a dictionary keyed by
        the field or field name and mapped to a value.
      :param with_score: Whether the score should be returned as part of
        the ``SELECT`` statement.
      :param str score_alias: Alias to use for the calculated rank score.
        This is the attribute you will use to access the score
        if ``with_score=True``.
      :param bool explicit_ordering: Order using full SQL function to
          calculate rank, as opposed to simply referencing the score alias
          in the ORDER BY clause.

      Shorthand way of searching for a term and sorting results by the
      quality of the match using the BM25 algorithm.

      .. attention::
         The BM25 ranking algorithm is only available for FTS4. If you are
         using FTS3, use the :meth:`~FTSModel.search` method instead.

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

      The ``rank`` function accepts optional parameters that allow you to
      specify weights for the various columns. If no weights are specified,
      all columns are considered of equal importance.

      .. note::
         The algorithm used by :meth:`~FTSModel.rank` is simple and
         relatively quick. For more sophisticated result ranking, use:

         * :meth:`~FTSModel.bm25`
         * :meth:`~FTSModel.bm25f`
         * :meth:`~FTSModel.lucene`

      .. code-block:: python

         query = (DocumentIndex
                  .select(
                      DocumentIndex,
                      DocumentIndex.rank().alias('score'))
                  .where(DocumentIndex.match('search phrase'))
                  .order_by(DocumentIndex.rank()))

         for search_result in query:
             print(search_result.title, search_result.score)

   .. classmethod:: bm25(col1_weight, col2_weight...coln_weight)

      :param float col_weight: (Optional) weight to give to the *ith* column
          of the model. By default all columns have a weight of ``1.0``.

      Generate an expression that will calculate and return the quality of
      the search match using the `BM25 algorithm <https://en.wikipedia.org/wiki/Okapi_BM25>`_.
      This value can be used to sort the search results.

      Like :meth:`~FTSModel.rank`, ``bm25`` function accepts optional
      parameters that allow you to specify weights for the various columns.
      If no weights are specified, all columns are considered of equal
      importance.

      .. attention::
         The BM25 result ranking algorithm requires FTS4. If you are using
         FTS3, use :meth:`~FTSModel.rank` instead.

      .. code-block:: python

         query = (DocumentIndex
                  .select(
                      DocumentIndex,
                      DocumentIndex.bm25().alias('score'))
                  .where(DocumentIndex.match('search phrase'))
                  .order_by(DocumentIndex.bm25()))

         for search_result in query:
             print(search_result.title, search_result.score)

      .. note::
         The above code example is equivalent to calling the
         :meth:`~FTSModel.search_bm25` method:

          .. code-block:: python

             query = DocumentIndex.search_bm25('search phrase', with_score=True)
             for search_result in query:
                 print(search_result.title, search_result.score)

   .. classmethod:: bm25f(col1_weight, col2_weight...coln_weight)

      Identical to :meth:`~FTSModel.bm25`, except that it uses the BM25f
      variant of the BM25 ranking algorithm.

   .. classmethod:: lucene(col1_weight, col2_weight...coln_weight)

      Identical to :meth:`~FTSModel.bm25`, except that it uses the Lucene
      search result ranking algorithm.

   .. classmethod:: rebuild()

      Rebuild the search index. Only valid when the ``content`` option
      was specified (content tables).

   .. classmethod:: optimize()

      Optimize the index.

.. _sqlite-fts5:

FTS5 / ``FTS5Model``
^^^^^^^^^^^^^^^^^^^^

FTS5Model enables Peewee applications to store data in an efficient full-text
search index using SQLite `FTS5 <https://www.sqlite.org/fts5.html>`_. FTS5 also
comes with native BM25 result ranking.

FTS5Model caveats:

* All queries **except** ``MATCH`` and ``rowid`` lookup require a full table scan.
* Constraints, foreign-keys, and indexes are not supported. All columns **must**
  be instances of :class:`SearchField`.
* FTS5Model ``rowid`` primary key may be declared using :class:`RowIDField`.
  Lookups on the ``rowid`` are very efficient.

.. tip::
   Because of the lack of secondary indexes, it usually makes sense to treat
   the ``FTS5Model.rowid`` primary key as a foreign-key to a row in a normal
   SQLite table.

Example:

.. code-block:: python

   from peewee import *
   from playhouse.sqlite_ext import FTS5Model, SearchField

   db = SqliteDatabase('app.db')

   class Document(Model):
       # Canonical source of data, stored in a normal table.
       author = ForeignKeyField(User, backref='documents')
       title = TextField(null=False, unique=True)
       content = TextField(null=False)
       timestamp = DateTimeField()

       class Meta:
           database = db

   class DocumentIndex(FTS5Model):
       # Full-text search index.
       rowid = RowIDField()
       title = SearchField()
       content = SearchField()
       author = SearchField(unindexed=True)

       class Meta:
           database = db
           # Use the porter stemming algorithm and unicode tokenizers,
           # and optimize prefix matches of 3 or 4 characters.
           options = {'tokenize': 'porter unicode61', 'prefix': [3, 4]}

   # Check that FTS5 is available:
   if not DocumentIndex.fts5_installed():
       raise RuntimeError('FTS5 is not available in this SQLite build.')

Store data by inserting it into the FTS5 table:

.. code-block:: python

   # Store a document in the index:
   DocumentIndex.create(
       rowid=document.id,  # Set rowid to match Document's id.
       title=document.title,
       content=document.content,
       author=document.author.get_full_name())

   # Equivalent:
   (DocumentIndex
    .insert({
        'rowid': document.id,
        'title': document.title,
        'content': document.content,
        'author': document.author.get_full_name()})
    .execute())

:class:`FTS5Model` provides several shortcuts for full-text search queries:

.. code-block:: python

   # Simple search (BM25, ordered by relevance):
   results = DocumentIndex.search('python sqlite')

   # With score and per-column weighting:
   results = DocumentIndex.search(
       'python sqlite',
       weights={'title': 2.0, 'content': 1.0},
       with_score=True,
       score_alias='relevance')

   for r in results:
       print(r.title, r.relevance)

   # Highlight matches in the title:
   for r in (DocumentIndex.search('python')
             .select(DocumentIndex.title.highlight('[', ']').alias('hi'))):
       print(r.hi)  # e.g. "Learn [python] the hard way"

.. tip::
   An important method of searching relies on the ``rowid`` of the indexed
   data matching the document's canonical id. Using this technique we can
   apply additional filters and retrieve the matching ``Document`` objects
   efficiently:

   .. code-block:: python

      # Search and ensure we only retrieve articles from the last 30 days.
      cutoff = datetime.datetime.now() - datetime.timedelta(days=30)

      query = (Document
               .select()
               .join(
                   DocumentIndex,
                   on=(Document.id == DocumentIndex.rowid))
               .where(
                   (Document.timestamp >= cutoff) &
                   DocumentIndex.match('python sqlite'))
               .order_by(DocumentIndex.rank()))

If the primary source of the content you are indexing exists in a separate
table, you can save some disk space by instructing SQLite to not store an
additional copy of the search index content. See :ref:`External Content
<sqlite-fts4-external-content>` for implementation details. The `FTS5 documentation <https://www.sqlite.org/fts5.html#external_content_and_contentless_tables>`_
has more information.

.. class:: FTS5Model()

   Inherits all :class:`FTSModel` methods plus.

   Supports the following options:

   * ``content``: :class:`Model` containing external content, or empty string
     for "contentless"
   * ``content_rowid``: :class:`Field` (external content primary key)
   * ``prefix``: integer(s). Ex: '2' or ``[2, 3]``
   * ``tokenize``: simple, porter, unicode61. Ex: 'porter unicode61'

   Example:

   .. code-block:: python

      class DocumentIndex(FTS5Model):
          title = SearchField()
          body = SearchField()

          class Meta:
              database = db
              options = {
                  'tokenize': 'porter unicode61',
                  'prefix': '3',
              }

   .. classmethod:: fts5_installed()

      Return ``True`` if FTS5 is available.

   .. classmethod:: match(term)

      :param term: Search term or expression. `FTS5 syntax documentation <https://sqlite.org/fts5.html#full_text_query_syntax>`__.

      Generate a SQL expression representing a search for the given term or
      expression in the table. SQLite uses the ``MATCH`` operator to indicate
      a full-text search.

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

   .. classmethod:: search(term, weights=None, with_score=False, score_alias='score')

      :param term: Search term or expression. `FTS5 syntax documentation <https://sqlite.org/fts5.html#full_text_query_syntax>`__.
      :param weights: A list of weights for the columns, ordered with respect
        to the column's position in the table. **Or**, a dictionary keyed by
        the field or field name and mapped to a value.
      :param with_score: Whether the score should be returned as part of
        the ``SELECT`` statement.
      :param str score_alias: Alias to use for the calculated rank score.
        This is the attribute you will use to access the score
        if ``with_score=True``.
      :param bool explicit_ordering: Order using full SQL function to
          calculate rank, as opposed to simply referencing the score alias
          in the ORDER BY clause.

      Shorthand way of searching for a term and sorting results by the
      quality of the match. The ``FTS5`` extension provides a built-in
      implementation of the BM25 algorithm, which is used to rank the results
      by relevance.

      .. code-block:: python

          # Simple search.
          docs = DocumentIndex.search('search term')
          for result in docs:
              print(result.title)

          # More complete example.
          docs = DocumentIndex.search(
              'search term',
              weights={'title': 2.0, 'content': 1.0},
              with_score=True,
              score_alias='search_score')
          for result in docs:
              print(result.title, result.search_score)

   .. classmethod:: search_bm25(term, weights=None, with_score=False, score_alias='score')

      With FTS5, :meth:`~FTS5Model.search_bm25` is identical to the
      :meth:`~FTS5Model.search` method.

   .. classmethod:: rank(col1_weight, col2_weight...coln_weight)

      :param float col_weight: (Optional) weight to give to the *ith* column
          of the model. By default all columns have a weight of ``1.0``.

      Generate an expression that will calculate and return the quality of
      the search match using the `BM25 algorithm <https://en.wikipedia.org/wiki/Okapi_BM25>`_.
      This value can be used to sort the search results.

      The :meth:`~FTS5Model.rank` function accepts optional parameters
      that allow you to specify weights for the various columns.  If no
      weights are specified, all columns are considered of equal importance.

      .. code-block:: python

          query = (DocumentIndex
                   .select(
                       DocumentIndex,
                       DocumentIndex.rank().alias('score'))
                   .where(DocumentIndex.match('search phrase'))
                   .order_by(DocumentIndex.rank()))

          for search_result in query:
              print(search_result.title, search_result.score)

      .. note::
          The above code example is equivalent to calling the
          :meth:`~FTS5Model.search` method:

          .. code-block:: python

              query = DocumentIndex.search('search phrase', with_score=True)
              for search_result in query:
                  print(search_result.title, search_result.score)

   .. classmethod:: bm25(col1_weight, col2_weight...coln_weight)

      Because FTS5 provides built-in support for BM25, this method is identical
      to :meth:`~FTS5Model.rank` method.

   .. classmethod:: VocabModel(table_type='row'|'col'|'instance', table_name=None)

      :param str table_type: Either 'row', 'col' or 'instance'.
      :param table_name: Name for the vocab table. If not specified, will be
          "fts5tablename_v".

      Generate a model class suitable for accessing the `vocab table <http://sqlite.org/fts5.html#the_fts5vocab_virtual_table_module>`_
      corresponding to FTS5 search index.

   .. classmethod:: rebuild()

      Rebuild the search index. Only valid when the ``content`` option
      was specified (content tables).

   .. classmethod:: optimize()

      Optimize the index.


.. _sqlite-udf:

User-Defined Function Collection
---------------------------------

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

   The time is not adjusted in any way, the timezone is simply removed.

.. function:: humandelta(nseconds, glue=', ')

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

.. function:: date_series(start, stop, step_seconds=86400)

   :param datetime start: Start datetime
   :param datetime stop: Stop datetime
   :param int step_seconds: Number of seconds comprising a step.

   *Table-value function*: returns rows consisting of the date/+time values
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

.. function:: regex_search(regex, search_string)

   :param str regex: Regular expression
   :param str search_string: String to search for instances of regex.

   *Table-value function*: searches a string for substrings that match
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
