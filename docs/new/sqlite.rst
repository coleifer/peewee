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

There are also additional database classes that work with alternative SQLite
drivers:

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

SQLite allows run-time configuration of a number of parameters through
``PRAGMA`` statements (`SQLite documentation <https://www.sqlite.org/pragma.html>`_).
These statements are typically run when a new database connection is created.
To run one or more ``PRAGMA`` statements against new connections, you can
specify them as a dictionary or a list of 2-tuples containing the pragma name
and value:

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
   Pragmas set using the :py:meth:`~SqliteDatabase.pragma` method do not
   get re-applied when a new connection opens. To configure a pragma to be
   run whenever a connection is opened, specify ``permanent=True``.

   .. code-block:: python

      db.pragma('foreign_keys', 1, permanent=True)

.. seealso::
   SQLite PRAGMA documentation: https://sqlite.org/pragma.html

.. _sqlite-user-functions:

User-defined functions
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
                fn.mysum(Employee.salary).over(partition_by=[Employee.department]))
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

.. _sqlite-locking:

Locking mode for transactions
-----------------------------

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

.. danger::
   Do not alter the ``isolation_level`` property of the ``sqlite3.Connection``
   object. Peewee requires the ``sqlite3`` driver be in autocommit-mode, which
   is handled automatically by :class:`SqliteDatabase`.


.. _cysqlite-ext:

CySqlite
^^^^^^^^

:class:`CySqliteDatabase` uses the `cysqlite <https://cysqlite.readthedocs.io>`_
driver, a high-performance C-extension alternative to the standard library
``sqlite3`` module.

Installation:

.. code-block:: shell

   pip install cysqlite

Usage:

.. code-block:: python

   from playhouse.cysqlite_ext import CySqliteDatabase

   db = CySqliteDatabase('my_app.db', pragmas={
       'cache_size': -1024 * 64,
       'journal_mode': 'wal',
       'foreign_keys': 1,
   })

Extra capabilities compared to :class:`SqliteDatabase`:

.. py:class:: CySqliteDatabase(database, **kwargs)

   .. py:method:: table_function(name)

      Decorator to register a :py:class:`TableFunction` class as a
      user-defined table-valued function. See the
      `cysqlite documentation <https://cysqlite.readthedocs.io>`_ for the
      full ``TableFunction`` interface.

      .. code-block:: python

          from cysqlite import TableFunction

          @db.table_function('series')
          class Series(TableFunction):
              columns = ['value']
              params = ['start', 'stop', 'step']

              def initialize(self, start=0, stop=None, step=1):
                  self.current = start
                  self.stop = stop or float('Inf')
                  self.step = step

              def iterate(self, idx):
                  if self.current > self.stop:
                      raise StopIteration
                  ret, self.current = self.current, self.current + self.step
                  return (ret,)

          cursor = db.execute_sql('SELECT * FROM series(?, ?, ?)', (0, 5, 2))
          # Returns rows: (0,), (2,), (4,)

   .. py:method:: on_commit(fn)

      Register a callback that is invoked when a transaction is committed.

   .. py:method:: on_rollback(fn)

      Register a callback that is invoked when a transaction is rolled back.

   .. py:method:: on_update(fn)

      Register a callback invoked when a row is updated, inserted, or deleted.

   .. py:method:: backup(dest_db)

      Online backup of this database to ``dest_db``.

   .. py:method:: backup_to_file(filename)

      Online backup to a file at ``filename``.

   .. py:method:: blob_open(table, column, rowid, read_only=False)

      Open a :py:class:`ZeroBlobField` BLOB for incremental I/O.

.. _apsw:

APSW
^^^^

`APSW <https://rogerbinns.github.io/apsw/>`_ is a thin C wrapper over
SQLite's C API that exposes nearly every SQLite feature including virtual
tables, virtual filesystems, and BLOB I/O. Connections can be shared across
threads without additional locking.

Install: ``pip install apsw``

.. code-block:: python

   from playhouse.apsw_ext import APSWDatabase

   db = APSWDatabase('my_app.db')

   class BaseModel(Model):
       class Meta:
           database = db

.. warning::
   Use the ``Field`` subclasses from ``playhouse.apsw_ext`` rather than those
   from ``peewee``. For example, import ``DateTimeField`` from ``apsw_ext``,
   not from ``peewee``, to ensure correct type adaption.

