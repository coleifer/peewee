.. _api:

API Reference
=============

This document specifies Peewee's APIs.

.. contents:: On this page
   :local:
   :depth: 1

Database
--------

.. class:: Database(database, thread_safe=True, field_types=None, operations=None, autoconnect=True, **kwargs)

   :param str database: Database name or filename for SQLite (or ``None`` to
       :ref:`defer initialization <initializing-database>`, in which case
       you must call :meth:`Database.init`, specifying the database name).
   :param bool thread_safe: Whether to store connection state in a
       thread-local.
   :param dict field_types: A mapping of additional field types to support.
   :param dict operations: A mapping of additional operations to support.
   :param bool autoconnect: Automatically connect to database if attempting to
       execute a query on a closed database.
   :param kwargs: Arbitrary keyword arguments that will be passed to the
       database driver when a connection is created, for example ``password``,
       ``host``, etc.

   The :class:`Database` is responsible for:

   * Executing queries
   * Managing connections
   * Transactions
   * Introspection

   .. note::
      The database can be instantiated with ``None`` as the database name if
      the database is not known until run-time. In this way you can create a
      database instance and then configure it elsewhere when the settings are
      known. This is called :ref:`deferred initialization <initializing-database>`.

   Examples:

   .. code-block:: python

      # Sqlite database using WAL-mode and 64MB page-cache.
      db = SqliteDatabase('app.db', pragmas={
          'journal_mode': 'wal',
          'cache_size': -64000})

      # Postgresql database on remote host.
      db = PostgresqlDatabase(
          'my_app',
          user='postgres',
          host='10.8.0.3',
          password='secret')

   Deferred initialization example:

   .. code-block:: python

      db = PostgresqlDatabase(None)

      class BaseModel(Model):
          class Meta:
              database = db

      # Read database connection info from env, for example:
      db_name = os.environ['DATABASE']
      db_host = os.environ['PGHOST']

      # Initialize database.
      db.init(db_name, host=db_host, user='postgres')

   .. attribute:: param = '?'

      String used as parameter placeholder in SQL queries.

   .. attribute:: quote = '"'

      Type of quotation-mark to use to denote entities such as tables or
      columns.

   .. method:: init(database, **kwargs)

      :param str database: Database name or filename for SQLite.
      :param kwargs: Arbitrary keyword arguments that will be passed to the
          database driver when a connection is created, for example
          ``password``, ``host``, etc.

      Initialize a *deferred* database. See :ref:`initializing-database`
      for more info.

   .. method:: connect(reuse_if_open=False)

      :param bool reuse_if_open: Do not raise an exception if a connection is
          already opened.
      :return: whether a new connection was opened.
      :rtype: bool
      :raises: ``OperationalError`` if connection already open and
          ``reuse_if_open`` is not set to ``True``.

      Open a connection to the database.

      .. code-block:: python

         db.connect()

         # Or:
         db.connect(reuse_if_open=True)

   .. method:: close()

      :return: Whether the connection was closed. If the database was already
          closed, this returns ``False``.
      :rtype: bool

      Close the connection to the database.

      .. code-block:: python

         if not db.is_closed():
             db.close()

   .. method:: is_closed()

      :return: return ``True`` if database is closed, ``False`` if open.
      :rtype: bool

   .. method:: connection()

      Return the DB-API driver connection. If a connection is not open, one
      will be opened.

      .. code-block:: python

         db = SqliteDatabase(':memory:')

         # Get the sqlite3.Connection() instance.
         conn = db.connection()

   .. method:: __enter__()
   .. method:: __exit__(exc_type, exc_val, exc_tb)
   .. method:: __call__()

      The database object can be used as a context manager or decorator.

      1. Connection opens when context manager / decorated function is entered.
      2. Peewee begins a transaction.
      3. Control is passed to user for duration of block.
      4. Peewee commits transaction if block exits cleanly, otherwise issues a
         rollback.
      5. Peewee closes the connection.
      6. Any unhandled exception is raised.

      .. code-block:: python

         with db:
             User.create(username='charlie')
             # Transaction is committed when the block exits normally,
             # rolled back if an exception is raised.

      Decorator:

      .. code-block:: python

         @db
         def demo():
             print('closed?', db.is_closed())

         demo()  # "closed? False"
         db.is_closed()  # True

   .. method:: connection_context()

      Create a context-manager or decorator that will hold open a connection
      for the duration of the wrapped block.

      Example:

      .. code-block:: python

         with db.connection_context():
             # Connection is open; no implicit transaction.
             results = User.select()

      Decorator:

      .. code-block:: python

         @db.connection_context()
         def load_fixtures():
             db.create_tables([User, Tweet])
             import_data()
                        database.create_tables(APP_MODELS)

   .. method:: cursor(named_cursor=None)

      :param named_cursor: Reserved for internal use.

      Return a DB-API ``cursor`` object on the current connection. If a
      connection is not open, one will be opened.

   .. method:: execute_sql(sql, params=None)

      :param str sql: SQL string to execute.
      :param tuple params: Parameters for query.
      :return: cursor object.

      Execute a SQL query and return a cursor over the results.

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

   .. method:: execute(query, **context_options)

      :param query: A :class:`Query` instance.
      :param context_options: Arbitrary options to pass to the SQL generator.
      :return: cursor object.

      Execute a SQL query by compiling a ``Query`` instance and executing the
      resulting SQL.

      .. code-block:: python

         query = User.insert({'username': 'Huey'})
         db.execute(query)  # Equivalent to query.execute()

   .. method:: last_insert_id(cursor, query_type=None)

      :param cursor: cursor object.
      :return: primary key of last-inserted row.

   .. method:: rows_affected(cursor)

      :param cursor: cursor object.
      :return: number of rows modified by query.

   .. method:: atomic(...)

      Create a context-manager or decorator which wraps a block of code in a
      transaction (or savepoint).

      Calls to :meth:`~Database.atomic` can be nested.

      Database-specific parameters:

      :class:`PostgresqlDatabase` and :class:`MySQLDatabase` accept an
      ``isolation_level`` parameter. :class:`SqliteDatabase` accepts a
      ``lock_type`` parameter. Refer to :ref:`sqlite-locking` and :ref:`postgres-isolation`
      for discussion.

      :param str isolation_level: Isolation strategy: READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ, SERIALIZABLE
      :param str lock_type: Locking strategy: DEFERRED, IMMEDIATE, EXCLUSIVE.

      Example code::

         with db.atomic() as txn:
             user = User.create(username='charlie')
             with db.atomic():
                 tweet = Tweet.create(user=user, content='Hello')

         # Both rows are committed when block exits normally.

      As a decorator:

      .. code-block:: python

         @db.atomic()
         def create_user_with_tweet(username, content):
             user = User.create(username=username)
             Tweet.create(user=user, content=content)
             return user

      Transactions (and save-points) can be committed or rolled-back within the
      wrapped block. If this occurs, a new transaction or savepoint is begun:

      Example:

      .. code-block:: python

          with db.atomic() as txn:
              User.create(username='mickey')
              txn.commit()  # Changes are saved and a new transaction begins.

              User.create(username='huey')
              txn.rollback()  # "huey" will not be saved.

              User.create(username='zaizee')

          # Print the usernames of all users.
          print([u.username for u in User.select()])

          # Prints ["mickey", "zaizee"]

      If an unhandled exception occurs in the block, the block is rolled-back
      and the exception propagates.

   .. method:: transaction(...)

      Create a context-manager or decorator that runs all queries in the
      wrapped block in a transaction.

      Database-specific parameters:

      :class:`PostgresqlDatabase` and :class:`MySQLDatabase` accept an
      ``isolation_level`` parameter. :class:`SqliteDatabase` accepts a
      ``lock_type`` parameter. Refer to :ref:`sqlite-locking` and :ref:`postgres-isolation`
      for discussion.

      :param str isolation_level: Isolation strategy: READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ, SERIALIZABLE
      :param str lock_type: Locking strategy: DEFERRED, IMMEDIATE, EXCLUSIVE.

      .. code-block:: python

         with db.transaction() as txn:
             User.create(username='mickey')
             txn.commit()         # Commit now; a new transaction begins.
             User.create(username='huey')
             txn.rollback()       # Roll back huey; a new transaction begins.
             User.create(username='zaizee')
         # zaizee is committed when the block exits.

      .. note::
         Transactions can be committed or rolled-back within the wrapped block.
         If this occurs, a new transaction is begun.

      .. warning::
         If you attempt to nest transactions with peewee using the
         :meth:`~Database.transaction` context manager, only the outer-most
         transaction will be used.

         As this may lead to unpredictable behavior, it is recommended that
         you use :meth:`~Database.atomic`.

   .. method:: savepoint()

      Create a context-manager or decorator that runs all queries in the
      wrapped block in a savepoint. Savepoints can be nested arbitrarily, but
      must occur within a transaction.

      .. code-block:: python

         with db.transaction() as txn:
             with db.savepoint() as sp:
                 User.create(username='mickey')

             with db.savepoint() as sp2:
                 User.create(username='zaizee')
                 sp2.rollback()  # "zaizee" is not saved.
                 User.create(username='huey')

         # mickey and huey were created.

      .. note::
         Savepoints can be committed or rolled-back within the wrapped block.
         If this occurs, a new savepoint is begun.

   .. method:: manual_commit()

      Create a context-manager or decorator which disables Peewee's transaction
      management for the wrapped block.

      Example:

      .. code-block:: python

         with db.manual_commit():
             db.begin()  # Begin transaction explicitly.
             try:
                 user.delete_instance(recursive=True)
             except:
                 db.rollback()  # Rollback -- an error occurred.
                 raise
             else:
                 try:
                     db.commit()  # Attempt to commit changes.
                 except:
                     db.rollback()  # Error committing, rollback.
                     raise

      The above code is equivalent to the following:

      .. code-block:: python

         with db.atomic():
             user.delete_instance(recursive=True)

   .. method:: session_start()

      Begin a new transaction (without using a context-manager or decorator).
      This method is useful if you intend to execute a sequence of operations
      inside a transaction, but using a decorator or context-manager would
      not be appropriate.

      .. note::
         It is strongly advised that you use the :meth:`Database.atomic`
         method whenever possible for managing transactions/savepoints. The
         ``atomic`` method correctly manages nesting, uses the appropriate
         construction (e.g., transaction-vs-savepoint), and always cleans up
         after itself.

         The :meth:`~Database.session_start` method should only be used
         if the sequence of operations does not easily lend itself to
         wrapping using either a context-manager or decorator.

      .. warning::
         You must *always* call either :meth:`~Database.session_commit`
         or :meth:`~Database.session_rollback` after calling the
         ``session_start`` method.

   .. method:: session_commit()

      Commit any changes made during a transaction begun with
      :meth:`~Database.session_start`.

   .. method:: session_rollback()

      Roll back any changes made during a transaction begun with
      :meth:`~Database.session_start`.

   .. method:: begin()

      Begin a transaction when using manual-commit mode.

      .. note::
         This method should only be used in conjunction with the
         :meth:`~Database.manual_commit` context manager.

   .. method:: commit()

      Manually commit the currently-active transaction.

      .. note::
         This method should only be used in conjunction with the
         :meth:`~Database.manual_commit` context manager.

   .. method:: rollback()

      Manually roll-back the currently-active transaction.

      .. note::
         This method should only be used in conjunction with the
         :meth:`~Database.manual_commit` context manager.

   .. method:: in_transaction()

      :return: whether or not a transaction is currently open.
      :rtype: bool

      .. code-block:: python

         with db.atomic() as tx:
             assert db.in_transaction()

         assert not db.in_transaction()  # No longer in transaction.

   .. method:: batch_commit(it, n)

      :param iterable it: an iterable whose items will be yielded.
      :param int n: commit every *n* items.
      :return: an equivalent iterable to the one provided, with the addition
          that groups of *n* items will be yielded in a transaction.

      Simplify batching large operations, such as inserts, updates, etc. Pass
      in an iterable and the number of items-per-batch, and the items will be
      returned by an equivalent iterator that wraps each batch in a
      transaction.

      Example:

      .. code-block:: python

         # Some list or iterable containing data to insert.
         row_data = [{'username': 'u1'}, {'username': 'u2'}, ...]

         # Insert all data, committing every 100 rows. If, for example,
         # there are 789 items in the list, then there will be a total of
         # 8 transactions (7x100 and 1x89).
         for row in db.batch_commit(row_data, 100):
             user = User.create(**row)

             # Now let's suppose we need to do something w/the user.
             user.call_method()

      A more efficient option is to batch the data into a multi-value ``INSERT``
      statement (for example, using :meth:`Model.insert_many`). Use this
      approach instead wherever possible:

      .. code-block:: python

         with db.atomic():
             for idx in range(0, len(row_data), 100):
                 # Insert 100 rows at a time.
                 rows = row_data[idx:idx + 100]
                 User.insert_many(rows).execute()

   .. method:: table_exists(table, schema=None)

      :param str table: Table name.
      :param str schema: Schema name (optional).
      :return: ``bool`` indicating whether table exists.

   .. method:: get_tables(schema=None)

      :param str schema: Schema name (optional).
      :return: a list of table names in the database.

   .. method:: get_indexes(table, schema=None)

      :param str table: Table name.
      :param str schema: Schema name (optional).

      Return a list of :class:`IndexMetadata` tuples.

      Example:

      .. code-block:: python

         print(db.get_indexes('entry'))
         [IndexMetadata(
              name='entry_public_list',
              sql='CREATE INDEX "entry_public_list" ...',
              columns=['timestamp'],
              unique=False,
              table='entry'),
          IndexMetadata(
              name='entry_slug',
              sql='CREATE UNIQUE INDEX "entry_slug" ON "entry" ("slug")',
              columns=['slug'],
              unique=True,
              table='entry')]

   .. method:: get_columns(table, schema=None)

      :param str table: Table name.
      :param str schema: Schema name (optional).

      Return a list of :class:`ColumnMetadata` tuples.

      Example:

      .. code-block:: python

         print(db.get_columns('entry'))
         [ColumnMetadata(
              name='id',
              data_type='INTEGER',
              null=False,
              primary_key=True,
              table='entry'),
          ColumnMetadata(
              name='title',
              data_type='TEXT',
              null=False,
              primary_key=False,
              table='entry'),
          ...]

   .. method:: get_primary_keys(table, schema=None)

      :param str table: Table name.
      :param str schema: Schema name (optional).

      Return a list of column names that comprise the primary key.

      Example:

      .. code-block:: python

         print(db.get_primary_keys('entry'))
         ['id']

   .. method:: get_foreign_keys(table, schema=None)

      :param str table: Table name.
      :param str schema: Schema name (optional).

      Return a list of :class:`ForeignKeyMetadata` tuples for keys present
      on the table.

      Example:

      .. code-block:: python

         print(db.get_foreign_keys('entrytag'))
         [ForeignKeyMetadata(
              column='entry_id',
              dest_table='entry',
              dest_column='id',
              table='entrytag'),
          ...]

   .. method:: get_views(schema=None)

      :param str schema: Schema name (optional).

      Return a list of :class:`ViewMetadata` tuples for VIEWs present in
      the database.

      Example:

      .. code-block:: python

         print(db.get_views())
         [ViewMetadata(
              name='entries_public',
              sql='CREATE VIEW entries_public AS SELECT ... '),
          ...]

   .. method:: sequence_exists(seq)

      :param str seq: Name of sequence.
      :return: Whether sequence exists.
      :rtype: bool

      .. code-block:: python

         if db.sequence_exists('user_id_seq'):
             print('Sequence found.')

   .. method:: create_tables(models, **options)

      :param list models: A list of :class:`Model` classes.
      :param options: Options to specify when calling
          :meth:`Model.create_table`.

      Create tables, indexes and associated constraints for the given list of
      models.

      Dependencies are resolved so that tables are created in the appropriate
      order.

   .. method:: drop_tables(models, **options)

      :param list models: A list of :class:`Model` classes.
      :param kwargs: Options to specify when calling
          :meth:`Model.drop_table`.

      Drop tables, indexes and constraints for the given list of models.

      Dependencies are resolved so that tables are dropped in the appropriate
      order.

   .. method:: bind(models, bind_refs=True, bind_backrefs=True)

      :param list models: One or more :class:`Model` classes to bind.
      :param bool bind_refs: Bind related models.
      :param bool bind_backrefs: Bind back-reference related models.

      Bind the given list of models, and specified relations, to the
      database.

      .. code-block:: python

         def setup_tests():
             # Bind models to an in-memory SQLite database.
             test_db = SqliteDatabase(':memory:')
             test_db.bind([User, Tweet])

   .. method:: bind_ctx(models, bind_refs=True, bind_backrefs=True)

       :param list models: List of models to bind to the database.
       :param bool bind_refs: Bind models that are referenced using
           foreign-keys.
       :param bool bind_backrefs: Bind models that reference the given model
           with a foreign-key.

       Create a context-manager that binds (associates) the given models with
       the current database for the duration of the wrapped block.

       Example:

       .. code-block:: python

           MODELS = [User, Tweet, Favorite]

           # Bind the given models to the db for the duration of wrapped block.
           def use_test_database(fn):
               @wraps(fn)
               def inner(self):
                   with test_db.bind_ctx(MODELS):
                       test_db.create_tables(MODELS)
                       try:
                           fn(self)
                       finally:
                           test_db.drop_tables(MODELS)
               return inner


           class TestSomething(TestCase):
               @use_test_database
               def test_something(self):
                   # ... models are bound to test database ...
                   pass

   .. method:: extract_date(date_part, date_field)

      :param str date_part: date part to extract, e.g. 'year'.
      :param Node date_field: a SQL node containing a date/time, for example
          a :class:`DateTimeField`.
      :return: a SQL node representing a function call that will return the
          provided date part.

      Provides a compatible interface for extracting a portion of a datetime.

   .. method:: truncate_date(date_part, date_field)

      :param str date_part: date part to truncate to, e.g. 'day'.
      :param Node date_field: a SQL node containing a date/time, for example
          a :class:`DateTimeField`.
      :return: a SQL node representing a function call that will return the
          truncated date part.

      Provides a compatible interface for truncating a datetime to the given
      resolution.

   .. method:: random()

      :return: a SQL node representing a function call that returns a random
          value.

      A compatible interface for calling the appropriate random number
      generation function provided by the database. For Postgres and Sqlite,
      this is equivalent to ``fn.random()``, for MySQL ``fn.rand()``.