.. py:class:: APSWDatabase(database, **connect_kwargs)

   Subclass of :py:class:`SqliteExtDatabase` using the APSW driver.

   .. py:method:: register_module(mod_name, mod_inst)

      Register a virtual table module globally. See the `APSW virtual table
      documentation <https://rogerbinns.github.io/apsw/vtable.html>`_.

   .. py:method:: unregister_module(mod_name)

      Unregister a previously registered module.


.. _sqlcipher:

SQLCipher (Encrypted SQLite)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

`SQLCipher <https://www.zetetic.net/sqlcipher/>`_ is an encrypted wrapper
around SQLite. Peewee exposes it through :py:class:`SqlCipherDatabase`, which
is API-identical to :py:class:`SqliteDatabase` except for its constructor.

Install: ``pip install sqlcipher3``

.. warning::
   This extension has not been formally audited for cryptographic correctness.
   The underlying ``sqlcipher3`` and ``sqlcipher`` libraries are widely deployed,
   but use this in security-sensitive applications with appropriate care.

.. py:class:: SqlCipherDatabase(database, passphrase, **kwargs)

   :param str database: Path to the encrypted database file.
   :param str passphrase: Encryption passphrase (minimum 8 characters;
       enforce stronger requirements in your application).

   If the database file does not exist, it is created and encrypted with a
   key derived from ``passphrase``. If it does exist, ``passphrase`` must
   match the one used when the file was created.

   .. py:method:: rekey(passphrase)

       Change the encryption passphrase for the open database.

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
           if 'encrypted' in str(exc):
               print('Wrong passphrase.')
               db.init(None)
           else:
               raise

Pragma configuration (e.g. increasing PBKDF2 iterations):

.. code-block:: python

   db = SqlCipherDatabase('my_app.db',
                          passphrase='s3cr3t',
                          pragmas={'kdf_iter': 1_000_000})


.. _sqliteq:

SqliteQueueDatabase
-------------------

:py:class:`SqliteQueueDatabase` serializes all write queries through a
single long-lived connection on a dedicated background thread. This allows
multiple application threads to write to a SQLite database concurrently
without conflict or timeout errors.

.. code-block:: python

   from playhouse.sqliteq import SqliteQueueDatabase

   db = SqliteQueueDatabase(
       'my_app.db',
       use_gevent=False,    # Use stdlib threading (default).
       autostart=True,      # Start the writer thread immediately.
       queue_max_size=64,   # Max pending writes before blocking.
       results_timeout=5.0, # Seconds to wait for a write to complete.
   )

If you set ``autostart=False``, start the writer thread explicitly:

.. code-block:: python

   db.start()

Stop the writer thread on application shutdown (waits for pending writes):

.. code-block:: python

   import atexit

   @atexit.register
   def _stop():
       db.stop()

Read queries work as normal — open and close the connection per-request as you
would with any other database. Only writes are funneled through the queue.

.. warning::
   **Transactions are not supported.** Because writes from different threads
   are interleaved, there is no way to guarantee that the statements in a
   transaction from one thread execute atomically without statements from
   another thread appearing between them. The ``atomic()`` and
   ``transaction()`` methods raise an exception if called.

   If you need to temporarily bypass the queue and write directly (for
   example, during a batch import), use :py:meth:`~SqliteQueueDatabase.pause`
   and :py:meth:`~SqliteQueueDatabase.unpause`.

.. py:class:: SqliteQueueDatabase(database, use_gevent=False, autostart=True, queue_max_size=None, results_timeout=None, **kwargs)

   .. py:method:: start()

      Start the background writer thread.

   .. py:method:: stop()

      Signal the writer thread to stop. Blocks until all pending writes
      are flushed.

   .. py:method:: is_stopped()

      Return ``True`` if the writer thread is not running.

   .. py:method:: pause()

      Block until the writer thread finishes its current work, then
      disconnect it. The calling thread takes over direct database access.
      Must be followed by a call to :py:meth:`~SqliteQueueDatabase.unpause`.

   .. py:method:: unpause()

      Resume the writer thread and reconnect the queue.

.. _sqlite-fields:

SQLite-Specific Fields
----------------------

These field classes live in ``playhouse.sqlite_ext``.

.. py:class:: RowIDField()

   Primary-key field mapped to SQLite's implicit ``rowid`` column. Useful
   for explicit ``rowid`` access without a separate integer primary key.

   .. code-block:: python

       class Note(Model):
           rowid = RowIDField()
           content = TextField()
           timestamp = TimestampField()