.. class:: SqliteDatabase(database, pragmas=None, regexp_function=False, rank_functions=False, timeout=5, returning_clause=None,  **kwargs)

   :param pragmas: Either a dictionary or a list of 2-tuples containing
       pragma key and value to set every time a connection is opened.
   :param bool regexp_function: Make the REGEXP function available.
   :param bool rank_functions: Make the full-text search ranking functions
      available (recommended only if using FTS4).
   :param timeout: Set the busy-timeout on the SQLite driver (in seconds).
   :param bool returning_clause: Use `RETURNING` clause automatically for bulk
       INSERT queries (requires Sqlite 3.35 or newer).

   Sqlite database implementation. :class:`SqliteDatabase` that provides
   some advanced features only offered by Sqlite.

   * Register user-defined functions, aggregates, window functions, collations
   * Load extension modules distributed as shared libraries
   * Advanced transactions (specify lock type)
   * For additional features see :class:`CySqliteDatabase`.

   Example of initializing a database and configuring some PRAGMAs:

   .. code-block:: python

      db = SqliteDatabase('my_app.db', pragmas=(
          ('cache_size', -16000),  # 16MB
          ('journal_mode', 'wal'),  # Use write-ahead-log journal mode.
      ))

      # Alternatively, pragmas can be specified using a dictionary.
      db = SqliteDatabase('my_app.db', pragmas={'journal_mode': 'wal'})

   .. method:: pragma(key, value=SENTINEL, permanent=False)

      :param key: Setting name.
      :param value: New value for the setting (optional).
      :param permanent: Apply this pragma whenever a connection is opened.

      Execute a PRAGMA query once on the active connection. If a value is not
      specified, then the current value will be returned.

      If ``permanent`` is specified, then the PRAGMA query will also be
      executed whenever a new connection is opened, ensuring it is always
      in-effect.

   .. attribute:: cache_size

      Get or set the cache_size pragma for the current connection.

   .. attribute:: foreign_keys

      Get or set the foreign_keys pragma for the current connection.

   .. attribute:: journal_mode

      Get or set the journal_mode pragma.

   .. attribute:: journal_size_limit

      Get or set the journal_size_limit pragma.

   .. attribute:: mmap_size

      Get or set the mmap_size pragma for the current connection.

   .. attribute:: page_size

      Get or set the page_size pragma.

   .. attribute:: read_uncommitted

      Get or set the read_uncommitted pragma for the current connection.

   .. attribute:: synchronous

      Get or set the synchronous pragma for the current connection.

   .. attribute:: wal_autocheckpoint

      Get or set the wal_autocheckpoint pragma for the current connection.

   .. attribute:: timeout

      Get or set the busy timeout (seconds).

   .. method:: func(name=None, num_params=-1, deterministic=None)

      :param str name: Name of the function (defaults to function name).
      :param int num_params: Number of parameters the function accepts,
          or -1 for any number.
      :param bool deterministic: Whether the function is deterministic for a
          given input (this is required to use the function in an index).
          Requires Sqlite 3.20 or newer, and ``sqlite3`` driver support
          (added to stdlib in Python 3.8).

      Decorator to register a user-defined scalar function.

      Example:

      .. code-block:: python

         @db.func('title_case')
         def title_case(s):
             return s.title() if s else ''

         Book.select(fn.title_case(Book.title))

   .. method:: register_function(fn, name=None, num_params=-1, deterministic=None)

      :param fn: The user-defined scalar function.
      :param str name: Name of function (defaults to function name)
      :param int num_params: Number of arguments the function accepts, or
          -1 for any number.
      :param bool deterministic: Whether the function is deterministic for a
          given input (this is required to use the function in an index).
          Requires Sqlite 3.20 or newer, and ``sqlite3`` driver support
          (added to stdlib in Python 3.8).

      Register a user-defined scalar function. The function will be
      registered each time a new connection is opened.  Additionally, if a
      connection is already open, the function will be registered with the
      open connection.

   .. method:: aggregate(name=None, num_params=-1)

      :param str name: Name of the aggregate (defaults to class name).
      :param int num_params: Number of parameters the aggregate accepts,
          or -1 for any number.

      Class decorator to register a user-defined aggregate function.

      Example:

      .. code-block:: python

         @db.aggregate('md5')
         class MD5(object):
             def initialize(self):
                 self.md5 = hashlib.md5()

             def step(self, value):
                 self.md5.update(value)

             def finalize(self):
                 return self.md5.hexdigest()


         @db.aggregate()
         class Product(object):
             '''Like SUM() except calculates cumulative product.'''
             def __init__(self):
                 self.product = 1

             def step(self, value):
                 self.product *= value

             def finalize(self):
                 return self.product

   .. method:: register_aggregate(klass, name=None, num_params=-1)

      :param klass: Class implementing aggregate API.
      :param str name: Aggregate function name (defaults to name of class).
      :param int num_params: Number of parameters the aggregate accepts, or
          -1 for any number.

      Register a user-defined aggregate function.

      The function will be registered each time a new connection is opened.
      Additionally, if a connection is already open, the aggregate will be
      registered with the open connection.

   .. method:: window_function(name=None, num_params=-1)

      :param str name: Name of the window function (defaults to class name).
      :param int num_params: Number of parameters the function accepts, or -1
          for any number.

      Class decorator to register a user-defined window function. Window
      functions must define the following methods:

      * ``step(<params>)`` - receive values from a row and update state.
      * ``inverse(<params>)`` - inverse of ``step()`` for the given values.
      * ``value()`` - return the current value of the window function.
      * ``finalize()`` - return the final value of the window function.

      Example:

      .. code-block:: python

         @db.window_function('my_sum')
         class MySum(object):
             def __init__(self):
                 self._value = 0

             def step(self, value):
                 self._value += value

             def inverse(self, value):
                 self._value -= value

             def value(self):
                 return self._value

             def finalize(self):
                 return self._value

   .. method:: register_window_function(klass, name=None, num_params=-1)

      :param klass: Class implementing window function API.
      :param str name: Window function name (defaults to name of class).
      :param int num_params: Number of parameters the function accepts, or
          -1 for any number.

      Register a user-defined window function, requires SQLite >= 3.25.0.

      The window function will be registered each time a new connection is
      opened. Additionally, if a connection is already open, the window
      function will be registered with the open connection.

   .. method:: collation(name=None)

      :param str name: Name of collation (defaults to function name)

      Decorator to register a user-defined collation.

      Example:

      .. code-block:: python

         @db.collation('reverse')
         def collate_reverse(s1, s2):
             return -cmp(s1, s2)

         # Usage:
         Book.select().order_by(collate_reverse.collation(Book.title))

         # Equivalent:
         Book.select().order_by(Book.title.asc(collation='reverse'))

      As you might have noticed, the original ``collate_reverse`` function
      has a special attribute called ``collation`` attached to it.  This
      extra attribute provides a shorthand way to generate the SQL necessary
      to use our custom collation.

   .. method:: register_collation(fn, name=None)

      :param fn: The collation function.
      :param str name: Name of collation (defaults to function name)

      Register a user-defined collation. The collation will be registered
      each time a new connection is opened.  Additionally, if a connection is
      already open, the collation will be registered with the open
      connection.

   .. method:: unregister_function(name)

      :param name: Name of the user-defined scalar function.

      Unregister the user-defined scalar function.

   .. method:: unregister_aggregate(name)

      :param name: Name of the user-defined aggregate.

      Unregister the user-defined aggregate.

   .. method:: unregister_window_function(name)

      :param name: Name of the user-defined window function.

      Unregister the user-defined window function.

   .. method:: unregister_collation(name)

      :param name: Name of the user-defined collation.

      Unregister the user-defined collation.

   .. method:: load_extension(extension_module)

      Load the given extension shared library. Extension will be loaded for the
      current connection as well as all subsequent connections.

      .. code-block:: python

         db = SqliteDatabase('my_app.db')

         # Load extension in closure.so shared library.
         db.load_extension('closure')

   .. method:: unload_extension(extension_module):

      Unregister extension from being automatically loaded on new connections.

   .. method:: attach(filename, name)

      :param str filename: Database to attach (or ``:memory:`` for in-memory)
      :param str name: Schema name for attached database.
      :return: boolean indicating success

      Register another database file that will be attached to every database
      connection. If the main database is currently connected, the new
      database will be attached on the open connection.

      .. note::
         Databases that are attached using this method will be attached
         every time a database connection is opened.

   .. method:: detach(name)

      :param str name: Schema name for attached database.
      :return: boolean indicating success

      Unregister another database file that was attached previously with a
      call to ``attach()``. If the main database is currently connected, the
      attached database will be detached from the open connection.

   .. method:: atomic(lock_type=None)

      :param str lock_type: Locking strategy: DEFERRED, IMMEDIATE, EXCLUSIVE.

      Create an atomic context-manager / decorator, optionally using the
      specified locking strategy (default DEFERRED).

      Lock type only applies to the outermost ``atomic()`` block.

      .. seealso:: :ref:`sqlite-locking`

   .. method:: transaction(lock_type=None)

      :param str lock_type: Locking strategy: DEFERRED, IMMEDIATE, EXCLUSIVE.

      Create a transaction context-manager / decorator, optionally using the
      specified locking strategy (default DEFERRED).


.. class:: PostgresqlDatabase(database, register_unicode=True, encoding=None, isolation_level=None, prefer_psycopg3=False)

   Postgresql database implementation. Uses psycopg2 or psycopg3.

   Additional optional keyword-parameters:

   :param bool register_unicode: Register unicode types.
   :param str encoding: Database encoding.
   :param isolation_level: Isolation level constant, defined in the
       ``psycopg2.extensions`` module or ``psycopg.IsolationLevel`` enum (psycopg3).
       Also accepts string which is converted to the matching constant.
   :type isolation_level: int, str
   :param bool prefer_psycopg3: If both psycopg2 and psycopg3 are installed,
       instruct Peewee to prefer psycopg3.

   Example:

   .. code-block:: python

      db = PostgresqlDatabase(
          'app',
          user='postgres',
          host='10.8.0.1',
          port=5432,
          password=os.environ['PGPASSWORD'],
          isolation_level='SERIALIZABLE')

   .. method:: set_time_zone(timezone)

      :param str timezone: timezone name, e.g. "US/Central".
      :return: no return value.

      Set the timezone on the current connection. If no connection is open,
      then one will be opened.

   .. method:: set_isolation_level(isolation_level)

      :param isolation_level: Isolation level constant, defined in the
          ``psycopg2.extensions`` module or ``psycopg.IsolationLevel`` enum (psycopg3).
          Also accepts string which is converted to the matching constant.
          Set to ``None`` to use the server default.
      :type isolation_level: int, str

      Example of setting isolation level:

      .. code-block:: python

         # psycopg2 or psycopg3
         db = db.set_isolation_level('SERIALIZABLE')

         # psycopg2
         from psycopg2.extensions import ISOLATION_LEVEL_SERIALIZABLE
         db.set_isolation_level(ISOLATION_LEVEL_SERIALIZABLE)

         # psycopg3
         from psycopg import IsolationLevel
         db.set_isolation_level(IsolationLevel.SERIALIZABLE)

      Isolation level values in order of increasing strictness:

      * READ UNCOMMITTED
      * READ COMMITTED
      * REPEATABLE READ
      * SERIALIZABLE

      See the `Postgresql transaction isolation docs <https://www.postgresql.org/docs/current/transaction-iso.html>`__
      and Peewee's :ref:`postgres-isolation` for additional discussion.

   .. method:: atomic(isolation_level=None)

      :param isolation_level: Isolation strategy: SERIALIZABLE, READ COMMITTED, REPEATABLE READ, READ UNCOMMITTED
      :type isolation_level: int, str

      Create an atomic context-manager, optionally using the specified
      isolation level (if unspecified, the connection default will be used).

      Isolation level only applies to the outermost ``atomic()`` block.

      See the `Postgresql transaction isolation docs <https://www.postgresql.org/docs/current/transaction-iso.html>`__
      and Peewee's :ref:`postgres-isolation` for additional discussion.

   .. method:: transaction(isolation_level=None)

      :param isolation_level: Isolation strategy: SERIALIZABLE, READ COMMITTED, REPEATABLE READ, READ UNCOMMITTED
      :type isolation_level: int, str

      Create a transaction context-manager, optionally using the specified
      isolation level (if unspecified, the connection default will be used).


.. class:: MySQLDatabase(database, **kwargs)

   MySQL database implementation.

   Example:

   .. code-block:: python

      db = MySQLDatabase('app', host='10.8.0.1')

   .. method:: atomic(isolation_level=None)

      :param str isolation_level: Isolation strategy: SERIALIZABLE, READ COMMITTED, REPEATABLE READ, READ UNCOMMITTED

      Create an atomic context-manager, optionally using the specified
      isolation level (if unspecified, the server default will be used).

      Isolation level only applies to the outermost ``atomic()`` block.

   .. method:: transaction(isolation_level=None)

      :param str isolation_level: Isolation strategy: SERIALIZABLE, READ COMMITTED, REPEATABLE READ, READ UNCOMMITTED

      Create a transaction context-manager, optionally using the specified
      isolation level (if unspecified, the server default will be used).

.. _model-api:

Model
-----