.. py:class:: AutoIncrementField()

   Integer primary key that uses SQLite's ``AUTOINCREMENT`` keyword,
   guaranteeing the primary key is always strictly increasing even after
   deletions. Has a small performance cost versus the default
   :py:class:`PrimaryKeyField`.

   See the `SQLite AUTOINCREMENT documentation
   <https://sqlite.org/autoinc.html>`_ for details.

.. py:class:: ISODateTimeField()

   Subclass of :py:class:`DateTimeField` that preserves UTC offset
   information for timezone-aware datetimes when storing to SQLite's
   text-based datetime representation.


.. _sqlite-json:

SQLite JSON (json1 extension)
------------------------------

SQLite 3.9+ includes the ``json1`` extension, exposed by
:py:class:`JSONField` in ``playhouse.sqlite_ext``.

.. py:class:: JSONField(json_dumps=None, json_loads=None, **kwargs)

   :param json_dumps: Custom JSON serializer. Defaults to ``json.dumps``.
   :param json_loads: Custom JSON deserializer. Defaults to ``json.loads``.

   Stores and retrieves JSON data transparently. Python dicts and lists are
   automatically serialized on write and deserialized on read.

   Access and modify nested values using dictionary/list indexing:

   .. code-block:: python

       class Config(Model):
           data = JSONField()

       cfg = Config.create(data={'timeout': 30, 'retry': {'max': 5}})

       # Filter by nested value:
       Config.select().where(Config.data['retry']['max'] > 3)

       # In-place update (preserves other keys):
       Config.update(data=Config.data.update({'timeout': 60})).execute()

       # Remove a key atomically:
       Config.update(data=Config.data.update({'retry': None})).execute()

       # Set a specific path:
       Config.update(data=Config.data['timeout'].set(120)).execute()

   .. py:method:: __getitem__(item)

      Return a :py:class:`JSONPath` for the given key or array index. Paths
      can be chained: ``field['a']['b'][0]``.

   .. py:method:: extract(*paths)

      Extract one or more JSON path values. Returns a list when multiple
      paths are given.

   .. py:method:: set(value, as_json=None)

      Set the entire field value. Uses ``json_set()``.

   .. py:method:: update(data)

      Merge ``data`` into the stored JSON using RFC-7396 MergePatch. Setting
      a key to ``None`` removes it. Arrays are treated as atomic (cannot be
      partially updated with this method).

   .. py:method:: remove()

      Remove the stored value.

   .. py:method:: json_type()

      Return a string describing the JSON type of the stored value:
      ``'object'``, ``'array'``, ``'integer'``, ``'real'``, ``'true'``,
      ``'false'``, ``'text'``, ``'null'``, or ``NULL`` (path not found).

   .. py:method:: length()

      Return the length of the stored array.

   .. py:method:: children()

      Table-valued function (``json_each``) that yields the direct children
      of the stored JSON object or array as rows with the attributes
      ``key``, ``value``, ``type``, ``atom``, ``id``, ``parent``,
      ``fullkey``, and ``path``.

   .. py:method:: tree()

      Table-valued function (``json_tree``) that recursively yields all
      descendants of the stored JSON value. Same row attributes as
      :py:meth:`~JSONField.children`.

.. py:class:: JSONBField(json_dumps=None, json_loads=None, **kwargs)

   Like :py:class:`JSONField` but stores data in the binary ``jsonb`` format
   (SQLite 3.45.0+). When reading raw column values the data is in its
   encoded binary form; use the :py:meth:`~JSONBField.json` method to decode:

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

Peewee supports both FTS4 (legacy, widely available) and FTS5 (recommended,
SQLite 3.7.4+) full-text search extensions.

The general pattern is:

1. Define a :py:class:`FTSModel` or :py:class:`FTS5Model` subclass with
   :py:class:`SearchField` columns.
2. When a row is created or updated in the source table, insert or update
   the corresponding row in the search index.
3. Query the index using :py:meth:`~FTSModel.match` and rank results with
   :py:meth:`~FTSModel.bm25` (or :py:meth:`~FTSModel.rank` for FTS4).