.. class:: Model(**kwargs)

   :param kwargs: Mapping of field-name to value to initialize model with.

   Model class provides a high-level abstraction for working with database
   tables. Models are a one-to-one mapping with a database table (or a
   table-like object, such as a view). Subclasses of ``Model`` declare any
   number of :class:`Field` instances as class attributes. These fields
   correspond to columns on the table.

   Table-level operations, such as :meth:`~Model.select`,
   :meth:`~Model.update`, :meth:`~Model.insert` and
   :meth:`~Model.delete` are implemented as classmethods.

   Row-level operations, such as :meth:`~Model.save` and :meth:`~Model.delete_instance`
   are implemented as instancemethods.

   Example:

   .. code-block:: python

      db = SqliteDatabase(':memory:')

      class User(Model):
          username = TextField()
          join_date = DateTimeField(default=datetime.datetime.now)
          is_admin = BooleanField(default=False)

      admin = User(username='admin', is_admin=True)
      admin.save()

   .. classmethod:: alias([alias=None])

      :param str alias: Optional name for alias.
      :return: :class:`ModelAlias` instance.

      Create an alias to the model-class. Model aliases allow you to
      reference the same :class:`Model` multiple times in a query, for
      example when doing a self-join or sub-query.

      Example:

      .. code-block:: python

         Parent = Category.alias()
         sq = (Category
               .select(Category, Parent)
               .join(Parent, on=(Category.parent == Parent.id))
               .where(Parent.name == 'parent category'))

   .. classmethod:: select(*fields)

      :param fields: A list of model classes, field instances, functions or
          expressions. If no arguments are provided, all columns for the
          given model will be selected by default.
      :return: :class:`ModelSelect` query.

      Create a SELECT query. If no fields are explicitly provided, the query
      will by default SELECT all the fields defined on the model, unless you
      are using the query as a sub-query, in which case only the primary key
      will be selected by default.

      Example of selecting all columns:

      .. code-block:: python

         query = User.select().where(User.active == True).order_by(User.username)

      Example of selecting all columns on *Tweet* and the parent model,
      *User*. When the ``user`` foreign key is accessed on a *Tweet*
      instance no additional query will be needed (see :ref:`N+1 <nplusone>`
      for more details):

      .. code-block:: python

         query = (Tweet
                  .select(Tweet, User)
                  .join(User)
                  .order_by(Tweet.created_date.desc()))

         for tweet in query:
             print(tweet.user.username, '->', tweet.content)

      Example of subquery only selecting the primary key:

      .. code-block:: python

         inactive_users = User.select().where(User.active == False)

         # Here, instead of defaulting to all columns, Peewee will default
         # to only selecting the primary key.
         Tweet.delete().where(Tweet.user.in_(inactive_users)).execute()

      See :ref:`querying` for in-depth discussion.

   .. classmethod:: update(__data=None, **update)

      :param dict __data: ``dict`` of fields to values.
      :param update: Field-name to value mapping.

      Create an UPDATE query.

      Example showing users being marked inactive if their registration has
      expired:

      .. code-block:: python

         q = (User
              .update(active=False)
              .where(User.registration_expired == True))
         q.execute()  # Execute the query, returning number of rows updated.

      Example showing an atomic update:

      .. code-block:: python

         q = (PageView
              .update({PageView.count: PageView.count + 1})
              .where(PageView.url == url))
         q.execute()  # Execute the query.

      Update queries support :meth:`~WriteQuery.returning` with Postgresql and SQLite
      to obtain the updated rows:

      .. code-block:: python

         query = (User
                  .update(spam=True)
                  .where(User.username.contains('billing'))
                  .returning(User))
         for user in query:
             print(f'Marked {user.username} as spam')

      See :ref:`updating-records` for additional discussion.

      .. note::
         When an update query is executed, the number of rows modified will
         be returned.

   .. classmethod:: insert(__data=None, **insert)

      :param dict __data: ``dict`` of fields to values to insert.
      :param insert: Field-name to value mapping.

      Create an INSERT query.

      Insert a new row into the database. If any fields on the model have
      default values, these values will be used if the fields are not
      explicitly set in the ``insert`` dictionary.

      Example showing creation of a new user:

      .. code-block:: python

         q = User.insert(username='admin', active=True, registration_expired=False)
         q.execute()  # perform the insert.

      You can also use :class:`Field` objects as the keys:

      .. code-block:: python

         new_id = User.insert({User.username: 'admin'}).execute()

      If you have a model with a default value on one of the fields, and
      that field is not specified in the ``insert`` parameter, the default
      will be used:

      .. code-block:: python

         class User(Model):
             username = CharField()
             active = BooleanField(default=True)

         # This INSERT query will automatically specify `active=True`:
         User.insert(username='charlie')

      Insert queries support :meth:`~WriteQuery.returning` with Postgresql and
      SQLite to obtain the inserted rows:

      .. code-block:: python

         alice, = (User
                   .insert(username='alice')
                   .returning(User)
                   .execute())
         print(f'Added {alice.username} with id = {alice.id}')

      .. note::
         When an insert query is executed on a table with an
         auto-incrementing primary key, the primary key of the new row will
         be returned.

   .. classmethod:: insert_many(rows, fields=None)

      :param rows: An iterable that yields rows to insert.
      :param list fields: List of fields being inserted.
      :return: number of rows modified (see note).

      INSERT multiple rows of data.

      The ``rows`` parameter must be an iterable that yields dictionaries or
      tuples, where the ordering of the tuple values corresponds to the
      fields specified in the ``fields`` argument. As with
      :meth:`~Model.insert`, fields that are not specified in the
      dictionary will use their default value, if one exists.

      .. note::
         Due to the nature of bulk inserts, each row must contain the same
         fields. The following will not work:

         .. code-block:: python

             Person.insert_many([
                 {'first_name': 'Peewee', 'last_name': 'Herman'},
                 {'first_name': 'Huey'},  # Missing "last_name"!
             ]).execute()

      Example of inserting multiple Users:

      .. code-block:: python

         data = [
             ('charlie', True),
             ('huey', False),
             ('zaizee', False)]
         query = User.insert_many(data, fields=[User.username, User.is_admin])
         query.execute()

      Equivalent example using dictionaries:

      .. code-block:: python

         data = [
             {'username': 'charlie', 'is_admin': True},
             {'username': 'huey', 'is_admin': False},
             {'username': 'zaizee', 'is_admin': False}]

         # Insert new rows.
         User.insert_many(data).execute()

      Because the ``rows`` parameter can be an arbitrary iterable, you can
      also use a generator:

      .. code-block:: python

         def get_usernames():
             for username in ['charlie', 'huey', 'peewee']:
                 yield {'username': username}
         User.insert_many(get_usernames()).execute()

      Insert queries support :meth:`~WriteQuery.returning` with Postgresql and
      SQLite to obtain the inserted rows:

      .. code-block:: python

         query = (User
                  .insert_many([{'username': 'alice'}, {'username': 'bob'}])
                  .returning(User))
         for user in query:
             print(f'Added {user.username} with id = {user.id}')

      See :ref:`bulk-inserts` for additional discussion.

      .. note::
         SQLite has a default limit of bound variables per statement.
         Additional discussion: :ref:`bulk-inserts`.

         SQLite documentation:

         * `Max variable number limit <https://www.sqlite.org/limits.html#max_variable_number>`_
         * `SQLite compile-time flags <https://www.sqlite.org/compile.html>`_

      .. note::
         The default return value is the number of rows modified. However,
         when using Postgresql, Peewee will return a cursor that yields the
         primary-keys of the inserted rows. To disable this functionality with
         Postgresql, append ``as_rowcount()`` to your insert.

   .. classmethod:: insert_from(query, fields)

      :param Select query: SELECT query to use as source of data.
      :param fields: Fields to insert data into.
      :return: number of rows modified (see note).

      Generates an ``INSERT INTO ... SELECT`` query, copying rows from one
      table into another without round-tripping data through Python:

      .. code-block:: python

         (TweetArchive
          .insert_from(
              Tweet.select(Tweet.user, Tweet.message),
              fields=[TweetArchive.user, TweetArchive.message])
          .execute())

      See :ref:`bulk-inserts` for additional discussion.

      .. note::
         The default return value is the number of rows modified. However,
         when using Postgresql, Peewee will return a cursor that yields the
         primary-keys of the inserted rows. To disable this functionality with
         Postgresql, append ``as_rowcount()`` to your insert.

   .. classmethod:: replace(__data=None, **insert)

      :param dict __data: ``dict`` of fields to values to insert.
      :param insert: Field-name to value mapping.

      SQLite and MySQL support a ``REPLACE`` query, which will replace the row
      in the event of a conflict:

      .. code-block:: python

         class User(BaseModel):
             username = TextField(unique=True)
             last_login = DateTimeField(null=True)

         # Insert, or replace the entire existing row.
         User.replace(username='huey', last_login=datetime.datetime.now()).execute()

         # Equivalent using insert():
         (User
          .insert(username='huey', last_login=datetime.datetime.now())
          .on_conflict_replace()
          .execute())

      See :ref:`upsert` for additional discussion.

      .. warning::
         ``replace`` deletes and re-inserts, which changes the primary key.
         Use :meth:`Insert.on_conflict` when the primary key must be preserved,
         or when only some columns should be updated.

   .. classmethod:: replace_many(rows, fields=None)

      :param rows: An iterable that yields rows to insert.
      :param list fields: List of fields being inserted.

      INSERT multiple rows of data using REPLACE for conflict-resolution.

      .. seealso::
         * :meth:`Model.insert_many` for syntax and examples.
         * :ref:`upsert` for additional discussion.

      .. warning::
         ``replace_many`` may delete and re-insert rows, which changes the
         primary key. Use :meth:`Insert.on_conflict` when the primary key must
         be preserved, or when only some columns should be updated.

   .. classmethod:: raw(sql, *params)

      :param str sql: SQL query to execute.
      :param params: Parameters for query.

      Execute a SQL query directly.

      Example selecting rows from the User table:

      .. code-block:: python

         q = User.raw('select id, username from users')
         for user in q:
             print(user.id, user.username)

      .. note::
         Generally the use of ``raw`` is reserved for those cases where you
         can significantly optimize a select query.

   .. classmethod:: delete()

      Create a DELETE query.

      Example showing the deletion of all inactive users:

      .. code-block:: python

         q = User.delete().where(User.active == False)
         q.execute()  # Remove the rows, return number of rows removed.

      Delete queries support :meth:`~WriteQuery.returning` with Postgresql and
      SQLite to obtain the deleted rows:

      .. code-block:: python

         query = (User
                  .delete()
                  .where(User.username.contains('billing'))
                  .returning(User))
         for user in query:
             print(f'Deleted: {user.username}')

      .. seealso::
         * :ref:`deleting-records` for discussion and example usage.
         * :meth:`Model.delete_instance` for deleting individual rows.

   .. classmethod:: create(**query)

      :param query: Mapping of field-name to value.

      INSERT new row into table and return corresponding model instance.

      Example showing the creation of a user (a row will be added to the
      database):

      .. code-block:: python

         user = User.create(username='admin', password='test')

      .. note::
         ``create()`` is a shorthand for instantiate -> save.

   .. classmethod:: bulk_create(model_list, batch_size=None)

      :param iterable model_list: a list or other iterable of unsaved
          :class:`Model` instances.
      :param int batch_size: number of rows to batch per insert. If
          unspecified, all models will be inserted in a single query.
      :return: no return value.

      Efficiently INSERT multiple unsaved model instances into the database.
      Unlike :meth:`~Model.insert_many`, which accepts row data as a list
      of either dictionaries or lists, this method accepts a list of unsaved
      model instances.

      Example:

      .. code-block:: python

         user_list = [User(username='u%s' % i) for i in range(10)]

         with db.atomic():
             # All 10 users are inserted in a single query.
             User.bulk_create(user_list)

      Batches:

      .. code-block:: python

          user_list = [User(username='u%s' % i) for i in range(10)]

          with database.atomic():
              # Will execute 4 INSERT queries (3 batches of 3, 1 batch of 1).
              User.bulk_create(user_list, batch_size=3)

      .. note::
         * The primary-key value for the newly-created models will only be
           set if you are using Postgresql (which supports the ``RETURNING``
           clause).
         * SQLite has a limit of bound parameters for a query, typically 999
           for Sqlite < 3.32.0, and 32766 for newer versions.
         * **Strongly recommended** that you wrap the call in a transaction
           using :meth:`Database.atomic`. Otherwise an error in a batch mid-way
           through could leave the database in an inconsistent state.

   .. classmethod:: bulk_update(model_list, fields, batch_size=None)

      :param iterable model_list: a list or other iterable of
          :class:`Model` instances.
      :param list fields: list of fields to update.
      :param int batch_size: number of rows to batch per insert. If
          unspecified, all models will be inserted in a single query.
      :return: total number of rows updated.

      UPDATE multiple model instances in a single query by generating a
      ``CASE`` statement mapping ids to new field values.

      Example:

      .. code-block:: python

         # First, create 3 users.
         u1, u2, u3 = [User.create(username='u%s' % i) for i in (1, 2, 3)]

         # Now let's modify their usernames.
         u1.username = 'u1-x'
         u2.username = 'u2-y'
         u3.username = 'u3-z'

         # Update all three rows using a single UPDATE query.
         User.bulk_update([u1, u2, u3], fields=[User.username])

      This will result in executing the following SQL:

      .. code-block:: sql

         UPDATE "users" SET "username" = CASE "users"."id"
             WHEN 1 THEN "u1-x"
             WHEN 2 THEN "u2-y"
             WHEN 3 THEN "u3-z" END
         WHERE "users"."id" IN (1, 2, 3);

      If you have a large number of objects to update, it is strongly
      recommended that you specify a ``batch_size`` and wrap the operation in
      a transaction:

      .. code-block:: python

         with database.atomic():
             User.bulk_update(user_list, fields=['username'], batch_size=50)

      .. note::
         ``bulk_update`` may be slower than a direct UPDATE query when the list is
         very large, because the generated ``CASE`` expression grows proportionally.
         For updates that can be expressed as a single WHERE clause, the direct
         :meth:`~Model.update` approach is faster.

   .. classmethod:: get(*query, **filters)

      :param query: Zero or more :class:`Expression` objects.
      :param filters: Mapping of field-name to value for Django-style filter.
      :raises: :class:`DoesNotExist`
      :return: Model instance matching the specified filters.

      Retrieve a single model instance matching the given filters. If no
      model is returned, a :class:`DoesNotExist` is raised.

      .. code-block:: python

         user = User.get(User.username == username, User.active == True)

      This method is also exposed via the :class:`SelectQuery`, though it
      takes no parameters:

      .. code-block:: python

         active = User.select().where(User.active == True)
         try:
             user = (active
                     .where(
                         (User.username == username) &
                         (User.active == True))
                     .get())
         except User.DoesNotExist:
             user = None

      .. note::
         The :meth:`~Model.get` method is shorthand for selecting with a
         limit of 1. It has the added behavior of raising an exception when
         no matching row is found. If more than one row is found, the first
         row returned by the database cursor will be used.

   .. classmethod:: get_or_none(*query, **filters)

      Identical to :meth:`Model.get` but returns ``None`` if no model
      matches the given filters.

      .. code-block:: python

         active = User.select().where(User.active == True)
         user = (active
                 .where(
                     (User.username == username) &
                     (User.active == True))
                 .get_or_none())

   .. classmethod:: get_by_id(pk)

      :param pk: Primary-key value.

      Short-hand for calling :meth:`Model.get` specifying a lookup by
      primary key. Raises a :class:`DoesNotExist` if instance with the
      given primary key value does not exist.

      Example:

      .. code-block:: python

         user = User.get_by_id(1)  # Returns user with id = 1.

   .. classmethod:: set_by_id(key, value)

      :param key: Primary-key value.
      :param dict value: Mapping of field to value to update.

      Short-hand for updating the data with the given primary-key. If no row
      exists with the given primary key, no exception will be raised.

      Example:

      .. code-block:: python

         # Set "is_admin" to True on user with id=3.
         User.set_by_id(3, {'is_admin': True})

   .. classmethod:: delete_by_id(pk)

      :param pk: Primary-key value.

      Short-hand for deleting the row with the given primary-key. If no row
      exists with the given primary key, no exception will be raised.

   .. classmethod:: get_or_create(**kwargs)

      :param kwargs: Mapping of field-name to value.
      :param defaults: Default values to use if creating a new row.
      :return: Tuple of :class:`Model` instance and boolean indicating
          if a new object was created.

      Attempt to get the row matching the given filters. If no matching row
      is found, create a new row.

      .. warning:: Race-conditions are possible when using this method.

      Example **without** ``get_or_create``:

      .. code-block:: python

         # Without `get_or_create`, we might write:
         try:
             person = Person.get(
                 (Person.first_name == 'John') &
                 (Person.last_name == 'Lennon'))
         except Person.DoesNotExist:
             person = Person.create(
                 first_name='John',
                 last_name='Lennon',
                 birthday=datetime.date(1940, 10, 9))

      Equivalent code using ``get_or_create``:

      .. code-block:: python

         person, created = Person.get_or_create(
             first_name='John',
             last_name='Lennon',
             defaults={'birthday': datetime.date(1940, 10, 9)})

   .. classmethod:: filter(*dq_nodes, **filters)

      :param dq_nodes: Zero or more :class:`DQ` objects.
      :param filters: Django-style filters.
      :return: :class:`ModelSelect` query.

   .. method:: get_id()

      :return: The primary-key of the model instance.

   .. method:: save(force_insert=False, only=None)

      :param bool force_insert: Force INSERT query.
      :param list only: Only save the given :class:`Field` instances.
      :return: Number of rows modified.

      Save the data in the model instance. By default, the presence of a
      primary-key value will cause an UPDATE query to be executed.

      Example showing saving a model instance:

      .. code-block:: python

         user = User()
         user.username = 'some-user'  # does not touch the database
         user.save()  # change is persisted to the db

      When a model uses any primary key OTHER than an auto-incrementing integer
      it is necessary to specify ``force_insert=True`` when calling ``save()``
      with a new instance:

      .. code-block:: python

         class Tag(Model):
             tag = TextField(primary_key=True)

         t = Tag(tag='python')
         t.save(force_insert=True)

         # create() automatically specifies force_insert=True:
         t = Tag.create(tag='sqlite')

   .. attribute:: dirty_fields

      Return list of fields that have been modified.

      :rtype: list

      .. note::
         If you just want to persist modified fields, you can call
         ``model.save(only=model.dirty_fields)``.

         To **always** save a model's dirty fields, use the Meta option
         ``only_save_dirty = True``. Any calls to :meth:`Model.save()` will
         only save the dirty fields by default:

         .. code-block:: python

            class Person(Model):
                first_name = CharField()
                last_name = CharField()
                dob = DateField()

                class Meta:
                    database = db
                    only_save_dirty = True

      .. warning::
         Peewee determines whether a field is "dirty" by observing when the
         field attribute is set on a model instance. If the field contains a
         value that is mutable, such as a dictionary instance, and that
         dictionary is then modified, Peewee will not notice the change.

      .. warning::
         Do not do membership tests on this list, e.g. ``f in dirty_fields``
         because if there is one or more fields in the dirty fields list,
         the field equality override will return a truthy Expression object.
         If you want to test if a field is dirty, instead
         check ``f.name in model.dirty_field_names``.

   .. attribute:: dirty_field_names

      Return list of field names that have been modified.

      :rtype: list

   .. method:: is_dirty()

      Return boolean indicating whether any fields were manually set.

   .. method:: delete_instance(recursive=False, delete_nullable=False)

       :param bool recursive: Delete related models.
       :param bool delete_nullable: Delete related models that have a null
           foreign key. If ``False`` nullable relations will be set to NULL.

       Delete the given instance.  Any foreign keys set to cascade on
       delete will be deleted automatically.  For more programmatic control,
       you can specify ``recursive=True``, which will delete any non-nullable
       related models (those that *are* nullable will be set to NULL).  If you
       wish to delete all dependencies regardless of whether they are nullable,
       set ``delete_nullable=True``.

       Example:

       .. code-block:: python

          some_obj.delete_instance()

       See :ref:`deleting-records` for additional discussion.

   .. classmethod:: bind(database, bind_refs=True, bind_backrefs=True)

      :param Database database: database to bind to.
      :param bool bind_refs: Bind related models.
      :param bool bind_backrefs: Bind back-reference related models.

      Bind the model (and specified relations) to the given database.

      See also: :meth:`Database.bind`.

   .. classmethod:: bind_ctx(database, bind_refs=True, bind_backrefs=True)

      Like :meth:`~Model.bind`, but returns a context manager that only
      binds the models for the duration of the wrapped block.

      See also: :meth:`Database.bind_ctx`.

   .. classmethod:: table_exists()

      :return: boolean indicating whether the table exists.

   .. classmethod:: create_table(safe=True, **options)

      :param bool safe: When ``True``, the create table query will
          include an ``IF NOT EXISTS`` clause.

      Create the model table, indexes, constraints and sequences.

      Example:

      .. code-block:: python

         with database:
             SomeModel.create_table()

   .. classmethod:: drop_table(safe=True, **options)

      :param bool safe: If set to ``True``, the drop table query will
          include an ``IF EXISTS`` clause.

      Drop the model table.

   .. method:: truncate_table(restart_identity=False, cascade=False)

      :param bool restart_identity: Restart the id sequence (postgresql-only).
      :param bool cascade: Truncate related tables as well (postgresql-only).

      Truncate (delete all rows) for the model.

   .. classmethod:: index(*fields, unique=False, safe=True, where=None, using=None, name=None)

      :param fields: Fields to index.
      :param bool unique: Whether index is UNIQUE.
      :param bool safe: Whether to add IF NOT EXISTS clause.
      :param Expression where: Optional WHERE clause for index.
      :param str using: Index algorithm.
      :param str name: Optional index name.

      Expressive method for declaring an index on a model. Wraps the
      declaration of a :class:`ModelIndex` instance.

      Examples:

      .. code-block:: python

         class Article(Model):
             name = TextField()
             timestamp = TimestampField()
             status = IntegerField()
             flags = BitField()

             is_sticky = flags.flag(1)
             is_favorite = flags.flag(2)

         # CREATE INDEX ... ON "article" ("name", "timestamp" DESC)
         idx = Article.index(Article.name, Article.timestamp.desc())

         # Be sure to add the index to the model:
         Article.add_index(idx)

         # CREATE UNIQUE INDEX ... ON "article" ("timestamp" DESC, "flags" & 2)
         # WHERE ("status" = 1)
         idx = (Article
                .index(Article.timestamp.desc(),
                       Article.flags.bin_and(2),
                       unique=True)
                .where(Article.status == 1))

         # Add index to model:
         Article.add_index(idx)

   .. classmethod:: add_index(*args, **kwargs)

      :param args: a :class:`ModelIndex` instance, Field(s) to index,
          or a :class:`SQL` instance that contains the SQL for creating
          the index.
      :param kwargs: Keyword arguments passed to :class:`ModelIndex`
          constructor.

      Add an index to the model's definition.

      .. note::
         This method does not actually create the index in the database.
         Rather, it adds the index definition to the model's metadata, so
         that a subsequent call to :meth:`~Model.create_table` will
         create the new index (along with the table).

      Examples:

      .. code-block:: python

         class Article(Model):
             name = TextField()
             timestamp = TimestampField()
             status = IntegerField()
             flags = BitField()

             is_sticky = flags.flag(1)
             is_favorite = flags.flag(2)

         # CREATE INDEX ... ON "article" ("name", "timestamp") WHERE "status" = 1
         idx = Article.index(Article.name, Article.timestamp).where(Article.status == 1)
         Article.add_index(idx)

         # CREATE UNIQUE INDEX ... ON "article" ("timestamp" DESC, "flags" & 2)
         ts_flags_idx = Article.index(
             Article.timestamp.desc(),
             Article.flags.bin_and(2),
             unique=True)
         Article.add_index(ts_flags_idx)

         # You can also specify a list of fields and use the same keyword
         # arguments that the ModelIndex constructor accepts:
         Article.add_index(
             Article.name,
             Article.timestamp.desc(),
             where=(Article.status == 1))

         # Or even specify a SQL query directly:
         Article.add_index(SQL('CREATE INDEX ...'))

   .. method:: dependencies(search_nullable=False)

      :param bool search_nullable: Search models related via a nullable
          foreign key
      :rtype: Generator expression yielding queries and foreign key fields.

      Generate a list of queries of dependent models. Yields a 2-tuple
      containing the query and corresponding foreign key field.  Useful for
      searching dependencies of a model, i.e. things that would be orphaned
      in the event of a delete.

   .. method:: __iter__()

      :return: a :class:`ModelSelect` for the given class.

      Convenience function for iterating over all instances of a model.

      Example:

      .. code-block:: python

         Setting.insert_many([
             {'key': 'host', 'value': '192.168.1.2'},
             {'key': 'port': 'value': '1337'},
             {'key': 'user': 'value': 'nuggie'}]).execute()

         # Load settings from db into dict.
         settings = {setting.key: setting.value for setting in Setting}

   .. method:: __len__()

      :return: Count of rows in table.

      Example:

      .. code-block:: python

         n_accounts = len(Account)

         # Equivalent:
         n_accounts = Account.select().count()


.. class:: ModelAlias(model, alias=None)

   :param Model model: Model class to reference.
   :param str alias: (optional) name for alias.

   Provide a separate reference to a model in a query.

   With Peewee, we use :meth:`Model.alias` to alias a model class so it can be
   referenced twice in a single query:

   .. code-block:: python

       Owner = User.alias()
       query = (Favorite
                .select(Favorite, Tweet.content, User.username, Owner.username)
                .join_from(Favorite, Owner)  # Determine owner of favorite.
                .join_from(Favorite, Tweet)  # Join favorite -> tweet.
                .join_from(Tweet, User))     # Join tweet -> user.

   See :ref:`relationships` for additional discussion.


.. class:: Metadata(model, database=None, table_name=None, indexes=None, primary_key=None, constraints=None, schema=None, only_save_dirty=False, depends_on=None, options=None, without_rowid=False, strict_tables=False, **kwargs)

   :param Model model: Model class.
   :param Database database: database model is bound to.
   :param str table_name: Specify table name for model.
   :param list indexes: List of :class:`ModelIndex` objects.
   :param primary_key: Primary key for model (only specified if this is a
       :class:`CompositeKey` or ``False`` for no primary key.
   :param list constraints: List of table constraints.
   :param str schema: Schema table exists in.
   :param bool only_save_dirty: When :meth:`~Model.save` is called, only
       save the fields which have been modified.
   :param dict options: Arbitrary options for the model.
   :param bool without_rowid: Specify WITHOUT ROWID (sqlite only).
   :param bool strict_tables: Specify STRICT (sqlite only, requires 3.37+).
   :param kwargs: Arbitrary setting attributes and values.

   Store metadata for a :class:`Model`.

   This class should not be instantiated directly, but is instantiated using
   the attributes of a :class:`Model` class' inner ``Meta`` class. Metadata
   attributes are then available on ``Model._meta``.

   Example:

   .. code-block:: python

      class User(Model):
          ...
          class Meta:
              database = db
              table_name = 'user'

      # After class-creation, Meta configuration lives here:
      isinstance(User._meta, Metadata)  # True
      User._meta.database is db         # True
      User._meta.table_name == 'user'   # True

   .. seealso:: :ref:`model-options` for usage.

   .. attribute:: table

      Return a reference to the underlying :class:`Table` object.

   .. method:: model_graph(refs=True, backrefs=True, depth_first=True)

      :param bool refs: Follow foreign-key references.
      :param bool backrefs: Follow foreign-key back-references.
      :param bool depth_first: Do a depth-first search (``False`` for
          breadth-first).

      Traverse the model graph and return a list of 3-tuples, consisting of
      ``(foreign key field, model class, is_backref)``.

   .. method:: set_database(database)

      :param Database database: database object to bind Model to.

      Bind the model class to the given :class:`Database` instance.

      .. warning::
         This API should not need to be used. Instead, to change a
         :class:`Model` database at run-time, use one of the following:

         * :meth:`Model.bind`
         * :meth:`Model.bind_ctx` (bind for scope of a context manager).
         * :meth:`Database.bind`
         * :meth:`Database.bind_ctx`

   .. method:: set_table_name(table_name)

      :param str table_name: table name to bind Model to.

      Bind the model class to the given table name at run-time.


.. class:: SubclassAwareMetadata

   Metadata subclass that tracks :class:`Model` subclasses. Useful for
   when you need to track all models in a project.

   Example:

   .. code-block:: python

      from peewee import SubclassAwareMetadata

      class Base(Model):
          class Meta:
              database = db
              model_metadata_class = SubclassAwareMetadata

      # Create 3 model classes that inherit from Base.
      class A(Base): pass
      class B(Base): pass
      class C(Base): pass

      # Now let's make a helper for changing the `schema` for each Model.
      def change_schema(schema):
          def _update(model):
              model._meta.schema = schema
          return _update

      # Set all models to use "schema1", e.g. "schema1.a", "schema1.b", etc.
      # Will apply the function to every subclass of Base.
      Base._meta.map_models(change_schema('schema1'))

      # Set all models to use "schema2", e.g. "schema2.a", "schema2.b", etc.
      Base._meta.map_models(change_schema('schema2'))

   .. method:: map_models(fn)

      Apply a function to all subclasses.

.. seealso::
   :class:`~playhouse.shortcuts.ThreadSafeDatabaseMetadata` for a :class:`Metadata`
   subclass that supports changing the ``database`` attribute at run-time in a
   multi-threaded environment.


.. class:: ModelSelect(model, fields_or_models)

   :param Model model: Model class to select.
   :param fields_or_models: List of fields or model classes to select.

   Model-specific implementation of SELECT query.

   .. method:: switch(ctx=None)

      :param ctx: A :class:`Model`, :class:`ModelAlias`, subquery, or
          other object that was joined-on.

      Switch the *join context* - the source which subsequent calls to
      :meth:`~ModelSelect.join` will be joined against. Used for
      specifying multiple joins against a single table.

      See :ref:`relationships` for additional discussion.

      If the ``ctx`` is not given, then the query's model will be used.

      The following example selects from tweet and joins on both user and
      tweet-flag:

      .. code-block:: python

          sq = Tweet.select().join(User).switch(Tweet).join(TweetFlag)

          # Equivalent (since Tweet is the query's model)
          sq = Tweet.select().join(User).switch().join(TweetFlag)

   .. method:: objects(constructor=None)

      :param constructor: Constructor (defaults to returning model instances)

      Return result rows as objects created using the given constructor. The
      default behavior is to create model instances.

      .. note::
         This method can be used, when selecting field data from multiple
         sources/models, to make all data available as attributes on the
         model being queried (as opposed to constructing the graph of joined
         model instances). For very complex queries this can have a positive
         performance impact, especially iterating large result sets.

         Similarly, you can use :meth:`~BaseQuery.dicts`,
         :meth:`~BaseQuery.tuples` or :meth:`~BaseQuery.namedtuples`
         to achieve even more performance.

   .. method:: join(dest, join_type='INNER', on=None, src=None, attr=None)

      :param dest: A :class:`Model`, :class:`ModelAlias`,
          :class:`Select` query, or other object to join to.
      :param str join_type: Join type, defaults to INNER.
      :param on: Join predicate or a :class:`ForeignKeyField` to join on.
      :param src: Explicitly specify the source of the join. If not specified
          then the current *join context* will be used.
      :param str attr: Attribute to use when projecting columns from the
          joined model.

      Join with another table-like object.

      Join type may be one of:

      * ``JOIN.INNER``
      * ``JOIN.LEFT_OUTER``
      * ``JOIN.RIGHT_OUTER``
      * ``JOIN.FULL``
      * ``JOIN.FULL_OUTER``
      * ``JOIN.CROSS``

      Example selecting tweets and joining on user in order to restrict to
      only those tweets made by "admin" users:

      .. code-block:: python

         sq = Tweet.select().join(User).where(User.is_admin == True)

      Example selecting users and joining on a particular foreign key field.
      See the :ref:`example app <example>` for a real-life usage:

      .. code-block:: python

         sq = User.select().join(Relationship, on=Relationship.to_user)

      For an in-depth discussion of foreign-keys, joins and relationships
      between models, refer to :ref:`relationships`.

   .. method:: join_from(src, dest, join_type='INNER', on=None, attr=None)

      :param src: Source for join.
      :param dest: Table to join to.

      Use same parameter order as the non-model-specific
      :meth:`~ModelSelect.join`. Bypasses the *join context* by requiring
      the join source to be specified.

   .. method:: filter(*args, **kwargs)

      :param args: Zero or more :class:`DQ` objects.
      :param kwargs: Django-style keyword-argument filters.

      Use Django-style filters to express a WHERE clause. Joins can be
      followed by chaining foreign-key fields. The supported operations are:

      * ``eq`` - equals
      * ``ne`` - not equals
      * ``lt``, ``lte`` - less-than, less-than or equal-to
      * ``gt``, ``gte`` - greater-than, greater-than or equal-to
      * ``in`` - IN set of values
      * ``is`` - IS (e.g. IS NULL).
      * ``like``, ``ilike`` - LIKE and ILIKE (case-insensitive)
      * ``regexp`` - regular expression match

      Examples:

      .. code-block:: python

         # Get all tweets by user with username="peewee".
         q = Tweet.filter(user__username='peewee')

         # Get all posts that are draft or published, and written after 2023.
         q = Post.filter(
             (DQ(status='draft') | DQ(status='published')),
             timestamp__gte=datetime.date(2023, 1, 1))

   .. method:: prefetch(*subqueries, prefetch_type=PREFETCH_TYPE.WHERE)

      :param subqueries: A list of :class:`Model` classes or select
          queries to prefetch.
      :param prefetch_type: Query type to use for the subqueries.
      :return: a list of models with selected relations prefetched.

      Execute the query, prefetching the given additional resources.

      Prefetch type may be one of:

      * ``PREFETCH_TYPE.WHERE``
      * ``PREFETCH_TYPE.JOIN``

      See also :func:`prefetch` standalone function.

      Example:

      .. code-block:: python

         # Fetch all Users and prefetch their associated tweets.
         query = User.select().prefetch(Tweet)
         for user in query:
             print(user.username)
             for tweet in user.tweets:
                 print('  *', tweet.content)

      .. note::
         Because ``prefetch`` must reconstruct a graph of models, it is
         necessary to be sure that the foreign-key/primary-key of any
         related models are selected, so that the related objects can be
         mapped correctly.


.. class:: DoesNotExist(Exception)

   Base exception class raised when a call to :meth:`Model.get` (or other
   ``.get()`` method) fails to return a matching result. Model classes have a
   model-specific subclass as a top-level attribute:

   .. code-block:: python

      def get_user(email):
          try:
              return User.get(fn.LOWER(User.email) == email.lower())
          except User.DoesNotExist:
              return None


.. _fields-api:

Fields
------

.. class:: Field(null=False, index=False, unique=False, column_name=None, default=None, primary_key=False, constraints=None, sequence=None, collation=None, unindexed=False, choices=None, help_text=None, verbose_name=None, index_type=None)

   :param bool null: Field allows NULLs.
   :param bool index: Create an index on field.
   :param bool unique: Create a unique index on field.
   :param str column_name: Specify column name for field.
   :param default: Default value (enforced in Python, not on server).
   :param bool primary_key: Field is the primary key.
   :param list constraints: List of constraints to apply to column, for
       example: ``[Check('price > 0')]``.
   :param str sequence: Sequence name for field.
   :param str collation: Collation name for field.
   :param bool unindexed: Declare field UNINDEXED (sqlite only).
   :param list choices: An iterable of 2-tuples mapping column values to
       display labels. Used for metadata purposes only, to help when
       displaying a dropdown of choices for field values, for example.
   :param str help_text: Help-text for field, metadata purposes only.
   :param str verbose_name: Verbose name for field, metadata purposes only.
   :param str index_type: Specify index type (postgres only), e.g. 'BRIN'.

   Fields on a :class:`Model` are analogous to columns on a table.

   .. attribute:: field_type = '<some field type>'

      Attribute used to map this field to a column type, e.g. "INT". See
      the ``FIELD`` object in the source for more information.

   .. attribute:: column

      Retrieve a reference to the underlying :class:`Column` object.

   .. attribute:: model

      The model the field is bound to.

   .. attribute:: name

      The name of the field.

   .. method:: db_value(value)

      Coerce a Python value into a value suitable for storage in the
      database. Sub-classes operating on special data-types will most likely
      want to override this method.

   .. method:: python_value(value)

      Coerce a value from the database into a Python object. Sub-classes
      operating on special data-types will most likely want to override this
      method.

   .. method:: coerce(value)

      This method is a shorthand that is used, by default, by both
      :meth:`~Field.db_value` and :meth:`~Field.python_value`.

      :param value: arbitrary data from app or backend
      :rtype: python data type

.. class:: IntegerField

   Field class for storing integers.

.. class:: BigIntegerField

   Field class for storing big integers (if supported by database).

.. class:: SmallIntegerField

   Field class for storing small integers (if supported by database).

.. class:: AutoField

   Field class for storing auto-incrementing primary keys.

   .. note::
      In SQLite, for performance reasons, the default primary key type simply
      uses the max existing value + 1 for new values, as opposed to the max
      ever value + 1. This means deleted records can have their primary keys
      reused. In conjunction with SQLite having foreign keys disabled by
      default (meaning ON DELETE is ignored, even if you specify it
      explicitly), this can lead to surprising and dangerous behaviour. To
      avoid this, you may want to use one or both of
      :class:`AutoIncrementField` and ``pragmas=[('foreign_keys', 'on')]``
      when you instantiate :class:`SqliteDatabase`.

.. class:: BigAutoField

   Field class for storing auto-incrementing primary keys using 64-bits.

.. class:: IdentityField(generate_always=False)

   :param bool generate_always: if specified, then the identity will always be
       generated (and specifying the value explicitly during INSERT will raise
       a programming error). Otherwise, the identity value is only generated
       as-needed.

   Field class for storing auto-incrementing primary keys using the
   Postgresql *IDENTITY* column type. The column definition ends up looking
   like this:

   .. code-block:: python

      id = IdentityField()
      # "id" INT GENERATED BY DEFAULT AS IDENTITY NOT NULL PRIMARY KEY

   .. attention:: Requires Postgresql >= 10

.. class:: FloatField

   Field class for storing floating-point numbers.

.. class:: DoubleField

   Field class for storing double-precision floating-point numbers.

.. class:: DecimalField(max_digits=10, decimal_places=5, auto_round=False, rounding=None, **kwargs)

   :param int max_digits: Maximum digits to store.
   :param int decimal_places: Maximum precision.
   :param bool auto_round: Automatically round values.
   :param rounding: Defaults to ``decimal.DefaultContext.rounding``.

    Field class for storing decimal numbers. Values are represented as
    ``decimal.Decimal`` objects.

.. class:: CharField(max_length=255)

   Field class for storing strings.

   .. note:: Values that exceed length are NOT truncated automatically.

.. class:: FixedCharField

   Field class for storing fixed-length strings.

   .. note:: Values that exceed length are not truncated automatically.

.. class:: TextField

   Field class for storing text.

.. class:: BlobField

   Field class for storing binary data.

.. class:: BitField

   Field class for storing options in a 64-bit integer column.

   Usage:

   .. code-block:: python

      class Post(Model):
          content = TextField()
          flags = BitField()

          is_favorite = flags.flag(1)
          is_sticky = flags.flag(2)
          is_minimized = flags.flag(4)
          is_deleted = flags.flag(8)

      >>> p = Post()
      >>> p.is_sticky = True
      >>> p.is_minimized = True
      >>> print(p.flags)  # Prints 4 | 2 --> "6"
      6
      >>> p.is_favorite
      False
      >>> p.is_sticky
      True

   We can use the flags on the Post class to build expressions in queries as
   well:

   .. code-block:: python

      # Generates a WHERE clause that looks like:
      # WHERE (post.flags & 1 != 0)
      query = Post.select().where(Post.is_favorite)

      # Query for sticky + favorite posts:
      query = Post.select().where(Post.is_sticky & Post.is_favorite)

   When bulk-updating one or more bits in a :class:`BitField`, you can use
   bitwise operators to set or clear one or more bits:

   .. code-block:: python

      # Set the 4th bit on all Post objects.
      Post.update(flags=Post.flags | 8).execute()

      # Clear the 1st and 3rd bits on all Post objects.
      Post.update(flags=Post.flags & ~(1 | 4)).execute()

   For simple operations, the flags provide handy ``set()`` and ``clear()``
   methods for setting or clearing an individual bit:

   .. code-block:: python

      # Set the "is_deleted" bit on all posts.
      Post.update(flags=Post.is_deleted.set()).execute()

      # Clear the "is_deleted" bit on all posts.
      Post.update(flags=Post.is_deleted.clear()).execute()

   .. method:: flag(value=None)

      :param int value: Value associated with flag, typically a power of 2.

      Returns a descriptor that can get or set specific bits in the overall
      value. When accessed on the class itself, it returns a
      :class:`Expression` object suitable for use in a query.

      If the value is not provided, it is assumed that each flag will be an
      increasing power of 2, so if you had four flags, they would have the
      values 1, 2, 4, 8.

.. class:: BigBitField

   Field class for storing arbitrarily-large bitmaps in a ``BLOB``. The field
   will grow the underlying buffer as necessary, ensuring there are enough
   bytes of data to support the number of bits of data being stored.

   Example usage:

   .. code-block:: python

      class Bitmap(Model):
          data = BigBitField()

      bitmap = Bitmap()

      # Sets the ith bit, e.g. the 1st bit, the 11th bit, the 63rd, etc.
      bits_to_set = (1, 11, 63, 31, 55, 48, 100, 99)
      for bit_idx in bits_to_set:
          bitmap.data.set_bit(bit_idx)

      # We can test whether a bit is set using "is_set":
      assert bitmap.data.is_set(11)
      assert not bitmap.data.is_set(12)

      # We can clear a bit:
      bitmap.data.clear_bit(11)
      assert not bitmap.data.is_set(11)

      # We can also "toggle" a bit. Recall that the 63rd bit was set earlier.
      assert bitmap.data.toggle_bit(63) is False
      assert bitmap.data.toggle_bit(63) is True
      assert bitmap.data.is_set(63)

      # BigBitField supports item accessor by bit-number, e.g.:
      assert bitmap.data[63]
      bitmap.data[0] = 1
      del bitmap.data[0]

      # We can also combine bitmaps using bitwise operators, e.g.
      b = Bitmap(data=b'\x01')
      b.data |= b'\x02'
      assert list(b.data) == [1, 1, 0, 0, 0, 0, 0, 0]
      assert len(b.data) == 1

   .. method:: clear()

      Clears the bitmap and sets length to 0.

   .. method:: set_bit(idx)

      :param int idx: Bit to set, indexed starting from zero.

      Sets the *idx*-th bit in the bitmap.

   .. method:: clear_bit(idx)

      :param int idx: Bit to clear, indexed starting from zero.

      Clears the *idx*-th bit in the bitmap.

   .. method:: toggle_bit(idx)

      :param int idx: Bit to toggle, indexed starting from zero.
      :return: Whether the bit is set or not.

      Toggles the *idx*-th bit in the bitmap and returns whether the bit is
      set or not.

      Example:

      .. code-block:: pycon

          >>> bitmap = Bitmap()
          >>> bitmap.data.toggle_bit(10)  # Toggle the 10th bit.
          True
          >>> bitmap.data.toggle_bit(10)  # This will clear the 10th bit.
          False

   .. method:: is_set(idx)

      :param int idx: Bit index, indexed starting from zero.
      :return: Whether the bit is set or not.

      Returns boolean indicating whether the *idx*-th bit is set or not.

   .. method:: __getitem__(idx)

      Same as :meth:`~BigBitField.is_set`

   .. method:: __setitem__(idx, value)

      Set the bit at ``idx`` to value (True or False).

   .. method:: __delitem__(idx)

      Same as :meth:`~BigBitField.clear_bit`

   .. method:: __len__()

      Return the length of the bitmap **in bytes**.

   .. method:: __iter__()

      Returns an iterator yielding 1 or 0 for each bit in the bitmap.

   .. method:: __and__(other)

      :param other: Either :class:`BigBitField`, ``bytes``, ``bytearray``
          or ``memoryview`` object.
      :return: bitwise ``and`` of two bitmaps.

   .. method:: __or__(other)

      :param other: Either :class:`BigBitField`, ``bytes``, ``bytearray``
          or ``memoryview`` object.
      :return: bitwise ``or`` of two bitmaps.

   .. method:: __xor__(other)

      :param other: Either :class:`BigBitField`, ``bytes``, ``bytearray``
          or ``memoryview`` object.
      :return: bitwise ``xor`` of two bitmaps.


.. class:: UUIDField

   Field class for storing ``uuid.UUID`` objects. With Postgres, the
   underlying column's data-type will be *UUID*. Since SQLite and MySQL do not
   have a native UUID type, the UUID is stored as a *VARCHAR* instead.

.. class:: BinaryUUIDField

   Field class for storing ``uuid.UUID`` objects efficiently in 16-bytes. Uses
   the database's *BLOB* data-type (or *VARBINARY* in MySQL, or *BYTEA* in
   Postgres).

.. class:: DateTimeField(formats=None, **kwargs)

   :param list formats: A list of format strings to use when coercing a string
       to a date-time.

   Field class for storing ``datetime.datetime`` objects.

   Accepts a special parameter ``formats``, which contains a list of formats
   the datetime can be encoded with (for databases that do not have support
   for a native datetime data-type). The default supported formats are:

   .. code-block:: python

      '%Y-%m-%d %H:%M:%S.%f' # year-month-day hour-minute-second.microsecond
      '%Y-%m-%d %H:%M:%S' # year-month-day hour-minute-second
      '%Y-%m-%d' # year-month-day

   .. note::
      SQLite does not have a native datetime data-type, so datetimes are
      stored as strings. This is handled transparently by Peewee, but if you
      have pre-existing data you should ensure it is stored as
      ``YYYY-mm-dd HH:MM:SS`` or one of the other supported formats.

   .. attribute:: year

      Reference the year of the value stored in the column in a query.

      .. code-block:: python

         Blog.select().where(Blog.pub_date.year == 2018)

   .. attribute:: month

      Reference the month of the value stored in the column in a query.

   .. attribute:: day

      Reference the day of the value stored in the column in a query.

   .. attribute:: hour

      Reference the hour of the value stored in the column in a query.

   .. attribute:: minute

      Reference the minute of the value stored in the column in a query.

   .. attribute:: second

      Reference the second of the value stored in the column in a query.

   .. method:: to_timestamp()

      Method that returns a database-specific function call that will allow
      you to work with the given date-time value as a numeric timestamp. This
      can sometimes simplify tasks like date math in a compatible way.

      Example:

      .. code-block:: python

          # Find all events that are exactly 1 hour long.
          query = (Event
                   .select()
                   .where((Event.start.to_timestamp() + 3600) ==
                          Event.stop.to_timestamp())
                   .order_by(Event.start))

   .. method:: truncate(date_part)

      :param str date_part: year, month, day, hour, minute or second.
      :return: expression node to truncate date/time to given resolution.

      Truncates the value in the column to the given part. This method is
      useful for finding all rows within a given month, for instance.


.. class:: DateField(formats=None, **kwargs)

   :param list formats: A list of format strings to use when coercing a string
       to a date.

   Field class for storing ``datetime.date`` objects.

   Accepts a special parameter ``formats``, which contains a list of formats
   the datetime can be encoded with (for databases that do not have support
   for a native date data-type). The default supported formats are:

   .. code-block:: python

      '%Y-%m-%d' # year-month-day
      '%Y-%m-%d %H:%M:%S' # year-month-day hour-minute-second
      '%Y-%m-%d %H:%M:%S.%f' # year-month-day hour-minute-second.microsecond

   .. note::
      If the incoming value does not match a format, it is returned as-is.

   .. attribute:: year

      Reference the year of the value stored in the column in a query.

      .. code-block:: python

         Person.select().where(Person.dob.year == 1983)

   .. attribute:: month

      Reference the month of the value stored in the column in a query.

   .. attribute:: day

      Reference the day of the value stored in the column in a query.

   .. method:: to_timestamp()

      See :meth:`DateTimeField.to_timestamp`.

   .. method:: truncate(date_part)

      See :meth:`DateTimeField.truncate`. Note that only *year*, *month*,
      and *day* are meaningful for :class:`DateField`.


.. class:: TimeField(formats=None, **kwargs)

   :param list formats: A list of format strings to use when coercing a string
       to a time.

   Field class for storing ``datetime.time`` objects (not ``timedelta``).

   Accepts a special parameter ``formats``, which contains a list of formats
   the datetime can be encoded with (for databases that do not have support
   for a native time data-type). The default supported formats are:

   .. code-block:: python

      '%H:%M:%S.%f' # hour:minute:second.microsecond
      '%H:%M:%S' # hour:minute:second
      '%H:%M' # hour:minute
      '%Y-%m-%d %H:%M:%S.%f' # year-month-day hour-minute-second.microsecond
      '%Y-%m-%d %H:%M:%S' # year-month-day hour-minute-second

   .. note::
      If the incoming value does not match a format, it is returned as-is.

   .. attribute:: hour

      Reference the hour of the value stored in the column in a query.

      .. code-block:: python

         evening_events = Event.select().where(Event.time.hour > 17)

   .. attribute:: minute

      Reference the minute of the value stored in the column in a query.

   .. attribute:: second

      Reference the second of the value stored in the column in a query.