.. py:class:: SearchField(unindexed=False, column_name=None)

   Column type for full-text search virtual tables. Raises an exception if
   constraints (``null=False``, ``unique=True``, etc.) are specified, since
   FTS tables do not support them.

   Pass ``unindexed=True`` to store metadata alongside the search index
   without indexing it:

   .. code-block:: python

       class DocumentIndex(FTSModel):
           title    = SearchField()
           content  = SearchField()
           timestamp = SearchField(unindexed=True)  # Stored but not searched.

   .. py:method:: match(term)

      Generate a ``MATCH`` expression that restricts full-text search to
      this column only (as opposed to :py:meth:`FTSModel.match`, which
      searches all indexed columns).

   .. py:method:: highlight(left, right)

      FTS5 only. Wrap matched terms with ``left`` and ``right`` strings
      (e.g. ``'<b>'`` / ``'</b>'``).

   .. py:method:: snippet(left, right, over_length='...', max_tokens=16)

      FTS5 only. Return a short extract of the column value with matched
      terms highlighted. ``max_tokens`` must be 1–64.


FTS4 / ``FTSModel``
^^^^^^^^^^^^^^^^^^^

Use FTS4 when you need compatibility with older SQLite versions or are
working on an existing FTS4 index.

.. code-block:: python

   from playhouse.sqlite_ext import FTSModel, SearchField, RowIDField

   class Document(Model):
       title   = TextField()
       content = TextField()
       class Meta:
           database = db

   class DocumentIndex(FTSModel):
       rowid   = RowIDField()  # Points to Document.id.
       title   = SearchField()
       content = SearchField()

       class Meta:
           database = db
           options = {'tokenize': 'porter'}  # Porter stemming.

   # Populate the index when saving a document:
   def index_document(doc):
       DocumentIndex.insert({
           DocumentIndex.rowid:    doc.id,
           DocumentIndex.title:    doc.title,
           DocumentIndex.content:  doc.content,
       }).execute()

   # Search, joined back to the source table for full data:
   def search(phrase):
       return (Document
               .select()
               .join(DocumentIndex, on=(Document.id == DocumentIndex.rowid))
               .where(DocumentIndex.match(phrase))
               .order_by(DocumentIndex.bm25()))

.. warning::
   All queries on an ``FTSModel`` perform a full-table scan **except**
   ``MATCH`` searches and ``rowid`` lookups.

.. py:class:: FTSModel()

   .. py:classmethod:: match(term)

      Return a ``MATCH`` expression for use in ``WHERE``.

   .. py:classmethod:: search(term, weights=None, with_score=False, score_alias='score')

      Shorthand that generates a query with ``MATCH`` and ``ORDER BY`` rank
      (using BM25). Pass ``with_score=True`` to include the score in the
      SELECT.

   .. py:classmethod:: search_bm25(term, weights=None, with_score=False, score_alias='score')

      Like :py:meth:`~FTSModel.search` but always uses the BM25 ranking
      algorithm. Requires FTS4.

   .. py:classmethod:: rank(*col_weights)

      Return an expression representing the relevance score. Higher is better.

   .. py:classmethod:: bm25(*col_weights)

      Return an expression representing the BM25 relevance score. Requires FTS4.
      Optional ``col_weights`` arguments provide per-column importance weights.

   .. py:classmethod:: rebuild()

      Rebuild the search index. Only valid when the ``content`` option
      was specified (content tables).

   .. py:classmethod:: optimize()

      Optimize the index.

**Content tables.** You can save disk space by pointing the FTS index at a
source table instead of duplicating its data:

.. code-block:: python

   class Blog(Model):
       content = TextField()
       class Meta:
           database = db

   class BlogIndex(FTSModel):
       content = SearchField()
       class Meta:
           database = db
           options = {'content': Blog.content}  # Use Blog.content as source.

   db.create_tables([Blog, BlogIndex])
   BlogIndex.rebuild()   # Populate from the source table.
   BlogIndex.optimize()  # Merge index segments.


FTS5 / ``FTS5Model``
^^^^^^^^^^^^^^^^^^^^^

FTS5 is the current recommended implementation. It has built-in BM25 and
a cleaner API. All columns must use :py:class:`SearchField`.

.. code-block:: python

   from playhouse.sqlite_ext import FTS5Model, SearchField

   class ArticleIndex(FTS5Model):
       title   = SearchField()
       body    = SearchField()
       author  = SearchField(unindexed=True)

       class Meta:
           database = db

   # Check that FTS5 is available:
   if not ArticleIndex.fts5_installed():
       raise RuntimeError('FTS5 is not available in this SQLite build.')

   # Simple search (BM25, ordered by relevance):
   results = ArticleIndex.search('python asyncio')

   # With score and per-column weighting:
   results = ArticleIndex.search(
       'python asyncio',
       weights={'title': 2.0, 'body': 1.0},
       with_score=True,
       score_alias='relevance')

   for r in results:
       print(r.title, r.relevance)

   # Highlight matches in the title:
   for r in (ArticleIndex.search('python')
             .select(ArticleIndex.title.highlight('[', ']').alias('hi'))):
       print(r.hi)  # e.g. "Learn [python] the hard way"