.. class:: TimestampField(resolution=1, utc=False, **kwargs)

   :param resolution: Can be provided as either a power of 10, or as an
       exponent indicating how many decimal places to store.
   :param bool utc: Treat timestamps as UTC.

   Field class for storing date-times as integer timestamps. Sub-second
   resolution is supported by multiplying by a power of 10 to get an integer.

   If the ``resolution`` parameter is ``0`` *or* ``1``, then the timestamp is
   stored using second resolution. A resolution between ``2`` and ``6`` is
   treated as the number of decimal places, e.g. ``resolution=3`` corresponds
   to milliseconds. Alternatively, the decimal can be provided as a multiple
   of 10, such that ``resolution=10`` will store 1/10th of a second
   resolution.

   The ``resolution`` parameter can be either 0-6 *or* 10, 100, etc up to
   1000000 (for microsecond resolution). This allows sub-second precision
   while still using an :class:`IntegerField` for storage. The default is
   second resolution.

   Also accepts a boolean parameter ``utc``, used to indicate whether the
   timestamps should be UTC. Default is ``False``.

   Finally, the field ``default`` is the current timestamp. If you do not want
   this behavior, then explicitly pass in ``default=None``.

.. class:: IPField

   Field class for storing IPv4 addresses efficiently (as integers).

.. class:: BooleanField

   Field class for storing boolean values.

.. class:: BareField(coerce=None, **kwargs)

   :param coerce: Optional function to use for converting raw values into a
       specific format.

   Field class that does not specify a data-type (**SQLite-only**).

   Since data-types are not enforced, you can declare fields without *any*
   data-type. It is also common for SQLite virtual tables to use meta-columns
   or untyped columns, so for those cases as well you may wish to use an
   untyped field.

   Accepts a special ``coerce`` parameter, a function that takes a value
   coming from the database and converts it into the appropriate Python type.

.. class:: ForeignKeyField(model, field=None, backref=None, on_delete=None, on_update=None, deferrable=None, object_id_name=None, lazy_load=True, constraint_name=None, **kwargs)

   :param Model model: Model to reference or the string 'self' if declaring a
       self-referential foreign key.
   :param Field field: Field to reference on ``model`` (default is primary
       key).
   :param str backref: Accessor name for back-reference, or "+" to disable
       the back-reference accessor.
   :param str on_delete: ON DELETE action, e.g. ``'CASCADE'``..
   :param str on_update: ON UPDATE action.
   :param str deferrable: Control when constraint is enforced, e.g. ``'INITIALLY DEFERRED'``.
   :param str object_id_name: Name for object-id accessor.
   :param bool lazy_load: Fetch the related object when the foreign-key field
       attribute is accessed (if it was not already loaded). If this is
       disabled, accessing the foreign-key field will return the value stored
       in the foreign-key column.
   :param str constraint_name: (optional) name to use for foreign-key constraint.

   Field class for storing a foreign key.

   .. code-block:: python

      class User(Model):
          name = TextField()

      class Tweet(Model):
          user = ForeignKeyField(User, backref='tweets')
          content = TextField()

      # "user" attribute
      >>> some_tweet.user
      <User: charlie>

      # "tweets" backref attribute
      >>> for tweet in charlie.tweets:
      ...     print(tweet.content)
      Some tweet
      Another tweet
      Yet another tweet

   For an in-depth discussion of foreign-keys, joins and relationships between
   models, refer to :ref:`relationships`.

   .. note::
      Foreign keys do not have a particular ``field_type`` as they will take
      their field type depending on the type of primary key on the model they
      are related to.

   .. note::
      If you manually specify a ``field``, that field must be either a
      primary key or have a unique constraint.

   .. note::
      Take care with foreign keys in SQLite. By default, ON DELETE has no
      effect, which can have surprising (and usually unwanted) effects on
      your database integrity. This can affect you even if you don't specify
      ``on_delete``, since the default ON DELETE behaviour (to fail without
      modifying your data) does not happen, and your data can be silently
      relinked. The safest thing to do is to specify
      ``pragmas={'foreign_keys': 1}`` when you instantiate
      :class:`SqliteDatabase`.

.. class:: DeferredForeignKey(rel_model_name, **kwargs)

   :param str rel_model_name: Model name to reference.

   Field class for representing a deferred foreign key. Useful for circular
   foreign-key references, for example:

   .. code-block:: python

      class Husband(Model):
          name = TextField()
          wife = DeferredForeignKey('Wife', deferrable='INITIALLY DEFERRED')

      class Wife(Model):
          name = TextField()
          husband = ForeignKeyField(Husband, deferrable='INITIALLY DEFERRED')

   In the above example, when the ``Wife`` model is declared, the foreign-key
   ``Husband.wife`` is automatically resolved and turned into a regular
   :class:`ForeignKeyField`.

   .. warning::
      :class:`DeferredForeignKey` references are resolved when model
      classes are declared and created. This means that if you declare a
      :class:`DeferredForeignKey` to a model class that has already been
      imported and created, the deferred foreign key instance will never be
      resolved. For example:

      .. code-block:: python

         class User(Model):
             username = TextField()

         class Tweet(Model):
             # This will never actually be resolved, because the User
             # model has already been declared.
             user = DeferredForeignKey('user', backref='tweets')
             content = TextField()

      In cases like these you should use the regular
      :class:`ForeignKeyField` *or* you can manually resolve deferred
      foreign keys like so:

      .. code-block:: python

         # Tweet.user will be resolved into a ForeignKeyField:
         DeferredForeignKey.resolve(User)