.. py:class:: FTS5Model()

   Inherits all :py:class:`FTSModel` methods plus:

   .. py:classmethod:: fts5_installed()

      Return ``True`` if FTS5 is available.

   .. py:classmethod:: VocabModel(table_type='row'|'col'|'instance', table_name=None)

      Generate a model for the FTS5 vocabulary table, which exposes
      per-term token statistics.


.. _sqlite-udf:

SQLite User-Defined Functions
-------------------------------

The ``playhouse.sqlite_udf`` module ships a library of Python-implemented
scalar functions, aggregate functions, and (when using CySqlite)
table-valued functions grouped into named collections.

.. code-block:: python

   from playhouse.sqlite_udf import register_all, register_groups

   db = SqliteExtDatabase('my_app.db')

   register_all(db)                     # Register every function.
   register_groups(db, 'DATE', 'MATH')  # Register selected groups.

   # Register a single function by hand:
   from playhouse.sqlite_udf import gzip, gunzip
   db.register_function(gzip,   'gzip')
   db.register_function(gunzip, 'gunzip')

Once registered, call functions via Peewee's ``fn`` namespace or raw SQL:

.. code-block:: python

   # Find most common URL hostnames.
   query = (Link
            .select(fn.hostname(Link.url).alias('host'), fn.COUNT(Link.id))
            .group_by(fn.hostname(Link.url))
            .order_by(fn.COUNT(Link.id).desc())
            .tuples())

Available collections and functions:

**CONTROL_FLOW**

- ``if_then_else(cond, truthy, falsey=None)`` — ternary expression.

**DATE**

- ``strip_tz(date_str)`` — remove timezone offset from a datetime string
  (does not adjust the time).
- ``humandelta(nseconds, glue=', ')`` (a) — human-readable timedelta,
  e.g. ``86471`` → ``"1 day, 1 minute, 11 seconds"``.
- ``mintdiff(datetime_value)`` (a) — minimum difference between any two
  values in a set.
- ``avgtdiff(datetime_value)`` (a) — average difference between consecutive
  values.
- ``duration(datetime_value)`` (a) — duration from smallest to largest value
  in seconds.
- ``date_series(start, stop, step_seconds=86400)`` (t) — table-valued
  function yielding dates/datetimes between ``start`` and ``stop``.

**FILE**

- ``file_ext(filename)`` — extract file extension including the leading dot.
- ``file_read(filename)`` — return the contents of a file.

**HELPER**

- ``gzip(data, compression=9)`` — compress bytes.
- ``gunzip(data)`` — decompress bytes.
- ``hostname(url)`` — extract hostname from a URL.
- ``toggle(key)`` / ``clear_toggles()`` — in-memory boolean toggle per key.
- ``setting(key, value=None)`` / ``clear_settings()`` — in-memory key/value
  settings store.

**MATH**

- ``randomrange(start, stop=None, step=None)`` — random integer in range.
- ``gauss_distribution(mean, sigma)`` — Gaussian random value.
- ``sqrt(n)`` — square root.
- ``tonumber(s)`` — parse a string to integer or float, or NULL.
- ``mode(val)`` (a) — most common value in a set.
- ``minrange(val)`` (a) — minimum difference between any two numbers.
- ``avgrange(val)`` (a) — average distance between consecutive numbers.
- ``range(val)`` (a) — difference between smallest and largest value.
- ``median(val)`` (a) — middle value (requires ``_sqlite_udf`` extension).

**STRING**

- ``substr_count(haystack, needle)`` — count occurrences of a substring.
- ``strip_chars(haystack, chars)`` — strip characters from both ends.
- ``damerau_levenshtein_dist(s1, s2)`` — edit distance with transpositions
  (requires ``_sqlite_udf``).
- ``levenshtein_dist(s1, s2)`` — edit distance (requires ``_sqlite_udf``).
- ``str_dist(s1, s2)`` — edit distance via ``SequenceMatcher``
  (requires ``_sqlite_udf``).
- ``regex_search(regex, string)`` (t) — table-valued function returning
  all regex matches in a string (requires CySqlite).

*(a) = aggregate function, (t) = table-valued function*