.. class:: ManyToManyField(model, backref=None, through_model=None, on_delete=None, on_update=None)

   :param Model model: Model to create relationship with.
   :param str backref: Accessor name for back-reference
   :param Model through_model: :class:`Model` to use for the intermediary
       table. If not provided, a simple through table will be automatically
       created.
   :param str on_delete: ON DELETE action, e.g. ``'CASCADE'``. Will be used
       for foreign-keys in through model.
   :param str on_update: ON UPDATE action. Will be used for foreign-keys in
       through model.

   The :class:`ManyToManyField` provides a simple interface for working
   with many-to-many relationships, inspired by Django. A many-to-many
   relationship is typically implemented by creating a junction table with
   foreign keys to the two models being related. For instance, if you were
   building a syllabus manager for college students, the relationship between
   students and courses would be many-to-many. Here is the schema using
   standard APIs:

   .. attention::
      This is not a field in the sense that there is no column associated
      with it. Rather, it provides a convenient interface for accessing rows
      of data related via a through model.

   Standard way of declaring a many-to-many relationship (without the use of
   the :class:`ManyToManyField`):

   .. code-block:: python

      class Student(Model):
          name = CharField()

      class Course(Model):
          name = CharField()

      class StudentCourse(Model):
          student = ForeignKeyField(Student)
          course = ForeignKeyField(Course)

   To query the courses for a particular student, you would join through the
   junction table:

   .. code-block:: python

      # List the courses that "Huey" is enrolled in:
      courses = (Course
                 .select()
                 .join(StudentCourse)
                 .join(Student)
                 .where(Student.name == 'Huey'))
      for course in courses:
          print(course.name)

   The :class:`ManyToManyField` is designed to simplify this use-case by
   providing a *field-like* API for querying and modifying data in the
   junction table. Here is how our code looks using
   :class:`ManyToManyField`:

   .. code-block:: python

      class Student(Model):
          name = CharField()

      class Course(Model):
          name = CharField()
          students = ManyToManyField(Student, backref='courses')

   .. note::
      It does not matter from Peewee's perspective which model the
      :class:`ManyToManyField` goes on, since the back-reference is just
      the mirror image. In order to write valid Python, though, you will need
      to add the ``ManyToManyField`` on the second model so that the name of
      the first model is in the scope.

   We still need a junction table to store the relationships between students
   and courses. This model can be accessed by calling the
   :meth:`~ManyToManyField.get_through_model` method. This is useful when
   creating tables.

   .. code-block:: python

      # Create tables for the students, courses, and relationships between
      # the two.
      db.create_tables([
          Student,
          Course,
          Course.students.get_through_model()])

   When accessed from a model instance, the :class:`ManyToManyField`
   exposes a :class:`ModelSelect` representing the set of related objects.
   Let's use the interactive shell to see how all this works:

   .. code-block:: pycon

      >>> huey = Student.get(Student.name == 'huey')
      >>> [course.name for course in huey.courses]
      ['English 101', 'CS 101']

      >>> engl_101 = Course.get(Course.name == 'English 101')
      >>> [student.name for student in engl_101.students]
      ['Huey', 'Mickey', 'Zaizee']

   To add new relationships between objects, you can either assign the objects
   directly to the ``ManyToManyField`` attribute, or call the
   :meth:`~ManyToManyField.add` method. The difference between the two is
   that simply assigning will clear out any existing relationships, whereas
   ``add()`` can preserve existing relationships.

   .. code-block:: pycon

      >>> huey.courses = Course.select().where(Course.name.contains('english'))
      >>> for course in huey.courses.order_by(Course.name):
      ...     print(course.name)
      English 101
      English 151
      English 201
      English 221

      >>> cs_101 = Course.get(Course.name == 'CS 101')
      >>> cs_151 = Course.get(Course.name == 'CS 151')
      >>> huey.courses.add([cs_101, cs_151])
      >>> [course.name for course in huey.courses.order_by(Course.name)]
      ['CS 101', 'CS151', 'English 101', 'English 151', 'English 201',
       'English 221']

   This is quite a few courses, so let's remove the 200-level english courses.
   To remove objects, use the :meth:`~ManyToManyField.remove` method.

   .. code-block:: pycon

      >>> huey.courses.remove(Course.select().where(Course.name.contains('2'))
      2
      >>> [course.name for course in huey.courses.order_by(Course.name)]
      ['CS 101', 'CS151', 'English 101', 'English 151']

   To remove all relationships from a collection, you can use the
   :meth:`~SelectQuery.clear` method. Let's say that English 101 is
   canceled, so we need to remove all the students from it:

   .. code-block:: pycon

      >>> engl_101 = Course.get(Course.name == 'English 101')
      >>> engl_101.students.clear()

   .. note::
      For an overview of implementing many-to-many relationships using
      standard Peewee APIs, check out the :ref:`manytomany` section. For all
      but the most simple cases, you will be better off implementing
      many-to-many using the standard APIs.

   .. attribute:: through_model

      The :class:`Model` representing the many-to-many junction table.
      Will be auto-generated if not explicitly declared.

   .. method:: add(value, clear_existing=True)

      :param value: Either a :class:`Model` instance, a list of model
          instances, or a :class:`SelectQuery`.
      :param bool clear_existing: Whether to remove existing relationships.

      Associate ``value`` with the current instance. You can pass in a single
      model instance, a list of model instances, or even a :class:`ModelSelect`.

      Example code:

      .. code-block:: python

         # Huey needs to enroll in a bunch of courses, including all
         # the English classes, and a couple Comp-Sci classes.
         huey = Student.get(Student.name == 'Huey')

         # We can add all the objects represented by a query.
         english_courses = Course.select().where(
             Course.name.contains('english'))
         huey.courses.add(english_courses)

         # We can also add lists of individual objects.
         cs101 = Course.get(Course.name == 'CS 101')
         cs151 = Course.get(Course.name == 'CS 151')
         huey.courses.add([cs101, cs151])

   .. method:: remove(value)

      :param value: Either a :class:`Model` instance, a list of model
          instances, or a :class:`ModelSelect`.

      Disassociate ``value`` from the current instance. Like
      :meth:`~ManyToManyField.add`, you can pass in a model instance, a
      list of model instances, or even a :class:`ModelSelect`.

      Example code:

      .. code-block:: python

         # Huey is currently enrolled in a lot of english classes
         # as well as some Comp-Sci. He is changing majors, so we
         # will remove all his courses.
         english_courses = Course.select().where(
             Course.name.contains('english'))
         huey.courses.remove(english_courses)

         # Remove the two Comp-Sci classes Huey is enrolled in.
         cs101 = Course.get(Course.name == 'CS 101')
         cs151 = Course.get(Course.name == 'CS 151')
         huey.courses.remove([cs101, cs151])

   .. method:: clear()

      Remove all associated objects.

      Example code:

      .. code-block:: python

         # English 101 is canceled this semester, so remove all
         # the enrollments.
         english_101 = Course.get(Course.name == 'English 101')
         english_101.students.clear()

   .. method:: get_through_model()

      Return the :class:`Model` representing the many-to-many junction
      table. This can be specified manually when the field is being
      instantiated using the ``through_model`` parameter. If a
      ``through_model`` is not specified, one will automatically be created.

      When creating tables for an application that uses
      :class:`ManyToManyField`, **you must explicitly create the through table**.

      .. code-block:: python

         # Get a reference to the automatically-created through table.
         StudentCourseThrough = Course.students.get_through_model()

         # Create tables for our two models as well as the through model.
         db.create_tables([
             Student,
             Course,
             StudentCourseThrough])

.. class:: DeferredThroughModel()

   Place-holder for a through-model in cases where, due to a dependency, you
   cannot declare either a model or a many-to-many field without introducing
   NameErrors.

   Example:

   .. code-block:: python

      class Note(BaseModel):
          content = TextField()

      NoteThroughDeferred = DeferredThroughModel()

      class User(BaseModel):
          username = TextField()
          notes = ManyToManyField(Note, through_model=NoteThroughDeferred)

      # Cannot declare this before "User" since it has a foreign-key to
      # the User model.
      class NoteThrough(BaseModel):
          note = ForeignKeyField(Note)
          user = ForeignKeyField(User)

      # Resolve dependencies.
      NoteThroughDeferred.set_model(NoteThrough)

.. class:: CompositeKey(*field_names)

   :param field_names: Names of fields that comprise the primary key.

   A primary key composed of multiple columns. Unlike the other fields, a
   composite key is defined in the model's ``Meta`` class after the fields
   have been defined. It takes as parameters the string names of the fields to
   use as the primary key:

   .. code-block:: python

      class BlogTagThrough(Model):
          blog = ForeignKeyField(Blog, backref='tags')
          tag = ForeignKeyField(Tag, backref='blogs')

          class Meta:
              primary_key = CompositeKey('blog', 'tag')

   See :ref:`composite-keys` for additional discussion.


.. _schema-manager-api:

Schema Manager
--------------

.. class:: SchemaManager(model, database=None, **context_options)

   :param Model model: Model class.
   :param Database database: if ``None`` defaults to model._meta.database.

   Provides methods for managing the creation and deletion of tables and
   indexes for the given model.

   .. method:: create_table(safe=True, **options)

      :param bool safe: Specify IF NOT EXISTS clause.
      :param options: Arbitrary options.

      Execute CREATE TABLE query for the given model.

   .. method:: drop_table(safe=True, drop_sequences=True, **options)

      :param bool safe: Specify IF EXISTS clause.
      :param bool drop_sequences: Drop any sequences associated with the
          columns on the table (postgres only).
      :param options: Arbitrary options.

      Execute DROP TABLE query for the given model.

   .. method:: truncate_table(restart_identity=False, cascade=False)

      :param bool restart_identity: Restart the id sequence (postgres-only).
      :param bool cascade: Truncate related tables as well (postgres-only).

      Execute TRUNCATE TABLE for the given model. If the database is Sqlite,
      which does not support TRUNCATE, then an equivalent DELETE query will
      be executed.

   .. method:: create_indexes(safe=True)

      :param bool safe: Specify IF NOT EXISTS clause.

      Execute CREATE INDEX queries for the indexes defined for the model.

   .. method:: drop_indexes(safe=True)

      :param bool safe: Specify IF EXISTS clause.

      Execute DROP INDEX queries for the indexes defined for the model.

   .. method:: create_sequence(field)

      :param Field field: Field instance which specifies a sequence.

      Create sequence for the given :class:`Field`.

   .. method:: drop_sequence(field)

      :param Field field: Field instance which specifies a sequence.

      Drop sequence for the given :class:`Field`.

   .. method:: create_foreign_key(field)

      :param ForeignKeyField field: Foreign-key field constraint to add.

      Add a foreign-key constraint for the given field. This method should
      not be necessary in most cases, as foreign-key constraints are created
      as part of table creation. The exception is when you are creating a
      circular foreign-key relationship using :class:`DeferredForeignKey`.
      In those cases, it is necessary to first create the tables, then add
      the constraint for the deferred foreign-key:

      .. code-block:: python

         class Language(Model):
             name = TextField()
             selected_snippet = DeferredForeignKey('Snippet')

         class Snippet(Model):
             code = TextField()
             language = ForeignKeyField(Language, backref='snippets')

         # Creates both tables but does not create the constraint for the
         # Language.selected_snippet foreign key (because of the circular
         # dependency).
         db.create_tables([Language, Snippet])

         # Explicitly create the constraint:
         Language._schema.create_foreign_key(Language.selected_snippet)

      For more information, see documentation on :ref:`circular-fks`.

      .. warning::
         Because SQLite has limited support for altering existing tables, it
         is not possible to add a foreign-key constraint to an existing
         SQLite table.

   .. method:: create_all(safe=True, **table_options)

      :param bool safe: Whether to specify IF NOT EXISTS.

      Create sequence(s), index(es) and table for the model.

   .. method:: drop_all(safe=True, drop_sequences=True, **options)

      :param bool safe: Whether to specify IF EXISTS.
      :param bool drop_sequences: Drop any sequences associated with the
          columns on the table (postgres only).
      :param options: Arbitrary options.

      Drop table for the model and associated indexes.


.. class:: Index(name, table, expressions, unique=False, safe=False, where=None, using=None, nulls_distinct=None)

   :param str name: Index name.
   :param Table table: Table to create index on.
   :param expressions: List of columns to index on (or expressions).
   :param bool unique: Whether index is UNIQUE.
   :param bool safe: Whether to add IF NOT EXISTS clause.
   :param Expression where: Optional WHERE clause for index.
   :param str using: Index algorithm.
   :param bool nulls_distinct: Postgres-only - specify True (NULLS DISTINCT)
       or False (NULLS NOT DISTINCT) - controls handling of NULL in unique
       indexes.

   .. method:: safe(_safe=True)

      :param bool _safe: Whether to add IF NOT EXISTS clause.

   .. method:: where(*expressions)

      :param expressions: zero or more expressions to include in the WHERE
          clause.

      Include the given expressions in the WHERE clause of the index. The
      expressions will be AND-ed together with any previously-specified
      WHERE expressions.

   .. method:: using(_using=None)

      :param str _using: Specify index algorithm for USING clause.

   .. method:: nulls_distinct(nulls_distinct=None)

      :param bool nulls_distinct: specify True (NULLS DISTINCT) or False
          for (NULLS NOT DISTINCT).

      Requires Postgres 15 or newer.

      Control handling of NULL values in unique indexes.


.. class:: ModelIndex(model, fields, unique=False, safe=True, where=None, using=None, name=None, nulls_distinct=None)

   :param Model model: Model class to create index on.
   :param list fields: Fields to index.
   :param bool unique: Whether index is UNIQUE.
   :param bool safe: Whether to add IF NOT EXISTS clause.
   :param Expression where: Optional WHERE clause for index.
   :param str using: Index algorithm or type, e.g. 'BRIN', 'GiST' or 'GIN'.
   :param str name: Optional index name.
   :param bool nulls_distinct: Postgres-only - specify True (NULLS DISTINCT)
       or False (NULLS NOT DISTINCT) - controls handling of NULL in unique
       indexes.

   Expressive method for declaring an index on a model.

   Examples:

   .. code-block:: python

      class Article(Model):
          name = TextField()
          timestamp = TimestampField()
          status = IntegerField()
          flags = BitField()

          is_sticky = flags.flag(1)
          is_favorite = flags.flag(2)

      # CREATE INDEX ... ON "article" ("name", "timestamp")
      idx = ModelIndex(Article, (Article.name, Article.timestamp))

      # CREATE INDEX ... ON "article" ("name", "timestamp") WHERE "status" = 1
      idx = idx.where(Article.status == 1)

      # CREATE UNIQUE INDEX ... ON "article" ("timestamp" DESC, "flags" & 2) WHERE "status" = 1
      idx = ModelIndex(
          Article,
          (Article.timestamp.desc(), Article.flags.bin_and(2)),
          unique = True).where(Article.status == 1)

   You can also use :meth:`Model.index`:

   .. code-block:: python

      idx = Article.index(Article.name, Article.timestamp).where(Article.status == 1)

   To add an index to a model definition use :meth:`Model.add_index`:

   .. code-block:: python

      idx = Article.index(Article.name, Article.timestamp).where(Article.status == 1)

      # Add above index definition to the model definition. When you call
      # Article.create_table() (or database.create_tables([Article])), the
      # index will be created.
      Article.add_index(idx)


.. _query-builder-api:

Query-builder
-------------

.. seealso: :ref:`query-builder`

.. class:: Node()

   Base-class for all components which make up the AST for a SQL query.

   .. staticmethod:: copy(method)

      Decorator to use with Node methods that mutate the node's state.
      This allows method-chaining, e.g.:

      .. code-block:: python

          query = MyModel.select()
          new_query = query.where(MyModel.field == 'value')

   .. method:: unwrap()

      API for recursively unwrapping "wrapped" nodes. Base case is to
      return self.

   .. method:: is_alias()

      API for determining if a node, at any point, has been explicitly
      aliased by the user.


.. class:: Source(alias=None)

   A source of row tuples, for example a table, join, or select query. By
   default provides a "magic" attribute named "c" that is a factory for
   column/attribute lookups, for example:

   .. code-block:: python

      User = Table('users')
      query = (User
               .select(User.c.username)
               .where(User.c.active == True)
               .order_by(User.c.username))

   .. method:: alias(name)

      Returns a copy of the object with the given alias applied.

   .. method:: select(*columns)

      :param columns: :class:`Column` instances, expressions, functions,
          sub-queries, or anything else that you would like to select.

      Create a :class:`Select` query on the table. If the table explicitly
      declares columns and no columns are provided, then by default all the
      table's defined columns will be selected.

   .. method:: join(dest, join_type='INNER', on=None)

      :param Source dest: Join the table with the given destination.
      :param str join_type: Join type.
      :param on: Expression to use as join predicate.
      :return: a :class:`Join` instance.

      Join type may be one of:

      * ``JOIN.INNER``
      * ``JOIN.LEFT_OUTER``
      * ``JOIN.RIGHT_OUTER``
      * ``JOIN.FULL``
      * ``JOIN.FULL_OUTER``
      * ``JOIN.CROSS``

   .. method:: left_outer_join(dest, on=None)

      :param Source dest: Join the table with the given destination.
      :param on: Expression to use as join predicate.
      :return: a :class:`Join` instance.

      Convenience method for calling :meth:`~Source.join` using a LEFT
      OUTER join.


.. class:: BaseTable()

   Base class for table-like objects, which support JOINs via operator
   overloading.

   .. method:: __and__(dest)

       Perform an INNER join on ``dest``.

   .. method:: __add__(dest)

       Perform a LEFT OUTER join on ``dest``.

   .. method:: __sub__(dest)

       Perform a RIGHT OUTER join on ``dest``.

   .. method:: __or__(dest)

       Perform a FULL OUTER join on ``dest``.

   .. method:: __mul__(dest)

       Perform a CROSS join on ``dest``.


.. class:: Table(name, columns=None, primary_key=None, schema=None, alias=None)

   Represents a table in the database (or a table-like object such as a view).

   :param str name: Database table name
   :param tuple columns: List of column names (optional).
   :param str primary_key: Name of primary key column.
   :param str schema: Schema name used to access table (if necessary).
   :param str alias: Alias to use for table in SQL queries.

   .. note::
      If columns are specified, the magic "c" attribute will be disabled.

   When columns are not explicitly defined, tables have a special attribute
   "c" which is a factory that provides access to table columns dynamically.

   Example:

   .. code-block:: python

      User = Table('users')
      query = (User
               .select(User.c.id, User.c.username)
               .order_by(User.c.username))

   Equivalent example when columns **are** specified:

   .. code-block:: python

      User = Table('users', ('id', 'username'))
      query = (User
               .select(User.id, User.username)
               .order_by(User.username))

   .. method:: bind(database=None)

      :param database: :class:`Database` object.

      Bind this table to the given database (or unbind by leaving empty).

      When a table is *bound* to a database, queries may be executed against
      it without the need to specify the database in the query's execute
      method.

   .. method:: bind_ctx(database=None)

      :param database: :class:`Database` object.

      Return a context manager that will bind the table to the given database
      for the duration of the wrapped block.

   .. method:: select(*columns)

      :param columns: :class:`Column` instances, expressions, functions,
          sub-queries, or anything else that you would like to select.

      Create a :class:`Select` query on the table. If the table explicitly
      declares columns and no columns are provided, then by default all the
      table's defined columns will be selected.

      Examples:

      .. code-block:: python

         User = Table('users', ('id', 'username'))

         # Because columns were defined on the Table, we will default to
         # selecting both of the User table's columns.
         # Evaluates to SELECT id, username FROM users
         query = User.select()

         Note = Table('notes')
         query = (Note
                  .select(Note.c.content, Note.c.timestamp, User.username)
                  .join(User, on=(Note.c.user_id == User.id))
                  .where(Note.c.is_published == True)
                  .order_by(Note.c.timestamp.desc()))

         # Using a function to select users and the number of notes they
         # have authored.
         query = (User
                  .select(
                     User.username,
                     fn.COUNT(Note.c.id).alias('n_notes'))
                  .join(
                     Note,
                     JOIN.LEFT_OUTER,
                     on=(User.id == Note.c.user_id))
                  .order_by(fn.COUNT(Note.c.id).desc()))

   .. method:: insert(insert=None, columns=None, **kwargs)

      :param insert: A dictionary mapping column to value, an iterable that
          yields dictionaries (i.e. list), or a :class:`Select` query.
      :param list columns: The list of columns to insert into when the
          data being inserted is not a dictionary.
      :param kwargs: Mapping of column-name to value.

      Create a :class:`Insert` query into the table.

   .. method:: replace(insert=None, columns=None, **kwargs)

      :param insert: A dictionary mapping column to value, an iterable that
          yields dictionaries (i.e. list), or a :class:`Select` query.
      :param list columns: The list of columns to insert into when the
          data being inserted is not a dictionary.
      :param kwargs: Mapping of column-name to value.

      Create a :class:`Insert` query into the table whose conflict
      resolution method is to replace.

   .. method:: update(update=None, **kwargs)

      :param update: A dictionary mapping column to value.
      :param kwargs: Mapping of column-name to value.

      Create a :class:`Update` query for the table.

   .. method:: delete()

      Create a :class:`Delete` query for the table.


.. class:: Join(lhs, rhs, join_type=JOIN.INNER, on=None, alias=None)

   Represent a JOIN between two table-like objects.

   :param lhs: Left-hand side of the join.
   :param rhs: Right-hand side of the join.
   :param join_type: Type of join. e.g. JOIN.INNER, JOIN.LEFT_OUTER, etc.
   :param on: Expression describing the join predicate.
   :param str alias: Alias to apply to joined data.

   .. method:: on(predicate)

       :param Expression predicate: join predicate.

       Specify the predicate expression used for this join.


.. class:: ValuesList(values, columns=None, alias=None)

   Represent a values list that can be used like a table.

   :param values: a list-of-lists containing the row data to represent.
   :param list columns: the names to give to the columns in each row.
   :param str alias: alias to use for values-list.

   Example:

   .. code-block:: python

      data = [(1, 'first'), (2, 'second')]
      vl = ValuesList(data, columns=('idx', 'name'))

      query = (vl
               .select(vl.c.idx, vl.c.name)
               .order_by(vl.c.idx))
      # Yields:
      # SELECT t1.idx, t1.name
      # FROM (VALUES (1, 'first'), (2, 'second')) AS t1(idx, name)
      # ORDER BY t1.idx

   .. method:: columns(*names)

      :param names: names to apply to the columns of data.

      Example:

      .. code-block:: python

         vl = ValuesList([(1, 'first'), (2, 'second')])
         vl = vl.columns('idx', 'name').alias('v')

         query = vl.select(vl.c.idx, vl.c.name)
         # Yields:
         # SELECT v.idx, v.name
         # FROM (VALUES (1, 'first'), (2, 'second')) AS v(idx, name)


.. class:: CTE(name, query, recursive=False, columns=None)

   Represent a common-table-expression. For example queries, see :ref:`cte`.

   :param name: Name for the CTE.
   :param query: :class:`Select` query describing CTE.
   :param bool recursive: Whether the CTE is recursive.
   :param list columns: Explicit list of columns produced by CTE (optional).

   .. method:: select_from(*columns)

      Create a SELECT query that utilizes the given common table expression
      as the source for a new query.

      :param columns: One or more columns to select from the CTE.
      :return: :class:`Select` query utilizing the common table expression

   .. method:: union_all(other)

      Used on the base-case CTE to construct the recursive term of the CTE.

      :param other: recursive term, generally a :class:`Select` query.
      :return: a recursive :class:`CTE` with the given recursive term.


.. class:: ColumnBase()

   Base-class for column-like objects, attributes or expressions.

   Column-like objects can be composed using various operators and special
   methods.

   * ``&``: Logical AND
   * ``|``: Logical OR
   * ``+``: Addition
   * ``-``: Subtraction
   * ``*``: Multiplication
   * ``/``: Division
   * ``^``: Exclusive-OR
   * ``==``: Equality
   * ``!=``: Inequality
   * ``>``: Greater-than
   * ``<``: Less-than
   * ``>=``: Greater-than or equal
   * ``<=``: Less-than or equal
   * ``<<``: ``IN``
   * ``>>``: ``IS`` (i.e. ``IS NULL``)
   * ``%``: ``LIKE``
   * ``**``: ``ILIKE``
   * ``bin_and()``: Binary AND
   * ``bin_or()``: Binary OR
   * ``in_()``: ``IN``
   * ``not_in()``: ``NOT IN``
   * ``regexp()``: ``REGEXP``
   * ``is_null(True/False)``: ``IS NULL`` or ``IS NOT NULL``
   * ``contains(s)``: ``LIKE %s%``
   * ``startswith(s)``: ``LIKE s%``
   * ``endswith(s)``: ``LIKE %s``
   * ``between(low, high)``: ``BETWEEN low AND high``
   * ``concat()``: ``||``

   .. method:: alias(alias)

      :param str alias: Alias for the given column-like object.
      :return: a :class:`Alias` object.

      Indicate the alias that should be given to the specified column-like
      object.

   .. method:: cast(as_type)

      :param str as_type: Type name to cast to.
      :return: a :class:`Cast` object.

      Create a ``CAST`` expression.

   .. method:: asc(collation=None, nulls=None)

      :param str collation: Collation name to use for sorting.
      :param str nulls: Sort nulls (FIRST or LAST).
      :return: an ascending :class:`Ordering` object for the column.

   .. method:: desc(collation=None, nulls=None)

      :param str collation: Collation name to use for sorting.
      :param str nulls: Sort nulls (FIRST or LAST).
      :return: an descending :class:`Ordering` object for the column.

   .. method:: __invert__()

      :return: a :class:`Negated` wrapper for the column.


.. class:: Column(source, name)

   :param Source source: Source for column.
   :param str name: Column name.

   Column on a table or a column returned by a sub-query.


.. class:: Alias(node, alias)

   :param Node node: a column-like object.
   :param str alias: alias to assign to column.

   Create a named alias for the given column-like object.

   .. method:: alias(alias=None)

      :param str alias: new name (or None) for aliased column.

      Create a new :class:`Alias` for the aliased column-like object. If
      the new alias is ``None``, then the original column-like object is
      returned.


.. class:: Negated(node)

   Represents a negated column-like object.


.. class:: Value(value, converter=None, unpack=True)

   :param value: Python object or scalar value.
   :param converter: Function used to convert value into type the database
       understands.
   :param bool unpack: Whether lists or tuples should be unpacked into a list
       of values or treated as-is.

   Value to be used in a parameterized query. It is the responsibility of the
   caller to ensure that the value passed in can be adapted to a type the
   database driver understands.


.. function:: AsIs(value, converter=None)

   Represents a :class:`Value` that is treated as-is, and passed directly
   back to the database driver. This may be useful if you are using database
   extensions that accept native Python data-types and you do not wish Peewee
   to impose any handling of the values.

   In the event a converter is in scope for this value, the converter will be
   applied unless ``converter=False`` (in which case no conversion is applied
   by Peewee and the value is passed directly to the driver). The Postgres JSON
   extensions make use of this to pass ``dict`` and ``list`` to the driver,
   which then handles the JSON serialization more efficiently, for example.


.. class:: Cast(node, cast)

   :param node: A column-like object.
   :param str cast: Type to cast to.

   Represents a ``CAST(<node> AS <cast>)`` expression.


.. class:: Ordering(node, direction, collation=None, nulls=None)

   :param node: A column-like object.
   :param str direction: ASC or DESC
   :param str collation: Collation name to use for sorting.
   :param str nulls: Sort nulls (FIRST or LAST).

   Represent ordering by a column-like object.

   Postgresql supports a non-standard clause ("NULLS FIRST/LAST"). Peewee will
   automatically use an equivalent ``CASE`` statement for databases that do
   not support this (Sqlite / MySQL).

   .. method:: collate(collation=None)

      :param str collation: Collation name to use for sorting.


.. function:: Asc(node, collation=None, nulls=None)

   Short-hand for instantiating an ascending :class:`Ordering` object.


.. function:: Desc(node, collation=None, nulls=None)

   Short-hand for instantiating an descending :class:`Ordering` object.


.. class:: Expression(lhs, op, rhs, flat=True)

   :param lhs: Left-hand side.
   :param op: Operation.
   :param rhs: Right-hand side.
   :param bool flat: Whether to wrap expression in parentheses.

   Represent a binary expression of the form (lhs op rhs), e.g. (foo + 1).


.. class:: Entity(*path)

   :param path: Components that make up the dotted-path of the entity name.

   Represent a quoted entity in a query, such as a table, column, alias. The
   name may consist of multiple components, e.g. "a_table"."column_name".

   .. method:: __getattr__(self, attr)

      Factory method for creating sub-entities.


.. class:: SQL(sql, params=None)

   :param str sql: SQL query string.
   :param tuple params: Parameters for query (optional).

   Represent a parameterized SQL query or query-fragment.


.. function:: Check(constraint, name=None)

   :param str constraint: Constraint SQL.
   :param str name: constraint name.

   Represent a CHECK constraint.

   .. warning::
      MySQL may not support a ``name`` parameter when inlining the
      constraint along with the column definition. The solution is to just
      put the named ``Check`` constraint in the model's ``Meta.constraints``
      list instead of in the field instances ``constraints=[...]`` list.


.. function:: Default(value)

   :param value: default value (literal).

   Represent a DEFAULT constraint. It is important to note that this
   constraint does not accept a parameterized value, so the value literal must
   be given. If a string value is intended, it must be quoted.

   Examples:

   .. code-block:: python

     # "added" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP.
     added = DateTimeField(constraints=[Default('CURRENT_TIMESTAMP')])

     # "label" TEXT NOT NULL DEFAULT 'string literal'
     label = TextField(constraints=[Default("'string literal'")])

     # "status" INTEGER NOT NULL DEFAULT 0
     status = IntegerField(constraints=[Default(0)])


.. class:: Function(name, arguments, coerce=True, python_value=None)

   :param str name: Function name.
   :param tuple arguments: Arguments to function.
   :param bool coerce: Whether to coerce the function result to a particular
       data-type when reading function return values from the cursor.
   :param callable python_value: Function to use for converting the return
       value from the cursor.

   Represent an arbitrary SQL function call.

   .. note::
      Rather than instantiating this class directly, it is recommended to use
      the ``fn`` helper.

   Example of using ``fn`` to call an arbitrary SQL function:

   .. code-block:: python

      # Query users and count of tweets authored.
      query = (User
               .select(User.username, fn.COUNT(Tweet.id).alias('ct'))
               .join(Tweet, JOIN.LEFT_OUTER, on=(User.id == Tweet.user_id))
               .group_by(User.username)
               .order_by(fn.COUNT(Tweet.id).desc()))

   .. method:: over(partition_by=None, order_by=None, start=None, end=None, window=None, exclude=None)

      :param list partition_by: List of columns to partition by.
      :param list order_by: List of columns / expressions to order window by.
      :param start: A :class:`SQL` instance or a string expressing the
          start of the window range.
      :param end: A :class:`SQL` instance or a string expressing the
          end of the window range.
      :param str frame_type: ``Window.RANGE``, ``Window.ROWS`` or
          ``Window.GROUPS``.
      :param Window window: A :class:`Window` instance.
      :param exclude: Frame exclusion, one of ``Window.CURRENT_ROW``,
          ``Window.GROUP``, ``Window.TIES`` or ``Window.NO_OTHERS``.

      .. note::
          For an in-depth guide to using window functions with Peewee,
          see the :ref:`window-functions` section.

      Examples:

      .. code-block:: python

         # Using a simple partition on a single column.
         query = (Sample
                  .select(
                     Sample.counter,
                     Sample.value,
                     fn.AVG(Sample.value).over([Sample.counter]))
                  .order_by(Sample.counter))

         # Equivalent example Using a Window() instance instead.
         window = Window(partition_by=[Sample.counter])
         query = (Sample
                  .select(
                     Sample.counter,
                     Sample.value,
                     fn.AVG(Sample.value).over(window))
                  .window(window)  # Note call to ".window()"
                  .order_by(Sample.counter))

         # Example using bounded window.
         query = (Sample
                  .select(Sample.value,
                          fn.SUM(Sample.value).over(
                             partition_by=[Sample.counter],
                             start=Window.CURRENT_ROW,  # current row
                             end=Window.following()))  # unbounded following
                  .order_by(Sample.id))

   .. method:: filter(where)

      :param where: Expression for filtering aggregate.

      Add a ``FILTER (WHERE...)`` clause to an aggregate function. The where
      expression is evaluated to determine which rows are fed to the
      aggregate function. This SQL feature is supported for Postgres and
      SQLite.

   .. method:: coerce(coerce=True)

      :param bool coerce: Whether to attempt to coerce function-call result
          to a Python data-type.

      When coerce is ``True``, the target data-type is inferred using several
      heuristics. Read the source for ``BaseModelCursorWrapper._initialize_columns``
      method to see how this works.

   .. method:: python_value(func=None)

      :param callable python_value: Function to use for converting the return
          value from the cursor.

      Specify a particular function to use when converting values returned by
      the database cursor. For example:

      .. code-block:: python

         # Get user and a list of their tweet IDs. The tweet IDs are
         # returned as a comma-separated string by the db, so we'll split
         # the result string and convert the values to python ints.
         convert_ids = lambda s: [int(i) for i in (s or '').split(',') if i]
         tweet_ids = (fn
                      .GROUP_CONCAT(Tweet.id)
                      .python_value(convert_ids))

         query = (User
                  .select(User.username, tweet_ids.alias('tweet_ids'))
                  .join(Tweet)
                  .group_by(User.username))

         for user in query:
             print(user.username, user.tweet_ids)

         # e.g.,
         # huey [1, 4, 5, 7]
         # mickey [2, 3, 6]
         # zaizee []

.. function:: fn()

   The :func:`fn` helper is actually an instance of :class:`Function`
   that implements a ``__getattr__`` hook to provide a nice API for calling
   SQL functions.

   To create a node representative of a SQL function call, use the function
   name as an attribute on ``fn`` and then provide the arguments as you would
   if calling a Python function:

   .. code-block:: python

      # List users and the number of tweets they have authored,
      # from highest-to-lowest:
      sql_count = fn.COUNT(Tweet.id)
      query = (User
               .select(User, sql_count.alias('count'))
               .join(Tweet, JOIN.LEFT_OUTER)
               .group_by(User)
               .order_by(sql_count.desc()))

      # Get the timestamp of the most recent tweet:
      query = Tweet.select(fn.MAX(Tweet.timestamp))
      max_timestamp = query.scalar()  # Retrieve scalar result from query.

   Function calls can, like anything else, be composed and nested:

   .. code-block:: python

      # Get users whose username begins with "A" or "a":
      a_users = User.select().where(fn.LOWER(fn.SUBSTR(User.username, 1, 1)) == 'a')


.. class:: Window(partition_by=None, order_by=None, start=None, end=None, frame_type=None, extends=None, exclude=None, alias=None)

   :param list partition_by: List of columns to partition by.
   :param list order_by: List of columns to order by.
   :param start: A :class:`SQL` instance or a string expressing the start
       of the window range.
   :param end: A :class:`SQL` instance or a string expressing the end of
       the window range.
   :param str frame_type: ``Window.RANGE``, ``Window.ROWS`` or
       ``Window.GROUPS``.
   :param extends: A :class:`Window` definition to extend. Alternately, you
       may specify the window's alias instead.
   :param exclude: Frame exclusion, one of ``Window.CURRENT_ROW``,
       ``Window.GROUP``, ``Window.TIES`` or ``Window.NO_OTHERS``.
   :param str alias: Alias for the window.

   Represent a WINDOW clause.

   .. note::
      For an in-depth guide to using window functions with Peewee,
      see the :ref:`window-functions` section.

   .. attribute:: RANGE
                  ROWS
                  GROUPS

      Specify the window ``frame_type``. See :ref:`window-frame-types`.

   .. attribute:: CURRENT_ROW

      Reference to current row for use in start/end clause or the frame
      exclusion parameter.

   .. attribute:: NO_OTHERS
                  GROUP
                  TIES

      Specify the window frame exclusion parameter.

   .. staticmethod:: preceding(value=None)

      :param value: Number of rows preceding. If ``None`` is UNBOUNDED.

      Convenience method for generating SQL suitable for passing in as the
      ``start`` parameter for a window range.

   .. staticmethod:: following(value=None)

      :param value: Number of rows following. If ``None`` is UNBOUNDED.

      Convenience method for generating SQL suitable for passing in as the
      ``end`` parameter for a window range.

   .. method:: as_rows()
               as_range()
               as_groups()

      Specify the frame type.

   .. method:: extends(window=None)

      :param Window window: A :class:`Window` definition to extend.
          Alternately, you may specify the window's alias instead.

   .. method:: exclude(frame_exclusion=None)

      :param frame_exclusion: Frame exclusion, one of ``Window.CURRENT_ROW``,
          ``Window.GROUP``, ``Window.TIES`` or ``Window.NO_OTHERS``.

   .. method:: alias(alias=None)

      :param str alias: Alias to use for window.


.. function:: Case(predicate, expression_tuples, default=None)

   :param predicate: Predicate for CASE query (optional).
   :param expression_tuples: One or more cases to evaluate.
   :param default: Default value (optional).
   :return: Representation of CASE statement.

   Example:

   .. code-block:: python

      Number = Table('numbers', ('val',))

      num_as_str = Case(Number.val, (
          (1, 'one'),
          (2, 'two'),
          (3, 'three')), 'a lot')

      query = Number.select(Number.val, num_as_str.alias('num_str'))

   Equivalent SQL:

   .. code-block:: sql

      SELECT "val",
        CASE "val"
            WHEN 1 THEN 'one'
            WHEN 2 THEN 'two'
            WHEN 3 THEN 'three'
            ELSE 'a lot' END AS "num_str"
      FROM "numbers"

   Example:

   .. code-block:: python

      num_as_str = Case(None, (
          (Number.val == 1, 'one'),
          (Number.val == 2, 'two'),
          (Number.val == 3, 'three')), 'a lot')
      query = Number.select(Number.val, num_as_str.alias('num_str'))

   Equivalent SQL:

   .. code-block:: sql

      SELECT "val",
        CASE
            WHEN "val" = 1 THEN 'one'
            WHEN "val" = 2 THEN 'two'
            WHEN "val" = 3 THEN 'three'
            ELSE 'a lot' END AS "num_str"
      FROM "numbers"


.. class:: NodeList(nodes, glue=' ', parens=False)

   :param list nodes: Zero or more nodes.
   :param str glue: How to join the nodes when converting to SQL.
   :param bool parens: Whether to wrap the resulting SQL in parentheses.

   Represent a list of nodes, a multi-part clause, a list of parameters, etc.


.. function:: CommaNodeList(nodes)

   :param list nodes: Zero or more nodes.
   :return: a :class:`NodeList`

   Represent a list of nodes joined by commas.


.. function:: EnclosedNodeList(nodes)

   :param list nodes: Zero or more nodes.
   :return: a :class:`NodeList`

   Represent a list of nodes joined by commas and wrapped in parentheses.


.. class:: DQ(**query)

   :param query: Arbitrary filter expressions using Django-style lookups.

   Represent a composable Django-style filter expression suitable for use with
   the :meth:`Model.filter` or :meth:`ModelSelect.filter` methods.


.. class:: Tuple(*args)

   Represent a SQL `row value <https://www.sqlite.org/rowvalue.html>`_.
   Row-values are supported by most databases.


.. class:: OnConflict(action=None, update=None, preserve=None, where=None, conflict_target=None, conflict_where=None, conflict_constraint=None)

   :param str action: Action to take when resolving conflict.
   :param update: A dictionary mapping column to new value.
   :param preserve: A list of columns whose values should be preserved from the original INSERT. See also :class:`EXCLUDED`.
   :param where: Expression to restrict the conflict resolution.
   :param conflict_target: Column(s) that comprise the constraint.
   :param conflict_where: Expressions needed to match the constraint target if it is a partial index (index with a WHERE clause).
   :param str conflict_constraint: Name of constraint to use for conflict
       resolution. Currently only supported by Postgres.

   Represent a conflict resolution clause for a data-modification query.

   See :ref:`upsert` for detailed discussion.

   .. method:: preserve(*columns)

      :param columns: Columns whose values should be preserved.

   .. method:: update(_data=None, **kwargs)

      :param dict _data: Dictionary mapping column to new value.
      :param kwargs: Dictionary mapping column name to new value.

      The ``update()`` method supports being called with either a dictionary
      of column-to-value, **or** keyword arguments representing the same.

   .. method:: where(*expressions)

      :param expressions: Expressions that restrict the action of the
          conflict resolution clause.

   .. method:: conflict_target(*constraints)

      :param constraints: Column(s) to use as target for conflict resolution.

   .. method:: conflict_where(*expressions)

      :param expressions: Expressions that match the conflict target index,
          in the case the conflict target is a partial index.

   .. method:: conflict_constraint(constraint)

      :param str constraint: Name of constraints to use as target for
          conflict resolution. Currently only supported by Postgres.


.. class:: EXCLUDED

   Helper object that exposes the ``EXCLUDED`` namespace that is used with
   ``INSERT ... ON CONFLICT`` to reference values in the conflicting data.
   This is a "magic" helper, such that one uses it by accessing attributes on
   it that correspond to a particular column.

   See :meth:`Insert.on_conflict` for example usage.


Queries
-------

.. class:: BaseQuery()

   The parent class from which all other query classes are derived. While you
   will not deal with :class:`BaseQuery` directly in your code, it
   implements some methods that are common across all query types.

   .. attribute:: default_row_type = ROW.DICT

   .. method:: bind(database=None)

      :param Database database: Database to execute query against.

      Bind the query to the given database for execution.

   .. method:: dicts(as_dict=True)

      :param bool as_dict: Specify whether to return rows as dictionaries.

      Return rows as dictionaries.

   .. method:: tuples(as_tuples=True)

      :param bool as_tuples: Specify whether to return rows as tuples.

      Return rows as tuples.

   .. method:: namedtuples(as_namedtuple=True)

      :param bool as_namedtuple: Specify whether to return rows as named
          tuples.

      Return rows as named tuples.

   .. method:: objects(constructor=None)

      :param constructor: Function that accepts row dict and returns an
          arbitrary object.

      Return rows as arbitrary objects using the given constructor.

   .. method:: sql()

      :return: A 2-tuple consisting of the query's SQL and parameters.

   .. method:: execute(database)

      :param Database database: Database to execute query against. Not
          required if query was previously bound to a database.

      Execute the query and return result (depends on type of query being
      executed). For example, select queries the return result will be an
      iterator over the query results.

   .. method:: iterator(database=None)

      :param Database database: Database to execute query against. Not
          required if query was previously bound to a database.

      Execute the query and return an iterator over the result-set. For large
      result-sets this method is preferable as rows are not cached in-memory
      during iteration.

      .. note::
         Because rows are not cached, the query may only be iterated over
         once. Subsequent iterations will return empty result-sets as the
         cursor will have been consumed.

       Example:

       .. code-block:: python

          query = StatTbl.select().order_by(StatTbl.timestamp).tuples()
          for row in query.iterator(db):
              process_row(row)

   .. method:: __iter__()

      Execute the query and return an iterator over the result-set.

      Unlike :meth:`~BaseQuery.iterator`, this method will cause rows to
      be cached in order to allow efficient iteration, indexing and slicing.

   .. method:: __getitem__(value)

      :param value: Either an integer index or a slice.

      Retrieve a row or range of rows from the result-set.

   .. method:: __len__()

      Return the number of rows in the result-set.

      .. warning::
         This does not issue a ``COUNT()`` query. Instead, the result-set
         is loaded as it would be during normal iteration, and the length
         is determined from the size of the result set.


.. class:: RawQuery(sql=None, params=None, **kwargs)

   :param str sql: SQL query.
   :param tuple params: Parameters (optional).

   Create a query by directly specifying the SQL to execute.


.. class:: Query(where=None, order_by=None, limit=None, offset=None, **kwargs)

   :param where: Representation of WHERE clause.
   :param tuple order_by: Columns or values to order by.
   :param int limit: Value of LIMIT clause.
   :param int offset: Value of OFFSET clause.

   Base-class for queries that support method-chaining APIs.

   .. method:: with_cte(*cte_list)

      :param cte_list: zero or more :class:`CTE` objects.

      Include the given common-table expressions in the query. Any previously
      specified CTEs will be overwritten. For examples of common-table
      expressions, see :ref:`cte`.

   .. method:: cte(name, recursive=False, columns=None)

      :param str name: Alias for common table expression.
      :param bool recursive: Will this be a recursive CTE?
      :param list columns: List of column names (as strings).

      Indicate that a query will be used as a common table expression. For
      example, if we are modelling a category tree and are using a
      parent-link foreign key, we can retrieve all categories and their
      absolute depths using a recursive CTE:

      .. code-block:: python

         class Category(Model):
             name = TextField()
             parent = ForeignKeyField('self', backref='children', null=True)

         # The base case of our recursive CTE will be categories that are at
         # the root level -- in other words, categories without parents.
         roots = (Category
                  .select(Category.name, Value(0).alias('level'))
                  .where(Category.parent.is_null())
                  .cte(name='roots', recursive=True))

         # The recursive term will select the category name and increment
         # the depth, joining on the base term so that the recursive term
         # consists of all children of the base category.
         RTerm = Category.alias()
         recursive = (RTerm
                      .select(RTerm.name, (roots.c.level + 1).alias('level'))
                      .join(roots, on=(RTerm.parent == roots.c.id)))

         # Express <base term> UNION ALL <recursive term>.
         cte = roots.union_all(recursive)

         # Select name and level from the recursive CTE.
         query = (cte
                  .select_from(cte.c.name, cte.c.level)
                  .order_by(cte.c.name))

         for category in query:
             print(category.name, category.level)

      For more examples of CTEs, see :ref:`cte`.

   .. method:: where(*expressions)

      :param expressions: zero or more expressions to include in the WHERE
          clause.

      Include the given expressions in the WHERE clause of the query. The
      expressions will be AND-ed together with any previously-specified
      WHERE expressions.

      Example selection users where the username is equal to 'somebody':

      .. code-block:: python

         sq = User.select().where(User.username == 'somebody')

      Example selecting tweets made by users who are either editors or
      administrators:

      .. code-block:: python

         sq = Tweet.select().join(User).where(
             (User.is_editor == True) |
             (User.is_admin == True))

      Example of deleting tweets by users who are no longer active:

      .. code-block:: python

         inactive_users = User.select().where(User.active == False)
         dq = (Tweet
               .delete()
               .where(Tweet.user.in_(inactive_users)))
         dq.execute()  # Return number of tweets deleted.

      .. note::

         :meth:`~Query.where` calls are chainable.  Multiple calls will
         be "AND"-ed together.

   .. method:: orwhere(*expressions)

      :param expressions: zero or more expressions to include in the WHERE
          clause.

      Include the given expressions in the WHERE clause of the query. This
      method is the same as the :meth:`Query.where` method, except that
      the expressions will be OR-ed together with any previously-specified
      WHERE expressions.

   .. method:: order_by(*values)

      :param values: zero or more Column-like objects to order by.

      Define the ORDER BY clause. Any previously-specified values will be
      overwritten.

   .. method:: order_by_extend(*values)

      :param values: zero or more Column-like objects to order by.

      Extend any previously-specified ORDER BY clause with the given values.

   .. method:: limit(value=None)

      :param int value: specify value for LIMIT clause.

   .. method:: offset(value=None)

      :param int value: specify value for OFFSET clause.

   .. method:: paginate(page, paginate_by=20)

      :param int page: Page number of results (starting from 1).
      :param int paginate_by: Rows-per-page.

      Convenience method for specifying the LIMIT and OFFSET in a more
      intuitive way.

      This feature is designed with web-site pagination in mind, so the first
      page starts with ``page=1``.


.. class:: SelectQuery()

   Select query helper-class that implements operator-overloads for creating
   compound queries.

   .. method:: select_from(*columns)

      :param columns: one or more columns to select from the inner query.
      :return: a new query that wraps the calling query.

      Create a new query that wraps the current (calling) query. For example,
      suppose you have a simple ``UNION`` query, and need to apply an
      aggregation on the union result-set. To do this, you need to write
      something like:

      .. code-block:: sql

         SELECT "u"."owner", COUNT("u"."id") AS "ct"
         FROM (
             SELECT "id", "owner", ... FROM "cars"
             UNION
             SELECT "id", "owner", ... FROM "motorcycles"
             UNION
             SELECT "id", "owner", ... FROM "boats") AS "u"
         GROUP BY "u"."owner"

      The :meth:`~SelectQuery.select_from` method is designed to simplify
      constructing this type of query.

      Example peewee code:

      .. code-block:: python

         class Car(Model):
             owner = ForeignKeyField(Owner, backref='cars')
             # ... car-specific fields, etc ...

         class Motorcycle(Model):
             owner = ForeignKeyField(Owner, backref='motorcycles')
             # ... motorcycle-specific fields, etc ...

         class Boat(Model):
             owner = ForeignKeyField(Owner, backref='boats')
             # ... boat-specific fields, etc ...

         cars = Car.select(Car.owner)
         motorcycles = Motorcycle.select(Motorcycle.owner)
         boats = Boat.select(Boat.owner)

         union = cars | motorcycles | boats

         query = (union
                  .select_from(union.c.owner, fn.COUNT(union.c.id))
                  .group_by(union.c.owner))

   .. method:: union_all(dest)

      Create a UNION ALL query with ``dest``.

   .. method:: __add__(dest)

      Create a UNION ALL query with ``dest``.

   .. method:: union(dest)

      Create a UNION query with ``dest``.

   .. method:: __or__(dest)

      Create a UNION query with ``dest``.

   .. method:: intersect(dest)

      Create an INTERSECT query with ``dest``.

   .. method:: __and__(dest)

      Create an INTERSECT query with ``dest``.

   .. method:: except_(dest)

      Create an EXCEPT query with ``dest``. Note that the method name has a
      trailing "_" character since ``except`` is a Python reserved word.

   .. method:: __sub__(dest)

      Create an EXCEPT query with ``dest``.


.. class:: SelectBase()

   Base-class for :class:`Select` and :class:`CompoundSelect` queries.

   .. method:: peek(database, n=1)

      :param Database database: database to execute query against.
      :param int n: Number of rows to return.
      :return: A single row if n = 1, else a list of rows.

      Execute the query and return the given number of rows from the start
      of the cursor. This function may be called multiple times safely, and
      will always return the first N rows of results.

   .. method:: first(database, n=1)

      :param Database database: database to execute query against.
      :param int n: Number of rows to return.
      :return: A single row if n = 1, else a list of rows.

      Like the :meth:`~SelectBase.peek` method, except a ``LIMIT`` is
      applied to the query to ensure that only ``n`` rows are returned.
      Multiple calls for the same value of ``n`` will not result in multiple
      executions.

      The query is altered in-place so it is not possible to call
      :meth:`~SelectBase.first` and then later iterate over the full
      result-set using the same query object. Again, this is done to ensure
      that multiple calls to ``first()`` will not result in multiple query
      executions.

   .. method:: scalar(database, as_tuple=False, as_dict=False)

      :param Database database: database to execute query against.
      :param bool as_tuple: Return the result as a tuple?
      :param bool as_dict: Return the result as a dict?
      :return: Single scalar value. If ``as_tuple = True``, a row tuple is
          returned. If ``as_dict = True``, a row dict is returned.

      Return a scalar value from the first row of results. If multiple
      scalar values are anticipated (e.g. multiple aggregations in a single
      query) then you may specify ``as_tuple=True`` to get the row tuple.

      Example:

      .. code-block:: python

         query = Note.select(fn.MAX(Note.timestamp))
         max_ts = query.scalar(db)

         query = Note.select(fn.MAX(Note.timestamp), fn.COUNT(Note.id))
         max_ts, n_notes = query.scalar(db, as_tuple=True)

         query = Note.select(fn.COUNT(Note.id).alias('count'))
         assert query.scalar(db, as_dict=True) == {'count': 123}

   .. method:: count(database, clear_limit=False)

      :param Database database: database to execute query against.
      :param bool clear_limit: Clear any LIMIT clause when counting.
      :return: Number of rows in the query result-set.

      Return number of rows in the query result-set.

      Implemented by running SELECT COUNT(1) FROM (<current query>).

   .. method:: exists(database)

      :param Database database: database to execute query against.
      :return: Whether any results exist for the current query.

      Return a boolean indicating whether the current query has any results.

   .. method:: get(database)

      :param Database database: database to execute query against.
      :return: A single row from the database or ``None``.

      Execute the query and return the first row, if it exists. Multiple
      calls will result in multiple queries being executed.


.. class:: CompoundSelectQuery(lhs, op, rhs)

   :param SelectBase lhs: A Select or CompoundSelect query.
   :param str op: Operation (e.g. UNION, INTERSECT, EXCEPT).
   :param SelectBase rhs: A Select or CompoundSelect query.

   Class representing a compound SELECT query.


.. class:: Select(from_list=None, columns=None, group_by=None, having=None, distinct=None, windows=None, for_update=None, for_update_of=None, for_update_nowait=None, **kwargs)

   :param list from_list: List of sources for FROM clause.
   :param list columns: Columns or values to select.
   :param list group_by: List of columns or values to group by.
   :param Expression having: Expression for HAVING clause.
   :param distinct: Either a boolean or a list of column-like objects.
   :param list windows: List of :class:`Window` clauses.
   :param for_update: Boolean or str indicating if SELECT...FOR UPDATE.
   :param for_update_of: One or more tables for FOR UPDATE OF clause.
   :param bool for_update_nowait: Specify NOWAIT locking.

   Class representing a SELECT query.

   .. note::
      Rather than instantiating this directly, most-commonly you will use a
      factory method like :meth:`Table.select` or :meth:`Model.select`.

   Methods on the select query can be chained together.

   Example selecting some user instances from the database.  Only the ``id``
   and ``username`` columns are selected.  When iterated, will return instances
   of the ``User`` model:

   .. code-block:: python

      query = User.select(User.id, User.username)
      for user in query:
          print(user.username)

   Example selecting users and additionally the number of tweets made by the
   user.  The ``User`` instances returned will have an additional attribute,
   'count', that corresponds to the number of tweets made:

   .. code-block:: python

      query = (User
               .select(User, fn.COUNT(Tweet.id).alias('count'))
               .join(Tweet, JOIN.LEFT_OUTER)
               .group_by(User))
      for user in query:
          print(user.username, 'has tweeted', user.count, 'times')

   .. note::
      While it is possible to instantiate :class:`Select` directly, more
      commonly you will build the query using the method-chaining APIs.

   .. method:: columns(*columns)

      :param columns: Zero or more column-like objects to SELECT.

      Specify which columns or column-like values to SELECT.

   .. method:: select(*columns)

      :param columns: Zero or more column-like objects to SELECT.

      Same as :meth:`Select.columns`, provided for
      backwards-compatibility.

   .. method:: select_extend(*columns)

      :param columns: Zero or more column-like objects to SELECT.

      Extend the current selection with the given columns.

      Example:

      .. code-block:: python

         def get_users(with_count=False):
             query = User.select()
             if with_count:
                 query = (query
                          .select_extend(fn.COUNT(Tweet.id).alias('count'))
                          .join(Tweet, JOIN.LEFT_OUTER)
                          .group_by(User))
             return query

   .. method:: from_(*sources)

      :param sources: Zero or more sources for the FROM clause.

      Specify which table-like objects should be used in the FROM clause.

      .. code-block:: python

         User = Table('users')
         Tweet = Table('tweets')
         query = (User
                  .select(User.c.username, Tweet.c.content)
                  .from_(User, Tweet)
                  .where(User.c.id == Tweet.c.user_id))
         for row in query.execute(db):
             print(row['username'], '->', row['content'])

   .. method:: join(dest, join_type='INNER', on=None)

      :param dest: A table or table-like object.
      :param str join_type: Type of JOIN, default is "INNER".
      :param Expression on: Join predicate.

      Join type may be one of:

      * ``JOIN.INNER``
      * ``JOIN.LEFT_OUTER``
      * ``JOIN.RIGHT_OUTER``
      * ``JOIN.FULL``
      * ``JOIN.FULL_OUTER``
      * ``JOIN.CROSS``

      Express a JOIN:

      .. code-block:: python

         User = Table('users', ('id', 'username'))
         Note = Table('notes', ('id', 'user_id', 'content'))

         query = (Note
                  .select(Note.content, User.username)
                  .join(User, on=(Note.user_id == User.id)))

   .. method:: group_by(*columns)

      :param values: zero or more Column-like objects to group by.

      Define the GROUP BY clause. Any previously-specified values will be
      overwritten.

      Additionally, to specify all columns on a given table, you can pass the
      table/model object in place of the individual columns.

      Example:

      .. code-block:: python

         query = (User
                  .select(User, fn.Count(Tweet.id).alias('count'))
                  .join(Tweet)
                  .group_by(User))

   .. method:: group_by_extend(*columns)

      :param values: zero or more Column-like objects to group by.

      Extend the GROUP BY clause with the given columns.

   .. method:: having(*expressions)

      :param expressions: zero or more expressions to include in the HAVING
          clause.

      Include the given expressions in the HAVING clause of the query. The
      expressions will be AND-ed together with any previously-specified
      HAVING expressions.

   .. method:: distinct(*columns)

      :param columns: Zero or more column-like objects.

      Indicate whether this query should use a DISTINCT clause. By specifying
      a single value of ``True`` the query will use a simple SELECT DISTINCT.
      Specifying one or more columns will result in a SELECT DISTINCT ON.

   .. method:: window(*windows)

      :param windows: zero or more :class:`Window` objects.

      Define the WINDOW clause. Any previously-specified values will be
      overwritten.

      Example:

      .. code-block:: python

         # Equivalent example Using a Window() instance instead.
         window = Window(partition_by=[Sample.counter])
         query = (Sample
                  .select(
                     Sample.counter,
                     Sample.value,
                     fn.AVG(Sample.value).over(window))
                  .window(window)  # Note call to ".window()"
                  .order_by(Sample.counter))

   .. method:: for_update(for_update=True, of=None, nowait=None)

      :param for_update: Either a boolean or a string indicating the
          desired expression, e.g. "FOR SHARE".
      :param of: One or more models to restrict locking to.
      :param bool nowait: Specify NOWAIT option when locking.


.. class:: _WriteQuery(table, returning=None, **kwargs)

   :param Table table: Table to write to.
   :param list returning: List of columns for RETURNING clause.

   Base-class for write queries.

   .. method:: returning(*returning)

      :param returning: Zero or more column-like objects for RETURNING clause

      Specify the RETURNING clause of query (Postgresql and Sqlite):

      .. code-block:: python

         query = (User
                  .insert_many([{'username': 'foo'},
                                {'username': 'bar'},
                                {'username': 'baz'}])
                  .returning(User.id, User.username)
                  .namedtuples())
         data = query.execute()
         for row in data:
             print('added:', row.username, 'with id=', row.id)

      .. seealso:: :ref:`returning-clause` for additional discussion.


.. class:: Update(table, update=None, **kwargs)

   :param Table table: Table to update.
   :param dict update: Data to update.

   Class representing an UPDATE query.

   See :ref:`updating-records` for additional discussion.

   Example:

   .. code-block:: python

      PageView = Table('page_views')
      query = (PageView
               .update({PageView.c.page_views: PageView.c.page_views + 1})
               .where(PageView.c.url == url))
      query.execute(database)

   .. method:: from_(*sources)

      :param Source sources: one or more :class:`Table`,
          :class:`Model`, query, or :class:`ValuesList` to join with.

      Specify additional tables to join with using the UPDATE ... FROM
      syntax, which is supported by Postgres. The `Postgres documentation <https://www.postgresql.org/docs/10/static/sql-update.html#id-1.9.3.176.8>`_
      provides additional detail, but to summarize:

         When a ``FROM`` clause is present, what essentially happens is that
         the target table is joined to the tables mentioned in the
         from_list, and each output row of the join represents an update
         operation for the target table. When using ``FROM`` you should
         ensure that the join produces at most one output row for each row
         to be modified.

      Example:

      .. code-block:: python

         # Update multiple users in a single query.
         data = [('huey', True),
                 ('mickey', False),
                 ('zaizee', True)]
         vl = ValuesList(data, columns=('username', 'is_admin'), alias='vl')

         # Here we'll update the "is_admin" status of the above users,
         # "joining" the VALUES() on the "username" column.
         query = (User
                  .update(is_admin=vl.c.is_admin)
                  .from_(vl)
                  .where(User.username == vl.c.username))

      The above query produces the following SQL:

      .. code-block:: sql

         UPDATE "users" SET "is_admin" = "vl"."is_admin"
         FROM (
             VALUES ('huey', t), ('mickey', f), ('zaizee', t))
             AS "vl"("username", "is_admin")
         WHERE ("users"."username" = "vl"."username")


.. class:: Insert(table, insert=None, columns=None, on_conflict=None, **kwargs)

   :param Table table: Table to INSERT data into.
   :param insert: Either a dict, a list, or a query.
   :param list columns: List of columns when ``insert`` is a list or query.
   :param on_conflict: Conflict resolution strategy.

   Class representing an INSERT query.

   See :ref:`inserting-records` for additional discussion.

   Example:

   .. code-block:: python

      User = Table('users')

      query = User.insert({User.c.username: 'huey'})
      query.execute(database)

   .. method:: as_rowcount(as_rowcount=True)

      :param bool as_rowcount: Whether to return the modified row count (as
          opposed to the last-inserted row id).

      SQLite and MySQL return the last inserted rowid. Postgresql will return a
      cursor for iterating over the inserted id(s).

      If you prefer to receive the inserted row-count, then specify
      ``as_rowcount()``:

      .. code-block:: python

         db = MySQLDatabase(...)

         query = User.insert_many([...])
         # By default, the last rowid is returned:
         #last_id = query.execute()

         # To get the modified row-count:
         rowcount = query.as_rowcount().execute()

   .. method:: on_conflict_ignore(ignore=True)

      :param bool ignore: Whether to add ON CONFLICT IGNORE clause.

      Specify IGNORE conflict resolution strategy.

   .. method:: on_conflict_replace(replace=True)

      :param bool replace: Whether to add ON CONFLICT REPLACE clause.

      Specify REPLACE conflict resolution strategy (SQLite and MySQL only).

   .. method:: on_conflict(action=None, update=None, preserve=None, where=None, conflict_target=None, conflict_where=None, conflict_constraint=None)

      :param str action: Action to take when resolving conflict. If blank,
          action is assumed to be "update".
      :param update: A dictionary mapping column to new value.
      :param preserve: A list of columns whose values should be preserved from the original INSERT.
      :param where: Expression to restrict the conflict resolution.
      :param conflict_target: Column(s) that comprise the constraint.
      :param conflict_where: Expressions needed to match the constraint target if it is a partial index (index with a WHERE clause).
      :param str conflict_constraint: Name of constraint to use for conflict
          resolution. Currently only supported by Postgres.

      Specify the parameters for an :class:`OnConflict` clause to use for
      conflict resolution.

      See :ref:`upsert` for additional discussion.

      Examples:

      .. code-block:: python

         class User(Model):
             username = TextField(unique=True)
             last_login = DateTimeField(null=True)
             login_count = IntegerField()

         def log_user_in(username):
             now = datetime.datetime.now()

             # INSERT a new row for the user with the current timestamp and
             # login count set to 1. If the user already exists, then we
             # will preserve the last_login value from the "insert()" clause
             # and atomically increment the login-count.
             userid = (User
                       .insert(username=username, last_login=now, login_count=1)
                       .on_conflict(
                           conflict_target=[User.username],
                           preserve=[User.last_login],
                           update={User.login_count: User.login_count + 1})
                       .execute())
             return userid

      Example using the special :class:`EXCLUDED` namespace:

      .. code-block:: python

         class KV(Model):
             key = CharField(unique=True)
             value = IntegerField()

         # Create one row.
         KV.create(key='k1', value=1)

         # Demonstrate usage of EXCLUDED.
         # Here we will attempt to insert a new value for a given key. If that
         # key already exists, then we will update its value with the *sum* of its
         # original value and the value we attempted to insert -- provided that
         # the new value is larger than the original value.
         query = (KV.insert(key='k1', value=10)
                  .on_conflict(conflict_target=[KV.key],
                               update={KV.value: KV.value + EXCLUDED.value},
                               where=(EXCLUDED.value > KV.value)))

         # Executing the above query will result in the following data being
         # present in the "kv" table:
         # (key='k1', value=11)
         query.execute()

         # If we attempted to execute the query *again*, then nothing would be
         # updated, as the new value (10) is now less than the value in the
         # original row (11).


.. class:: Delete()

   Class representing a DELETE query.

   See :ref:`deleting-records` for additional discussion.

   Example:

   .. code-block:: python

      Tweet = Table('tweets')

      # Delete all unpublished tweets older than 30 days.
      cutoff = datetime.datetime.now() - datetime.timedelta(days=30)
      query = (Tweet
               .delete()
               .where(
                   (Tweet.c.is_published == False) &
                   (Tweet.c.timestamp < cutoff)))
      nrows = query.execute(database)


.. function:: prefetch(sq, *subqueries, prefetch_type=PREFETCH_TYPE.WHERE)

   :param sq: Query to use as starting-point.
   :param subqueries: One or more models or :class:`ModelSelect` queries
       to eagerly fetch.
   :param prefetch_type: Query type to use for the subqueries.
   :return: a list of models with selected relations prefetched.

   Eagerly fetch related objects, allowing efficient querying of multiple
   tables when a 1-to-many relationship exists. The prefetch type changes how
   the subqueries are constructed which may be desirable depending on the
   database engine in use.

   Prefetch type may be one of:

   * ``PREFETCH_TYPE.WHERE``
   * ``PREFETCH_TYPE.JOIN``

   See :ref:`relationships` for in-depth discussion of joining and prefetch.

   For example, it is simple to query a many-to-1 relationship efficiently:

   .. code-block:: python

      query = (Tweet
               .select(Tweet, User)
               .join(User))
      for tweet in query:
          # Looking up tweet.user.username does not require a query since
          # the related user's columns were selected.
          print(tweet.user.username, '->', tweet.content)

   To efficiently do the inverse, query users and their tweets, you can use
   prefetch:

   .. code-block:: python

      query = User.select()
      for user in prefetch(query, Tweet):
          print(user.username)
          for tweet in user.tweets:  # Does not require additional query.
              print('    ', tweet.content)

   .. note::
      Because ``prefetch`` must reconstruct a graph of models, it is
      necessary to be sure that the foreign-key/primary-key of any
      related models are selected, so that the related objects can be
      mapped correctly.


Query-builder Internals
-----------------------

.. class:: AliasManager()

   Manages the aliases assigned to :class:`Source` objects in SELECT
   queries, so as to avoid ambiguous references when multiple sources are
   used in a single query.

   .. method:: add(source)

      Add a source to the AliasManager's internal registry at the current
      scope. The alias will be automatically generated using the following
      scheme (where each level of indentation refers to a new scope):

      :param Source source: Make the manager aware of a new source. If the
          source has already been added, the call is a no-op.

   .. method:: get(source, any_depth=False)

      Return the alias for the source in the current scope. If the source
      does not have an alias, it will be given the next available alias.

      :param Source source: The source whose alias should be retrieved.
      :return: The alias already assigned to the source, or the next
          available alias.
      :rtype: str

   .. method:: __setitem__(source, alias)

      Manually set the alias for the source at the current scope.

      :param Source source: The source for which we set the alias.

   .. method:: push()

      Push a new scope onto the stack.

   .. method:: pop()

      Pop scope from the stack.


.. class:: State(scope, parentheses=False, subquery=False, **kwargs)

   Lightweight object for representing the state at a given scope. During SQL
   generation, each object visited by the :class:`Context` can inspect the
   state. The :class:`State` class allows Peewee to do things like:

   * Use a common interface for field types or SQL expressions, but use
     vendor-specific data-types or operators.
   * Compile a :class:`Column` instance into a fully-qualified attribute,
     as a named alias, etc, depending on the value of the ``scope``.
   * Ensure parentheses are used appropriately.

   :param int scope: The scope rules to be applied while the state is active.
   :param bool parentheses: Wrap the contained SQL in parentheses.
   :param bool subquery: Whether the current state is a child of an outer
       query.
   :param dict kwargs: Arbitrary settings which should be applied in the
       current state.


.. class:: Context(**settings)

   Converts Peewee structures into parameterized SQL queries.

   Peewee structures should all implement a `__sql__` method, which will be
   called by the `Context` class during SQL generation. The `__sql__` method
   accepts a single parameter, the `Context` instance, which allows for
   recursive descent and introspection of scope and state.

   .. attribute:: scope

      Return the currently-active scope rules.

   .. attribute:: parentheses

      Return whether the current state is wrapped in parentheses.

   .. attribute:: subquery

      Return whether the current state is the child of another query.

   .. method:: scope_normal(**kwargs)

      The default scope. Sources are referred to by alias, columns by
      dotted-path from the source.

   .. method:: scope_source(**kwargs)

      Scope used when defining sources, e.g. in the column list and FROM
      clause of a SELECT query. This scope is used for defining the
      fully-qualified name of the source and assigning an alias.

   .. method:: scope_values(**kwargs)

      Scope used for UPDATE, INSERT or DELETE queries, where instead of
      referencing a source by an alias, we refer to it directly. Similarly,
      since there is a single table, columns do not need to be referenced
      by dotted-path.

   .. method:: scope_cte(**kwargs)

      Scope used when generating the contents of a common-table-expression.
      Used after a WITH statement, when generating the definition for a CTE
      (as opposed to merely a reference to one).

   .. method:: scope_column(**kwargs)

      Scope used when generating SQL for a column. Ensures that the column is
      rendered with its correct alias. Was needed because when referencing
      the inner projection of a sub-select, Peewee would render the full
      SELECT query as the "source" of the column (instead of the query's
      alias + . + column).  This scope allows us to avoid rendering the full
      query when we only need the alias.

   .. method:: sql(obj)

      Append a composable Node object, sub-context, or other object to the
      query AST. Python values, such as integers, strings, floats, etc. are
      treated as parameterized values.

      :return: The updated Context object.

   .. method:: literal(keyword)

      Append a string-literal to the current query AST.

      :return: The updated Context object.

   .. method:: parse(node)

      :param Node node: Instance of a Node subclass.
      :return: a 2-tuple consisting of (sql, parameters).

      Convert the given node to a SQL AST and return a 2-tuple consisting
      of the SQL query and the parameters.

   .. method:: query()

      :return: a 2-tuple consisting of (sql, parameters) for the context.


Constants and Helpers
---------------------

.. class:: Proxy()

   Create a proxy or placeholder for another object.

   .. method:: initialize(obj)

      :param obj: Object to proxy to.

      Bind the proxy to the given object. Afterwards all attribute lookups
      and method calls on the proxy will be sent to the given object.

      Any callbacks that have been registered will be called.

   .. method:: attach_callback(callback)

      :param callback: A function that accepts a single parameter, the bound
          object.
      :return: self

      Add a callback to be executed when the proxy is initialized.

.. class:: DatabaseProxy()

   Proxy subclass that is suitable to use as a placeholder for a
   :class:`Database` instance.

   See :ref:`initializing-database` for details.

   Example:

   .. code-block:: python

      db = DatabaseProxy()

      class BaseModel(Model):
          class Meta:
              database = db

      # ... some time later ...
      if app.config['DEBUG']:
          database = SqliteDatabase('local.db')
      elif app.config['TESTING']:
          database = SqliteDatabase(':memory:')
      else:
          database = PostgresqlDatabase('production')

      db.initialize(database)

.. function:: chunked(iterable, n)

   :param iterable: an iterable that is the source of the data to be chunked.
   :param int n: chunk size
   :return: a new iterable that yields *n*-length chunks of the source data.

   Efficient implementation for breaking up large lists of data into
   smaller-sized chunks.

   Usage:

   .. code-block:: python

      it = range(10)  # An iterable that yields 0...9.

      # Break the iterable into chunks of length 4.
      for chunk in chunked(it, 4):
          print(', '.join(str(num) for num in chunk))

      # PRINTS:
      # 0, 1, 2, 3
      # 4, 5, 6, 7
      # 8, 9


Playhouse Reference
-------------------

+---------------------------------------+---------------------------+
| Module                                | Section                   |
+=======================================+===========================+
| playhouse.sqlite_ext                  | :ref:`sqlite`             |
+---------------------------------------+---------------------------+
| playhouse.cysqlite_ext                | :ref:`cysqlite-ext`       |
+---------------------------------------+---------------------------+
| playhouse.sqliteq                     | :ref:`sqliteq`            |
+---------------------------------------+---------------------------+
| playhouse.sqlite_udf                  | :ref:`sqlite-udf`         |
+---------------------------------------+---------------------------+
| playhouse.apsw_ext                    | :ref:`apsw`               |
+---------------------------------------+---------------------------+
| playhouse.sqlcipher_ext               | :ref:`sqlcipher`          |
+---------------------------------------+---------------------------+
| playhouse.postgres_ext                | :ref:`postgresql`         |
+---------------------------------------+---------------------------+
| playhouse.cockroachdb                 | :ref:`crdb`               |
+---------------------------------------+---------------------------+
| playhouse.mysql_ext                   | :ref:`mysql`              |
+---------------------------------------+---------------------------+
| playhouse.db_url                      | :ref:`db-url`             |
+---------------------------------------+---------------------------+
| playhouse.pool                        | :ref:`pool`               |
+---------------------------------------+---------------------------+
| playhouse.migrate                     | :ref:`migrate`            |
+---------------------------------------+---------------------------+
| playhouse.reflection                  | :ref:`reflection`         |
+---------------------------------------+---------------------------+
| playhouse.test_utils                  | :ref:`test-utils`         |
+---------------------------------------+---------------------------+
| playhouse.fields                      | :ref:`extra-fields`       |
+---------------------------------------+---------------------------+
| playhouse.shortcuts                   | :ref:`shortcuts`          |
+---------------------------------------+---------------------------+
| playhouse.hybrid                      | :ref:`hybrid`             |
+---------------------------------------+---------------------------+
| playhouse.kv                          | :ref:`kv`                 |
+---------------------------------------+---------------------------+
| playhouse.signals                     | :ref:`signals`            |
+---------------------------------------+---------------------------+
| playhouse.dataset                     | :ref:`dataset`            |
+---------------------------------------+---------------------------+
| playhouse.flask_utils                 | :ref:`flask-utils`        |
+---------------------------------------+---------------------------+
