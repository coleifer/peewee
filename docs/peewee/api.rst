.. _api:

API Documentation
=================

This document specifies Peewee's APIs.

Database
--------

.. py:class:: Database(database[, thread_safe=True[, autorollback=False[, field_types=None[, operations=None[, **kwargs]]]]])

    :param str database: Database name or filename for SQLite.
    :param bool thread_safe: Whether to store connection state in a
        thread-local.
    :param bool autorollback: Automatically rollback queries that fail when
        **not** in an explicit transaction.
    :param dict field_types: A mapping of additional field types to support.
    :param dict operations: A mapping of additional operations to support.
    :param kwargs: Arbitrary keyword arguments that will be passed to the
        database driver when a connection is created, for example ``password``,
        ``host``, etc.

    The :py:class:`Database` is responsible for:

    * Executing queries
    * Managing connections
    * Transactions
    * Introspection

    .. note::

        The database can be instantiated with ``None`` as the database name if
        the database is not known until run-time. In this way you can create a
        database instance and then configure it elsewhere when the settings are
        known. This is called *deferred* initialization.

        To initialize a database that has been *deferred*, use the
        :py:meth:`~Database.init` method.

    .. py:attribute:: param = '?'

        String used as parameter placeholder in SQL queries.

    .. py:attribute:: quote = '"'

        Type of quotation-mark to use to denote entities such as tables or
        columns.

    .. py:method:: init(database[, **kwargs])

        :param str database: Database name or filename for SQLite.
        :param kwargs: Arbitrary keyword arguments that will be passed to the
            database driver when a connection is created, for example
            ``password``, ``host``, etc.

        Initialize a *deferred* database.

    .. py:method:: __enter__()

        The :py:class:`Database` instance can be used as a context-manager, in
        which case a connection will be held open for the duration of the
        wrapped block.

        Additionally, any SQL executed within the wrapped block will be
        executed in a transaction.

    .. py:method:: connection_context()

        Create a context-manager that will hold open a connection for the
        duration of the wrapped block.

        Example::

            def on_app_startup():
                # When app starts up, create the database tables, being sure
                # the connection is closed upon completion.
                with database.connection_context():
                    database.create_tables(APP_MODELS)

    .. py:method:: connect([reuse_if_open=False])

        :param bool reuse_if_open: Do not raise an exception if a connection is
            already opened.
        :returns: whether a new connection was opened.
        :rtype: bool
        :raises: ``OperationalError`` if connection already open and
            ``reuse_if_open`` is not set to ``True``.

        Open a connection to the database.

    .. py:method:: close()

        :returns: Whether a connection was closed. If the database was already
            closed, this returns ``False``.
        :rtype: bool

        Close the connection to the database.

    .. py:method:: is_closed()

        :returns: return ``True`` if database is closed, ``False`` if open.
        :rtype: bool

    .. py:method:: connection()

        Return the open connection. If a connection is not open, one will be
        opened. The connection will be whatever the underlying database-driver
        uses to encapsulate a database connection.

    .. py:method:: cursor([commit=None])

        :param commit: For internal use.

        Return a ``cursor`` object on the current connection. If a connection
        is not open, one will be opened. The cursor will be whatever the
        underlying database-driver uses to encapsulate a database cursor.

    .. py:method:: execute_sql(sql[, params=None[, commit=SENTINEL]])

        :param str sql: SQL string to execute.
        :param tuple params: Parameters for query.
        :param commit: Boolean flag to override the default commit logic.
        :returns: cursor object.

        Execute a SQL query and return a cursor over the results.

    .. py:method:: execute(query[, commit=SENTINEL[, **context_options]])

        :param query: A :py:class:`Query` instance.
        :param commit: Boolean flag to override the default commit logic.
        :param context_options: Arbitrary options to pass to the SQL generator.
        :returns: cursor object.

        Execute a SQL query by compiling a ``Query`` instance and executing the
        resulting SQL.

    .. py:method:: last_insert_id(cursor[, query_type=None])

        :param cursor: cursor object.
        :returns: primary key of last-inserted row.

    .. py:method:: rows_affected(cursor)

        :param cursor: cursor object.
        :returns: number of rows modified by query.

    .. py:method:: in_transaction()

        :returns: whether or not a transaction is currently open.
        :rtype: bool

    .. py:method:: atomic()

        Create a context-manager which runs any queries in the wrapped block in
        a transaction (or save-point if blocks are nested).

        Calls to :py:meth:`~Database.atomic` can be nested.

        :py:meth:`~Database.atomic` can also be used as a decorator.

        Example code::

            with db.atomic() as txn:
                perform_operation()

                with db.atomic() as nested_txn:
                    perform_another_operation()

        Transactions and save-points can be explicitly committed or rolled-back
        within the wrapped block. If this occurs, a new transaction or
        savepoint is begun after the commit/rollback.

        Example::

            with db.atomic() as txn:
                User.create(username='mickey')
                txn.commit()  # Changes are saved and a new transaction begins.

                User.create(username='huey')
                txn.rollback()  # "huey" will not be saved.

                User.create(username='zaizee')

            # Print the usernames of all users.
            print [u.username for u in User.select()]

            # Prints ["mickey", "zaizee"]

    .. py:method:: manual_commit()

        Create a context-manager which disables all transaction management for
        the duration of the wrapped block.

        Example::

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

        The above code is equivalent to the following::

            with db.atomic():
                user.delete_instance(recursive=True)

    .. py:method:: transaction()

        Create a context-manager that runs all queries in the wrapped block in
        a transaction.

        .. warning::
            Calls to ``transaction`` cannot be nested. Only the top-most call
            will take effect. Rolling-back or committing a nested transaction
            context-manager has undefined behavior.

    .. py:method:: savepoint()

        Create a context-manager that runs all queries in the wrapped block in
        a savepoint. Savepoints can be nested arbitrarily.

        .. warning::
            Calls to ``savepoint`` must occur inside of a transaction.

    .. py:method:: begin()

        Begin a transaction when using manual-commit mode.

        .. note::
            This method should only be used in conjunction with the
            :py:meth:`~Database.manual_commit` context manager.

    .. py:method:: commit()

        Manually commit the currently-active transaction.

        .. note::
            This method should only be used in conjunction with the
            :py:meth:`~Database.manual_commit` context manager.

    .. py:method:: rollback()

        Manually roll-back the currently-active transaction.

        .. note::
            This method should only be used in conjunction with the
            :py:meth:`~Database.manual_commit` context manager.

    .. py:method:: batch_commit(it, n)

        :param iterable it: an iterable whose items will be yielded.
        :param int n: commit every *n* items.
        :return: an equivalent iterable to the one provided, with the addition
            that groups of *n* items will be yielded in a transaction.

        The purpose of this method is to simplify batching large operations,
        such as inserts, updates, etc. You pass in an iterable and the number
        of items-per-batch, and the items will be returned by an equivalent
        iterator that wraps each batch in a transaction.

        Example:

        .. code-block:: python

            # Some list or iterable containing data to insert.
            row_data = [{'username': 'u1'}, {'username': 'u2'}, ...]

            # Insert all data, committing every 100 rows. If, for example,
            # there are 789 items in the list, then there will be a total of
            # 8 transactions (7x100 and 1x89).
            for row in db.batch_commit(row_data, 100):
                User.create(**row)

        An alternative that may be more efficient is to batch the data into a
        multi-value ``INSERT`` statement (for example, using
        :py:meth:`Model.insert_many`):

        .. code-block:: python

            with db.atomic():
                for idx in range(0, len(row_data), 100):
                    # Insert 100 rows at a time.
                    rows = row_data[idx:idx + 100]
                    User.insert_many(rows).execute()

    .. py:method:: table_exists(table[, schema=None])

        :param str table: Table name.
        :param str schema: Schema name (optional).
        :returns: ``bool`` indicating whether table exists.

    .. py:method:: get_tables([schema=None])

        :param str schema: Schema name (optional).
        :returns: a list of table names in the database.

    .. py:method:: get_indexes(table[, schema=None])

        :param str table: Table name.
        :param str schema: Schema name (optional).

        Return a list of :py:class:`IndexMetadata` tuples.

        Example::

            print db.get_indexes('entry')
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

    .. py:method:: get_columns(table[, schema=None])

        :param str table: Table name.
        :param str schema: Schema name (optional).

        Return a list of :py:class:`ColumnMetadata` tuples.

        Example::

            print db.get_columns('entry')
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

    .. py:method:: get_primary_keys(table[, schema=None])

        :param str table: Table name.
        :param str schema: Schema name (optional).

        Return a list of column names that comprise the primary key.

        Example::

            print db.get_primary_keys('entry')
            ['id']

    .. py:method:: get_foreign_keys(table[, schema=None])

        :param str table: Table name.
        :param str schema: Schema name (optional).

        Return a list of :py:class:`ForeignKeyMetadata` tuples for keys present
        on the table.

        Example::

            print db.get_foreign_keys('entrytag')
            [ForeignKeyMetadata(
                 column='entry_id',
                 dest_table='entry',
                 dest_column='id',
                 table='entrytag'),
             ...]

    .. py:method:: sequence_exists(seq)

        :param str seq: Name of sequence.
        :returns: Whether sequence exists.
        :rtype: bool

    .. py:method:: create_tables(models[, **options])

        :param list models: A list of :py:class:`Model` classes.
        :param options: Options to specify when calling
            :py:meth:`Model.create_table`.

        Create tables, indexes and associated metadata for the given list of
        models.

        Dependencies are resolved so that tables are created in the appropriate
        order.

    .. py:method:: drop_tables(models[, **options])

        :param list models: A list of :py:class:`Model` classes.
        :param kwargs: Options to specify when calling
            :py:meth:`Model.drop_table`.

        Drop tables, indexes and associated metadata for the given list of
        models.

        Dependencies are resolved so that tables are dropped in the appropriate
        order.

    .. py:method:: bind(models[, bind_refs=True[, bind_backrefs=True]])

        :param list models: One or more :py:class:`Model` classes to bind.
        :param bool bind_refs: Bind related models.
        :param bool bind_backrefs: Bind back-reference related models.

        Bind the given list of models, and specified relations, to the
        database.

    .. py:method:: bind_ctx(models[, bind_refs=True[, bind_backrefs=True]])

        :param list models: List of models to bind to the database.
        :param bool bind_refs: Bind models that are referenced using
            foreign-keys.
        :param bool bind_backrefs: Bind models that reference the given model
            with a foreign-key.

        Create a context-manager that binds (associates) the given models with
        the current database for the duration of the wrapped block.

        Example:

        .. code-block:: python

            MODELS = (User, Account, Note)

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


.. py:class:: SqliteDatabase(database[, pragmas=None[, timeout=5[, **kwargs]]])

    :param list pragmas: A list of 2-tuples containing pragma key and value to
        set every time a connection is opened.
    :param timeout: Set the busy-timeout on the SQLite driver (in seconds).

    Sqlite database implementation. :py:class:`SqliteDatabase` that provides
    some advanced features only offered by Sqlite.

    * Register custom aggregates, collations and functions
    * Load C extensions
    * Advanced transactions (specify isolation level)
    * For even more features, see :py:class:`SqliteExtDatabase`.

    Example of using PRAGMAs::

        db = SqliteDatabase('my_app.db', pragmas=(
            ('cache_size', -16000),  # 16MB
            ('journal_mode', 'wal'),  # Use write-ahead-log journal mode.
        ))

    .. py:method:: pragma(key[, value=SENTINEL[, permanent=False]])

        :param key: Setting name.
        :param value: New value for the setting (optional).
        :param permanent: Apply this pragma whenever a connection is opened.

        Execute a PRAGMA query once on the active connection. If a value is not
        specified, then the current value will be returned.

        If ``permanent`` is specified, then the PRAGMA query will also be
        executed whenever a new connection is opened, ensuring it is always
        in-effect.

        .. note::
            By default this only affects the current connection. If the PRAGMA
            being executed is not persistent, then you must specify
            ``permanent=True`` to ensure the pragma is set on subsequent
            connections.

    .. py:attribute:: cache_size

        Get or set the cache_size pragma for the current connection.

    .. py:attribute:: foreign_keys

        Get or set the foreign_keys pragma for the current connection.

    .. py:attribute:: journal_mode

        Get or set the journal_mode pragma.

    .. py:attribute:: journal_size_limit

        Get or set the journal_size_limit pragma.

    .. py:attribute:: mmap_size

        Get or set the mmap_size pragma for the current connection.

    .. py:attribute:: page_size

        Get or set the page_size pragma.

    .. py:attribute:: read_uncommitted

        Get or set the read_uncommitted pragma for the current connection.

    .. py:attribute:: synchronous

        Get or set the synchronous pragma for the current connection.

    .. py:attribute:: wal_autocheckpoint

        Get or set the wal_autocheckpoint pragma for the current connection.

    .. py:attribute:: timeout

        Get or set the busy timeout (seconds).

    .. py:method:: register_aggregate(klass[, name=None[, num_params=-1]])

        :param klass: Class implementing aggregate API.
        :param str name: Aggregate function name (defaults to name of class).
        :param int num_params: Number of parameters the aggregate accepts, or
            -1 for any number.

        Register a user-defined aggregate function.

        The function will be registered each time a new connection is opened.
        Additionally, if a connection is already open, the aggregate will be
        registered with the open connection.

    .. py:method:: aggregate([name=None[, num_params=-1]])

        :param str name: Name of the aggregate (defaults to class name).
        :param int num_params: Number of parameters the aggregate accepts,
            or -1 for any number.

        Class decorator to register a user-defined aggregate function.

        Example::

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

    .. py:method:: register_collation(fn[, name=None])

        :param fn: The collation function.
        :param str name: Name of collation (defaults to function name)

        Register a user-defined collation. The collation will be registered
        each time a new connection is opened.  Additionally, if a connection is
        already open, the collation will be registered with the open
        connection.

    .. py:method:: collation([name=None])

        :param str name: Name of collation (defaults to function name)

        Decorator to register a user-defined collation.

        Example::

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

    .. py:method:: register_function(fn[, name=None[, num_params=-1]])

        :param fn: The user-defined scalar function.
        :param str name: Name of function (defaults to function name)
        :param int num_params: Number of arguments the function accepts, or
            -1 for any number.

        Register a user-defined scalar function. The function will be
        registered each time a new connection is opened.  Additionally, if a
        connection is already open, the function will be registered with the
        open connection.

    .. py:method:: func([name=None[, num_params=-1]])

        :param str name: Name of the function (defaults to function name).
        :param int num_params: Number of parameters the function accepts,
            or -1 for any number.

        Decorator to register a user-defined scalar function.

        Example::

            @db.func('title_case')
            def title_case(s):
                return s.title() if s else ''

            # Usage:
            title_case_books = Book.select(fn.title_case(Book.title))

    .. py:method:: table_function([name=None])

        Class-decorator for registering a :py:class:`TableFunction`. Table
        functions are user-defined functions that, rather than returning a
        single, scalar value, can return any number of rows of tabular data.

        Example:

        .. code-block:: python

            from playhouse.sqlite_ext import TableFunction

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

    .. py:method:: unregister_aggregate(name)

        :param name: Name of the user-defined aggregate function.

        Unregister the user-defined aggregate function.

    .. py:method:: unregister_collation(name)

        :param name: Name of the user-defined collation.

        Unregister the user-defined collation.

    .. py:method:: unregister_function(name)

        :param name: Name of the user-defined scalar function.

        Unregister the user-defined scalar function.

    .. py:method:: unregister_table_function(name)

        :param name: Name of the user-defined table function.
        :returns: True or False, depending on whether the function was removed.

        Unregister the user-defined scalar function.

    .. py:method:: load_extension(extension_module)

        Load the given C extension. If a connection is currently open in the
        calling thread, then the extension will be loaded for that connection
        as well as all subsequent connections.

        For example, if you've compiled the closure table extension and wish to
        use it in your application, you might write:

        .. code-block:: python

            db = SqliteExtDatabase('my_app.db')
            db.load_extension('closure')

    .. py:method:: attach(filename, name)

        :param str filename: Database to attach (or ``:memory:`` for in-memory)
        :param str name: Schema name for attached database.
        :return: boolean indicating success

        Register another database file that will be attached to every database
        connection. If the main database is currently connected, the new
        database will be attached on the open connection.

        .. note::
            Databases that are attached using this method will be attached
            every time a database connection is opened.

    .. py:method:: detach(name)

        :param str name: Schema name for attached database.
        :return: boolean indicating success

        Unregister another database file that was attached previously with a
        call to :py:meth:`~SqliteDatabase.attach`. If the main database is
        currently connected, the attached database will be detached from the
        open connection.

    .. py:method:: transaction([lock_type=None])

        :param str lock_type: Locking strategy: DEFERRED, IMMEDIATE, EXCLUSIVE.

        Create a transaction context-manager using the specified locking
        strategy (defaults to DEFERRED).


.. py:class:: PostgresqlDatabase(database[, register_unicode=True[, encoding=None]])

    Postgresql database implementation.

    Additional optional keyword-parameters:

    :param bool register_unicode: Register unicode types.
    :param str encoding: Database encoding.


.. py:class:: MySQLDatabase(database[, **kwargs])

    MySQL database implementation.

.. _query-builder-api:

Query-builder
-------------

.. py:class:: Node()

    Base-class for all components which make up the AST for a SQL query.

    .. py:staticmethod:: copy(method)

        Decorator to use with Node methods that mutate the node's state.
        This allows method-chaining, e.g.:

        .. code-block:: python

            query = MyModel.select()
            new_query = query.where(MyModel.field == 'value')

    .. py:method:: unwrap()

        API for recursively unwrapping "wrapped" nodes. Base case is to
        return self.


.. py:class:: Source([alias=None])

    A source of row tuples, for example a table, join, or select query. By
    default provides a "magic" attribute named "c" that is a factory for
    column/attribute lookups, for example::

        User = Table('users')
        query = (User
                 .select(User.c.username)
                 .where(User.c.active == True)
                 .order_by(User.c.username))

    .. py:method:: alias(name)

        Returns a copy of the object with the given alias applied.

    .. py:method:: select(*columns)

        :param columns: :py:class:`Column` instances, expressions, functions,
            sub-queries, or anything else that you would like to select.

        Create a :py:class:`Select` query on the table. If the table explicitly
        declares columns and no columns are provided, then by default all the
        table's defined columns will be selected.

    .. py:method:: join(dest[, join_type='INNER'[, on=None]])

        :param Source dest: Join the table with the given destination.
        :param str join_type: Join type.
        :param on: Expression to use as join predicate.
        :returns: a :py:class:`Join` instance.

        Join type may be one of:

        * ``JOIN.INNER``
        * ``JOIN.LEFT_OUTER``
        * ``JOIN.RIGHT_OUTER``
        * ``JOIN.FULL``
        * ``JOIN.FULL_OUTER``
        * ``JOIN.CROSS``

    .. py:method:: left_outer_join(dest[, on=None])

        :param Source dest: Join the table with the given destination.
        :param on: Expression to use as join predicate.
        :returns: a :py:class:`Join` instance.

        Convenience method for calling :py:meth:`~Source.join` using a LEFT
        OUTER join.


.. py:class:: BaseTable()

    Base class for table-like objects, which support JOINs via operator
    overloading.

    .. py:method:: __and__(dest)

        Perform an INNER join on ``dest``.

    .. py:method:: __add__(dest)

        Perform a LEFT OUTER join on ``dest``.

    .. py:method:: __sub__(dest)

        Perform a RIGHT OUTER join on ``dest``.

    .. py:method:: __or__(dest)

        Perform a FULL OUTER join on ``dest``.

    .. py:method:: __mul__(dest)

        Perform a CROSS join on ``dest``.


.. py:class:: Table(name[, columns=None[, primary_key=None[, schema=None[, alias=None]]]])

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

    Example::

        User = Table('users')
        query = (User
                 .select(User.c.id, User.c.username)
                 .order_by(User.c.username))

    Equivalent example when columns **are** specified::

        User = Table('users', ('id', 'username'))
        query = (User
                 .select(User.id, User.username)
                 .order_by(User.username))

    .. py:method:: bind([database=None])

        :param database: :py:class:`Database` object.

        Bind this table to the given database (or unbind by leaving empty).

        When a table is *bound* to a database, queries may be executed against
        it without the need to specify the database in the query's execute
        method.

    .. py:method:: bind_ctx([database=None])

        :param database: :py:class:`Database` object.

        Return a context manager that will bind the table to the given database
        for the duration of the wrapped block.

    .. py:method:: select(*columns)

        :param columns: :py:class:`Column` instances, expressions, functions,
            sub-queries, or anything else that you would like to select.

        Create a :py:class:`Select` query on the table. If the table explicitly
        declares columns and no columns are provided, then by default all the
        table's defined columns will be selected.

        Example::

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

    .. py:method:: insert([insert=None[, columns=None[, **kwargs]]])

        :param insert: A dictionary mapping column to value, an iterable that
            yields dictionaries (i.e. list), or a :py:class:`Select` query.
        :param list columns: The list of columns to insert into when the
            data being inserted is not a dictionary.
        :param kwargs: Mapping of column-name to value.

        Create a :py:class:`Insert` query into the table.

    .. py:method:: replace([insert=None[, columns=None[, **kwargs]]])

        :param insert: A dictionary mapping column to value, an iterable that
            yields dictionaries (i.e. list), or a :py:class:`Select` query.
        :param list columns: The list of columns to insert into when the
            data being inserted is not a dictionary.
        :param kwargs: Mapping of column-name to value.

        Create a :py:class:`Insert` query into the table whose conflict
        resolution method is to replace.

    .. py:method:: update([update=None[, **kwargs]])

        :param update: A dictionary mapping column to value.
        :param kwargs: Mapping of column-name to value.

        Create a :py:class:`Update` query for the table.

    .. py:method:: delete()

        Create a :py:class:`Delete` query for the table.


.. py:class:: Join(lhs, rhs[, join_type=JOIN.INNER[, on=None[, alias=None]]])

    Represent a JOIN between to table-like objects.

    :param lhs: Left-hand side of the join.
    :param rhs: Right-hand side of the join.
    :param join_type: Type of join. e.g. JOIN.INNER, JOIN.LEFT_OUTER, etc.
    :param on: Expression describing the join predicate.
    :param str alias: Alias to apply to joined data.

    .. py:method:: on(predicate)

        :param Expression predicate: join predicate.

        Specify the predicate expression used for this join.


.. py:class:: ValuesList(values[, columns=None[, alias=None]])

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

    .. py:method:: columns(*names)

        :param names: names to apply to the columns of data.

        Example:

        .. code-block:: python

            vl = ValuesList([(1, 'first'), (2, 'second')])
            vl = vl.columns('idx', 'name').alias('v')

            query = vl.select(vl.c.idx, vl.c.name)
            # Yields:
            # SELECT v.idx, v.name
            # FROM (VALUES (1, 'first'), (2, 'second')) AS v(idx, name)


.. py:class:: CTE(name, query[, recursive=False[, columns=None]])

    Represent a common-table-expression.

    :param name: Name for the CTE.
    :param query: :py:class:`Select` query describing CTE.
    :param bool recursive: Whether the CTE is recursive.
    :param list columns: Explicit list of columns produced by CTE (optional).

    .. py:method:: select_from(*columns)

        Create a SELECT query that utilizes the given common table expression
        as the source for a new query.

        :param columns: One or more columns to select from the CTE.
        :return: :py:class:`Select` query utilizing the common table expression

    .. py:method:: union_all(other)

        Used on the base-case CTE to construct the recursive term of the CTE.

        :param other: recursive term, generally a :py:class:`Select` query.
        :return: a recursive :py:class:`CTE` with the given recursive term.


.. py:class:: ColumnBase()

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

    .. py:method:: alias(alias)

        :param str alias: Alias for the given column-like object.
        :returns: a :py:class:`Alias` object.

        Indicate the alias that should be given to the specified column-like
        object.

    .. py:method:: cast(as_type)

        :param str as_type: Type name to cast to.
        :returns: a :py:class:`Cast` object.

        Create a ``CAST`` expression.

    .. py:method:: asc()

        :returns: an ascending :py:class:`Ordering` object for the column.

    .. py:method:: desc()

        :returns: an descending :py:class:`Ordering` object for the column.

    .. py:method:: __invert__()

        :returns: a :py:class:`Negated` wrapper for the column.


.. py:class:: Column(source, name)

    :param Source source: Source for column.
    :param str name: Column name.

    Column on a table or a column returned by a sub-query.


.. py:class:: Alias(node, alias)

    :param Node node: a column-like object.
    :param str alias: alias to assign to column.

    Create a named alias for the given column-like object.

    .. py:method:: alias([alias=None])

        :param str alias: new name (or None) for aliased column.

        Create a new :py:class:`Alias` for the aliased column-like object. If
        the new alias is ``None``, then the original column-like object is
        returned.


.. py:class:: Negated(node)

    Represents a negated column-like object.


.. py:class:: Value(value[, converterNone[, unpack=True]])

    :param value: Python object or scalar value.
    :param converter: Function used to convert value into type the database
        understands.
    :param bool unpack: Whether lists or tuples should be unpacked into a list
        of values or treated as-is.

    Value to be used in a parameterized query. It is the responsibility of the
    caller to ensure that the value passed in can be adapted to a type the
    database driver understands.


.. py:function:: AsIs(value)

    Represents a :py:class:`Value` that is treated as-is, and passed directly
    back to the database driver.


.. py:class:: Cast(node, cast)

    :param node: A column-like object.
    :param str cast: Type to cast to.

    Represents a ``CAST(<node> AS <cast>)`` expression.


.. py:class:: Ordering(node, direction[, collation=None[, nulls=None]])

    :param node: A column-like object.
    :param str direction: ASC or DESC
    :param str collation: Collation name to use for sorting.
    :param str nulls: Sort nulls (FIRST or LAST).

    Represent ordering by a column-like object.

    .. py:method:: collate([collation=None])

        :param str collation: Collation name to use for sorting.


.. py:function:: Asc(node[, collation=None[, nulls=None]])

    Short-hand for instantiating an ascending :py:class:`Ordering` object.


.. py:function:: Desc(node[, collation=None[, nulls=None]])

    Short-hand for instantiating an descending :py:class:`Ordering` object.


.. py:class:: Expression(lhs, op, rhs[, flat=True])

    :param lhs: Left-hand side.
    :param op: Operation.
    :param rhs: Right-hand side.
    :param bool flat: Whether to wrap expression in parentheses.

    Represent a binary expression of the form (lhs op rhs), e.g. (foo + 1).


.. py:class:: Entity(*path)

    :param path: Components that make up the dotted-path of the entity name.

    Represent a quoted entity in a query, such as a table, column, alias. The
    name may consist of multiple components, e.g. "a_table"."column_name".

    .. py:method:: __getattr__(self, attr)

        Factory method for creating sub-entities.


.. py:class:: SQL(sql[, params=None])

    :param str sql: SQL query string.
    :param tuple params: Parameters for query (optional).

    Represent a parameterized SQL query or query-fragment.


.. py:function:: Check(constraint)

    :param str constraint: Constraint SQL.

    Represent a CHECK constraint.


.. py:class:: Function(name, arguments[, coerce=True])

    :param str name: Function name.
    :param tuple arguments: Arguments to function.
    :param bool coerce: Whether to coerce the function result to a particular
        data-type when reading function return values from the cursor.

    Represent an arbitrary SQL function call.

    .. note::
        Rather than instantiating this class directly, it is recommended to use
        the ``fn`` helper.

    Example of using ``fn`` to call an arbitrary SQL function::

        # Query users and count of tweets authored.
        query = (User
                 .select(User.username, fn.COUNT(Tweet.id).alias('ct'))
                 .join(Tweet, JOIN.LEFT_OUTER, on=(User.id == Tweet.user_id))
                 .group_by(User.username)
                 .order_by(fn.COUNT(Tweet.id).desc()))

    .. py:method:: over([partition_by=None[, order_by=None[, start=None[, end=None[, window=None]]]]])

        :param list partition_by: List of columns to partition by.
        :param list order_by: List of columns / expressions to order window by.
        :param start: A :py:class:`SQL` instance or a string expressing the
            start of the window range.
        :param end: A :py:class:`SQL` instance or a string expressing the
            end of the window range.
        :param Window window: A :py:class:`Window` instance.

        .. note::
            For simplicity, it is permissible to call ``over()`` with a
            :py:class:`Window` instance as the first and only parameter.

        Examples::

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
                                start=Window.preceding(),  # unbounded.
                                end=Window.following(1)))  # 1 following.
                     .order_by(Sample.id))

    .. py:method:: coerce([coerce=True])

        :param bool coerce: Whether to coerce function-call result.

.. py:function:: fn()

    The :py:func:`fn` helper is actually an instance of :py:class:`Function`
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

.. py:class:: Window([partition_by=None[, order_by=None[, start=None[, end=None[, alias=None]]]]])

    :param list partition_by: List of columns to partition by.
    :param list order_by: List of columns to order by.
    :param start: A :py:class:`SQL` instance or a string expressing the start
        of the window range.
    :param end: A :py:class:`SQL` instance or a string expressing the end of
        the window range.
    :param str alias: Alias for the window.

    Represent a WINDOW clause.

    .. py:attribute:: CURRENT_ROW

        Handy reference to current row for use in start/end clause.

    .. py:method:: alias([alias=None])

        :param str alias: Alias to use for window.

    .. py:staticmethod:: following([value=None])

        :param value: Number of rows following. If ``None`` is UNBOUNDED.

        Convenience method for generating SQL suitable for passing in as the
        ``end`` parameter for a window range.

    .. py:staticmethod:: preceding([value=None])

        :param value: Number of rows preceding. If ``None`` is UNBOUNDED.

        Convenience method for generating SQL suitable for passing in as the
        ``start`` parameter for a window range.


.. py:function:: Case(predicate, expression_tuples[, default=None]])

    :param predicate: Predicate for CASE query (optional).
    :param expression_tuples: One or more cases to evaluate.
    :param default: Default value (optional).
    :returns: Representation of CASE statement.

    Examples::

        Number = Table('numbers', ('val',))

        num_as_str = Case(Number.val, (
            (1, 'one'),
            (2, 'two'),
            (3, 'three')), 'a lot')

        query = Number.select(Number.val, num_as_str.alias('num_str'))

        # The above is equivalent to:
        # SELECT "val",
        #   CASE "val"
        #       WHEN 1 THEN 'one'
        #       WHEN 2 THEN 'two'
        #       WHEN 3 THEN 'three'
        #       ELSE 'a lot' END AS "num_str"
        # FROM "numbers"

        num_as_str = Case(None, (
            (Number.val == 1, 'one'),
            (Number.val == 2, 'two'),
            (Number.val == 3, 'three')), 'a lot')
        query = Number.select(Number.val, num_as_str.alias('num_str'))

        # The above is equivalent to:
        # SELECT "val",
        #   CASE
        #       WHEN "val" = 1 THEN 'one'
        #       WHEN "val" = 2 THEN 'two'
        #       WHEN "val" = 3 THEN 'three'
        #       ELSE 'a lot' END AS "num_str"
        # FROM "numbers"


.. py:class:: NodeList(nodes[, glue=' '[, parens=False]])

    :param list nodes: Zero or more nodes.
    :param str glue: How to join the nodes when converting to SQL.
    :param bool parens: Whether to wrap the resulting SQL in parentheses.

    Represent a list of nodes, a multi-part clause, a list of parameters, etc.


.. py:function:: CommaNodeList(nodes)

    :param list nodes: Zero or more nodes.
    :returns: a :py:class:`NodeList`

    Represent a list of nodes joined by commas.


.. py:function:: EnclosedNodeList(nodes)

    :param list nodes: Zero or more nodes.
    :returns: a :py:class:`NodeList`

    Represent a list of nodes joined by commas and wrapped in parentheses.


.. py:class:: DQ(**query)

    :param query: Arbitrary filter expressions using Django-style lookups.

    Represent a composable Django-style filter expression suitable for use with
    the :py:meth:`Model.filter` or :py:meth:`ModelSelect.filter` methods.


.. py:class:: Tuple(*args)

    Represent a SQL row tuple.


.. py:class:: OnConflict([action=None[, update=None[, preserve=None[, where=None[, conflict_target=None]]]]])

    :param str action: Action to take when resolving conflict.
    :param update: A dictionary mapping column to new value.
    :param preserve: A list of columns whose values should be preserved from the original INSERT.
    :param where: Expression to restrict the conflict resolution.
    :param conflict_target: Name of column or constraint to check.

    Represent a conflict resolution clause for a data-modification query.

    Depending on the database-driver being used, one or more of the above
    parameters may be required.

    .. py:method:: preserve(*columns)

        :param columns: Columns whose values should be preserved.

    .. py:method:: update([_data=None[, **kwargs]])

        :param dict _data: Dictionary mapping column to new value.
        :param kwargs: Dictionary mapping column name to new value.

        The ``update()`` method supports being called with either a dictionary
        of column-to-value, **or** keyword arguments representing the same.

    .. py:method:: where(*expressions)

        :param expressions: Expressions that restrict the action of the
            conflict resolution clause.

    .. py:method:: conflict_target(*constraints)

        :param constraints: Name(s) of columns/constraints that are the target
            of the conflict resolution.


.. py:class:: BaseQuery()

    The parent class from which all other query classes are derived. While you
    will not deal with :py:class:`BaseQuery` directly in your code, it
    implements some methods that are common across all query types.

    .. py:attribute:: default_row_type = ROW.DICT

    .. py:method:: bind([database=None])

        :param Database database: Database to execute query against.

        Bind the query to the given database for execution.

    .. py:method:: dicts([as_dict=True])

        :param bool as_dict: Specify whether to return rows as dictionaries.

        Return rows as dictionaries.

    .. py:method:: tuples([as_tuples=True])

        :param bool as_tuple: Specify whether to return rows as tuples.

        Return rows as tuples.

    .. py:method:: namedtuples([as_namedtuple=True])

        :param bool as_namedtuple: Specify whether to return rows as named
            tuples.

        Return rows as named tuples.

    .. py:method:: objects([constructor=None])

        :param constructor: Function that accepts row dict and returns an
            arbitrary object.

        Return rows as arbitrary objects using the given constructor.

    .. py:method:: sql()

        :returns: A 2-tuple consisting of the query's SQL and parameters.

    .. py:method:: execute(database)

        :param Database database: Database to execute query against. Not
            required if query was previously bound to a database.

        Execute the query and return result (depends on type of query being
        executed). For example, select queries the return result will be an
        iterator over the query results.

    .. py:method:: iterator([database=None])

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

    .. py:method:: __iter__()

        Execute the query and return an iterator over the result-set.

        Unlike :py:meth:`~BaseQuery.iterator`, this method will cause rows to
        be cached in order to allow efficient iteration, indexing and slicing.

    .. py:method:: __getitem__(value)

        :param value: Either an integer index or a slice.

        Retrieve a row or range of rows from the result-set.

    .. py:method:: __len__()

        Return the number of rows in the result-set.

        .. warning::
            This does not issue a ``COUNT()`` query. Instead, the result-set
            is loaded as it would be during normal iteration, and the length
            is determined from the size of the result set.


.. py:class:: RawQuery([sql=None[, params=None[, **kwargs]]])

    :param str sql: SQL query.
    :param tuple params: Parameters (optional).

    Create a query by directly specifying the SQL to execute.


.. py:class:: Query([where=None[, order_by=None[, limit=None[, offset=None[, **kwargs]]]]])

    :param where: Representation of WHERE clause.
    :param tuple order_by: Columns or values to order by.
    :param int limit: Value of LIMIT clause.
    :param int offset: Value of OFFSET clause.

    Base-class for queries that support method-chaining APIs.

    .. py:method:: with_cte(*cte_list)

        :param cte_list: zero or more CTE objects.

        Include the given common-table-expressions in the query. Any previously
        specified CTEs will be overwritten.

    .. py:method:: where(*expressions)

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

            :py:meth:`~Query.where` calls are chainable.  Multiple calls will
            be "AND"-ed together.

    .. py:method:: order_by(*values)

        :param values: zero or more Column-like objects to order by.

        Define the ORDER BY clause. Any previously-specified values will be
        overwritten.

    .. py:method:: order_by_extend(*values)

        :param values: zero or more Column-like objects to order by.

        Extend any previously-specified ORDER BY clause with the given values.

    .. py:method:: limit([value=None])

        :param int value: specify value for LIMIT clause.

    .. py:method:: offset([value=None])

        :param int value: specify value for OFFSET clause.

    .. py:method:: paginate(page[, paginate_by=20])

        :param int page: Page number of results (starting from 1).
        :param int paginate_by: Rows-per-page.

        Convenience method for specifying the LIMIT and OFFSET in a more
        intuitive way.

        This feature is designed with web-site pagination in mind, so the first
        page starts with ``page=1``.


.. py:class:: SelectQuery()

    Select query helper-class that implements operator-overloads for creating
    compound queries.

    .. py:method:: union_all(dest)

        Create a UNION ALL query with ``dest``.

    .. py:method:: __add__(dest)

        Create a UNION ALL query with ``dest``.

    .. py:method:: union(dest)

        Create a UNION query with ``dest``.

    .. py:method:: __or__(dest)

        Create a UNION query with ``dest``.

    .. py:method:: intersect(dest)

        Create an INTERSECT query with ``dest``.

    .. py:method:: __and__(dest)

        Create an INTERSECT query with ``dest``.

    .. py:method:: except_(dest)

        Create an EXCEPT query with ``dest``. Note that the method name has a
        trailing "_" character since ``except`` is a Python reserved word.

    .. py:method:: __sub__(dest)

        Create an EXCEPT query with ``dest``.


.. py:class:: SelectBase()

    Base-class for :py:class:`Select` and :py:class:`CompoundSelect` queries.

    .. py:method:: peek(database[, n=1])

        :param Database database: database to execute query against.
        :param int n: Number of rows to return.
        :returns: A single row if n = 1, else a list of rows.

        Execute the query and return the given number of rows from the start
        of the cursor. This function may be called multiple times safely, and
        will always return the first N rows of results.

    .. py:method:: first(database[, n=1])

        :param Database database: database to execute query against.
        :param int n: Number of rows to return.
        :returns: A single row if n = 1, else a list of rows.

        Like the :py:meth:`~SelectBase.peek` method, except a ``LIMIT`` is
        applied to the query to ensure that only ``n`` rows are returned.
        Multiple calls for the same value of ``n`` will not result in multiple
        executions.

    .. py:method:: scalar(database[, as_tuple=False])

        :param Database database: database to execute query against.
        :param bool as_tuple: Return the result as a tuple?
        :returns: Single scalar value if ``as_tuple = False``, else row tuple.

        Return a scalar value from the first row of results. If multiple
        scalar values are anticipated (e.g. multiple aggregations in a single
        query) then you may specify ``as_tuple=True`` to get the row tuple.

        Example::

            query = Note.select(fn.MAX(Note.timestamp))
            max_ts = query.scalar(db)

            query = Note.select(fn.MAX(Note.timestamp), fn.COUNT(Note.id))
            max_ts, n_notes = query.scalar(db, as_tuple=True)

    .. py:method:: count(database[, clear_limit=False])

        :param Database database: database to execute query against.
        :param bool clear_limit: Clear any LIMIT clause when counting.
        :return: Number of rows in the query result-set.

        Return number of rows in the query result-set.

        Implemented by running SELECT COUNT(1) FROM (<current query>).

    .. py:method:: exists(database)

        :param Database database: database to execute query against.
        :return: Whether any results exist for the current query.

        Return a boolean indicating whether the current query has any results.

    .. py:method:: get(database)

        :param Database database: database to execute query against.
        :return: A single row from the database or ``None``.

        Execute the query and return the first row, if it exists. Multiple
        calls will result in multiple queries being executed.


.. py:class:: CompoundSelectQuery(lhs, op, rhs)

    :param SelectBase lhs: A Select or CompoundSelect query.
    :param str op: Operation (e.g. UNION, INTERSECT, EXCEPT).
    :param SelectBase rhs: A Select or CompoundSelect query.

    Class representing a compound SELECT query.


.. py:class:: Select([from_list=None[, columns=None[, group_by=None[, having=None[, distinct=None[, windows=None[, for_update=None[, **kwargs]]]]]]]])

    :param list from_list: List of sources for FROM clause.
    :param list columns: Columns or values to select.
    :param list group_by: List of columns or values to group by.
    :param Expression having: Expression for HAVING clause.
    :param distinct: Either a boolean or a list of column-like objects.
    :param list windows: List of :py:class:`Window` clauses.
    :param for_update: Boolean or str indicating if SELECT...FOR UPDATE.

    Class representing a SELECT query.

    .. note::
        Rather than instantiating this directly, most-commonly you will use a
        factory method like :py:meth:`Table.select` or :py:meth:`Model.select`.

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
        While it is possible to instantiate :py:class:`Select` directly, more
        commonly you will build the query using the method-chaining APIs.

    .. py:method:: columns(*columns)

        :param columns: Zero or more column-like objects to SELECT.

        Specify which columns or column-like values to SELECT.

    .. py:method:: select(*columns)

        :param columns: Zero or more column-like objects to SELECT.

        Same as :py:meth:`Select.columns`, provided for
        backwards-compatibility.

    .. py:method:: select_extend(*columns)

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

    .. py:method:: from_(*sources)

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

    .. py:method:: join(dest[, join_type='INNER'[, on=None]])

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

        Express a JOIN::

            User = Table('users', ('id', 'username'))
            Note = Table('notes', ('id', 'user_id', 'content'))

            query = (Note
                     .select(Note.content, User.username)
                     .join(User, on=(Note.user_id == User.id)))

    .. py:method:: group_by(*columns)

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

    .. py:method:: group_by_extend(*columns)

        :param values: zero or more Column-like objects to group by.

        Extend the GROUP BY clause with the given columns.

    .. py:method:: having(*expressions)

        :param expressions: zero or more expressions to include in the HAVING
            clause.

        Include the given expressions in the HAVING clause of the query. The
        expressions will be AND-ed together with any previously-specified
        HAVING expressions.

    .. py:method:: distinct(*columns)

        :param columns: Zero or more column-like objects.

        Indicate whether this query should use a DISTINCT clause. By specifying
        a single value of ``True`` the query will use a simple SELECT DISTINCT.
        Specifying one or more columns will result in a SELECT DISTINCT ON.

    .. py:method:: window(*windows)

        :param windows: zero or more :py:class:`Window` objects.

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

    .. py:method:: for_update([for_update=True])

        :param for_update: Either a boolean or a string indicating the
            desired expression, e.g. "FOR UPDATE NOWAIT".


.. py:class:: _WriteQuery(table[, returning=None[, **kwargs]])

    :param Table table: Table to write to.
    :param list returning: List of columns for RETURNING clause.

    Base-class for write queries.

    .. py:method:: returning(*returning)

        :param returning: Zero or more column-like objects for RETURNING clause

        Specify the RETURNING clause of query (if supported by your database).

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

.. py:class:: Update(table[, update=None[, **kwargs]])

    :param Table table: Table to update.
    :param dict update: Data to update.

    Class representing an UPDATE query.

    Example::

        PageView = Table('page_views')
        query = (PageView
                 .update({PageView.c.page_views: PageView.c.page_views + 1})
                 .where(PageView.c.url == url))
        query.execute(database)


.. py:class:: Insert(table[, insert=None[, columns=None[, on_conflict=None[, **kwargs]]]])

    :param Table table: Table to INSERT data into.
    :param insert: Either a dict, a list, or a query.
    :param list columns: List of columns when ``insert`` is a list or query.
    :param on_conflict: Conflict resolution strategy.

    Class representing an INSERT query.

    .. py:method:: on_conflict_ignore([ignore=True])

        :param bool ignore: Whether to add ON CONFLICT IGNORE clause.

        Specify IGNORE conflict resolution strategy.

    .. py:method:: on_conflict_replace([replace=True])

        :param bool ignore: Whether to add ON CONFLICT REPLACE clause.

        Specify REPLACE conflict resolution strategy.

    .. py:method:: on_conflict([action=None[, update=None[, preserve=None[, where=None[, conflict_target=None]]]]])

        :param str action: Action to take when resolving conflict. If blank,
            action is assumed to be "update".
        :param update: A dictionary mapping column to new value.
        :param preserve: A list of columns whose values should be preserved from the original INSERT.
        :param where: Expression to restrict the conflict resolution.
        :param conflict_target: Name of column or constraint to check.

        Specify the parameters for an :py:class:`OnConflict` clause to use for
        conflict resolution.

        Example:

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


.. py:class:: Delete()

    Class representing a DELETE query.


.. py:class:: Index(name, table, expressions[, unique=False[, safe=False[, where=None[, using=None]]]])

    :param str name: Index name.
    :param Table table: Table to create index on.
    :param expressions: List of columns to index on (or expressions).
    :param bool unique: Whether index is UNIQUE.
    :param bool safe: Whether to add IF NOT EXISTS clause.
    :param Expression where: Optional WHERE clause for index.
    :param str using: Index algorithm.

    .. py:method:: safe([_safe=True])

        :param bool _safe: Whether to add IF NOT EXISTS clause.

    .. py:method:: where(*expressions)

        :param expressions: zero or more expressions to include in the WHERE
            clause.

        Include the given expressions in the WHERE clause of the index. The
        expressions will be AND-ed together with any previously-specified
        WHERE expressions.

    .. py:method:: using([_using=None])

        :param str _using: Specify index algorithm for USING clause.


.. py:class:: ModelIndex(model, fields[, unique=False[, safe=True[, where=None[, using=None[, name=None]]]]])

    :param Model model: Model class to create index on.
    :param list fields: Fields to index.
    :param bool unique: Whether index is UNIQUE.
    :param bool safe: Whether to add IF NOT EXISTS clause.
    :param Expression where: Optional WHERE clause for index.
    :param str using: Index algorithm.
    :param str name: Optional index name.

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

    You can also use :py:meth:`Model.index`:

    .. code-block:: python

        idx = Article.index(Article.name, Article.timestamp).where(Article.status == 1)

    To add an index to a model definition use :py:meth:`Model.add_index`:

    .. code-block:: python

        idx = Article.index(Article.name, Article.timestamp).where(Article.status == 1)

        # Add above index definition to the model definition. When you call
        # Article.create_table() (or database.create_tables([Article])), the
        # index will be created.
        Article.add_index(idx)

Fields
------

.. py:class:: Field([null=False[, index=False[, unique=False[, column_name=None[, default=None[, primary_key=False[, constraints=None[, sequence=None[, collation=None[, unindexed=False[, choices=None[, help_text=None[, verbose_name=None]]]]]]]]]]]]])

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

    Fields on a :py:class:`Model` are analagous to columns on a table.

    .. py:attribute:: field_type = '<some field type>'

        Attribute used to map this field to a column type, e.g. "INT". See
        the ``FIELD`` object in the source for more information.

    .. py:attribute:: column

        Retrieve a reference to the underlying :py:class:`Column` object.

    .. py:attribute:: model

        The model the field is bound to.

    .. py:attribute:: name

        The name of the field.

    .. py:method:: db_value(value)

        Coerce a Python value into a value suitable for storage in the
        database. Sub-classes operating on special data-types will most likely
        want to override this method.

    .. py:method:: python_value(value)

        Coerce a value from the database into a Python object. Sub-classes
        operating on special data-types will most likely want to override this
        method.

    .. py:method:: coerce(value)

        This method is a shorthand that is used, by default, by both
        :py:meth:`~Field.db_value` and :py:meth:`~Field.python_value`.

        :param value: arbitrary data from app or backend
        :rtype: python data type

.. py:class:: IntegerField

    Field class for storing integers.

.. py:class:: BigIntegerField

    Field class for storing big integers (if supported by database).

.. py:class:: SmallIntegerField

    Field class for storing small integers (if supported by database).

.. py:class:: AutoField

    Field class for storing auto-incrementing primary keys.

    .. note::
        In SQLite, for performance reasons, the default primary key type simply
        uses the max existing value + 1 for new values, as opposed to the max
        ever value + 1. This means deleted records can have their primary keys
        reused. In conjunction with SQLite having foreign keys disabled by
        default (meaning ON DELETE is ignored, even if you specify it
        explicitly), this can lead to surprising and dangerous behaviour. To
        avoid this, you may want to use one or both of
        :py:class:`AutoIncrementField` and ``pragmas=[('foreign_keys', 'on')]``
        when you instantiate :py:class:`SqliteDatabase`.

.. py:class:: BigAutoField

    Field class for storing auto-incrementing primary keys using 64-bits.

.. py:class:: FloatField

    Field class for storing floating-point numbers.

.. py:class:: DoubleField

    Field class for storing double-precision floating-point numbers.

.. py:class:: DecimalField([max_digits=10[, decimal_places=5[, auto_round=False[, rounding=None[, **kwargs]]]]])

   :param int max_digits: Maximum digits to store.
   :param int decimal_places: Maximum precision.
   :param bool auto_round: Automatically round values.
   :param rounding: Defaults to ``decimal.DefaultContext.rounding``.

    Field class for storing decimal numbers. Values are represented as
    ``decimal.Decimal`` objects.

.. py:class:: CharField([max_length=255])

    Field class for storing strings.

    .. note:: Values that exceed length are not truncated automatically.

.. py:class:: FixedCharField

    Field class for storing fixed-length strings.

    .. note:: Values that exceed length are not truncated automatically.

.. py:class:: TextField

    Field class for storing text.

.. py:class:: BlobField

    Field class for storing binary data.

.. py:class:: BitField

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

    .. py:method:: flag(value)

        Returns a descriptor that can get or set specific bits in the overall
        value. When accessed on the class itself, it returns a
        :py:class:`Expression` object suitable for use in a query.

.. py:class:: BigBitField

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

    .. py:method:: set_bit(idx)

        :param int idx: Bit to set, indexed starting from zero.

        Sets the *idx*-th bit in the bitmap.

    .. py:method:: clear_bit(idx)

        :param int idx: Bit to clear, indexed starting from zero.

        Clears the *idx*-th bit in the bitmap.

    .. py:method:: toggle_bit(idx)

        :param int idx: Bit to toggle, indexed starting from zero.
        :returns: Whether the bit is set or not.

        Toggles the *idx*-th bit in the bitmap and returns whether the bit is
        set or not.

        Example:

        .. code-block:: pycon

            >>> bitmap = Bitmap()
            >>> bitmap.data.toggle_bit(10)  # Toggle the 10th bit.
            True
            >>> bitmap.data.toggle_bit(10)  # This will clear the 10th bit.
            False

    .. py:method:: is_set(idx)

        :param int idx: Bit index, indexed starting from zero.
        :returns: Whether the bit is set or not.

        Returns boolean indicating whether the *idx*-th bit is set or not.


.. py:class:: UUIDField

    Field class for storing ``uuid.UUID`` objects. With Postgres, the
    underlying column's data-type will be *UUID*. Since SQLite and MySQL do not
    have a native UUID type, the UUID is stored as a *VARCHAR* instead.

.. py:class:: BinaryUUIDField

    Field class for storing ``uuid.UUID`` objects efficiently in 16-bytes. Uses
    the database's *BLOB* data-type (or *VARBINARY* in MySQL, or *BYTEA* in
    Postgres).

.. py:class:: DateTimeField([formats=None[, **kwargs]])

    :param list formats: A list of format strings to use when coercing a string
        to a date-time.

    Field class for storing ``datetime.datetime`` objects.

    Accepts a special parameter ``formats``, which contains a list of formats
    the datetime can be encoded with (for databases that do not have support
    for a native datetime data-type). The default supported formats are:

    .. note::
        If the incoming value does not match a format, it is returned as-is.

    .. code-block:: python

        '%Y-%m-%d %H:%M:%S.%f' # year-month-day hour-minute-second.microsecond
        '%Y-%m-%d %H:%M:%S' # year-month-day hour-minute-second
        '%Y-%m-%d' # year-month-day

    .. py:attribute:: year

        Reference the year of the value stored in the column in a query.

        .. code-block:: python

            Blog.select().where(Blog.pub_date.year == 2018)

    .. py:attribute:: month

        Reference the month of the value stored in the column in a query.

    .. py:attribute:: day

        Reference the day of the value stored in the column in a query.

    .. py:attribute:: hour

        Reference the hour of the value stored in the column in a query.

    .. py:attribute:: minute

        Reference the minute of the value stored in the column in a query.

    .. py:attribute:: second

        Reference the second of the value stored in the column in a query.

.. py:class:: DateField([formats=None[, **kwargs]])

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

    .. py:attribute:: year

        Reference the year of the value stored in the column in a query.

        .. code-block:: python

            Person.select().where(Person.dob.year == 1983)

    .. py:attribute:: month

        Reference the month of the value stored in the column in a query.

    .. py:attribute:: day

        Reference the day of the value stored in the column in a query.

.. py:class:: TimeField([formats=None[, **kwargs]])

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

    .. py:attribute:: hour

        Reference the hour of the value stored in the column in a query.

        .. code-block:: python

            evening_events = Event.select().where(Event.time.hour > 17)

    .. py:attribute:: minute

        Reference the minute of the value stored in the column in a query.

    .. py:attribute:: second

        Reference the second of the value stored in the column in a query.

.. py:class:: TimestampField([resolution=1[, utc=False[, **kwargs]]])

    :param resolution: A power of 10, 1=second, 1000=ms, 1000000=us, etc.
    :param bool utc: Treat timestamps as UTC.

    Field class for storing date-times as integer timestamps. Sub-second
    resolution is supported by multiplying by a power of 10 to get an integer.

    Accepts a special parameter ``resolution``, which is a power-of-10 up to
    ``10^6``. This allows sub-second precision while still using an
    :py:class:`IntegerField` for storage. Default is ``1`` (second precision).

    Also accepts a boolean parameter ``utc``, used to indicate whether the
    timestamps should be UTC. Default is ``False``.

    Finally, the field ``default`` is the current timestamp. If you do not want
    this behavior, then explicitly pass in ``default=None``.

.. py:class:: IPField

    Field class for storing IPv4 addresses efficiently (as integers).

.. py:class:: BooleanField

    Field class for storing boolean values.

.. py:class:: BareField([coerce=None[, **kwargs]])

    :param coerce: Optional function to use for converting raw values into a
        specific format.

    Field class that does not specify a data-type (**SQLite-only**).

    Since data-types are not enforced, you can declare fields without *any*
    data-type. It is also common for SQLite virtual tables to use meta-columns
    or untyped columns, so for those cases as well you may wish to use an
    untyped field.

    Accepts a special ``coerce`` parameter, a function that takes a value
    coming from the database and converts it into the appropriate Python type.

.. py:class:: ForeignKeyField(model[, field=None[, backref=None[, on_delete=None[, on_update=None[, object_id_name=None[, **kwargs]]]]]])

    :param Model model: Model to reference or the string 'self' if declaring a
        self-referential foreign key.
    :param Field field: Field to reference on ``model`` (default is primary
        key).
    :param str backref: Accessor name for back-reference.
    :param str on_delete: ON DELETE action, e.g. ``'CASCADE'``..
    :param str on_update: ON UPDATE action.
    :param str object_id_name: Name for object-id accessor.

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
        on_delete, since the default ON DELETE behaviour (to fail without
        modifying your data) does not happen, and your data can be silently
        relinked. The safest thing to do is to specify
        ``pragmas=(('foreign_keys', 'on'),)`` when you instantiate
        :py:class:`SqliteDatabase`.

.. py:class:: DeferredForeignKey(rel_model_name[, **kwargs])

    :param str rel_model_name: Model name to reference.

    Field class for representing a deferred foreign key.

.. py:class:: ManyToManyField(model[, backref=None[, through_model=None]])

    :param Model model: Model to create relationship with.
    :param str backref: Accessor name for back-reference
    :param Model through_model: :py:class:`Model` to use for the intermediary
        table. If not provided, a simple through table will be automatically
        created.

    The :py:class:`ManyToManyField` provides a simple interface for working
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
    the :py:class:`ManyToManyField`):

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

    The :py:class:`ManyToManyField` is designed to simplify this use-case by
    providing a *field-like* API for querying and modifying data in the
    junction table. Here is how our code looks using
    :py:class:`ManyToManyField`:

    .. code-block:: python

        class Student(Model):
            name = CharField()

        class Course(Model):
            name = CharField()
            students = ManyToManyField(Student, backref='courses')

    .. note::
        It does not matter from Peewee's perspective which model the
        :py:class:`ManyToManyField` goes on, since the back-reference is just
        the mirror image. In order to write valid Python, though, you will need
        to add the ``ManyToManyField`` on the second model so that the name of
        the first model is in the scope.

    We still need a junction table to store the relationships between students
    and courses. This model can be accessed by calling the
    :py:meth:`~ManyToManyField.get_through_model` method. This is useful when
    creating tables.

    .. code-block:: python

        # Create tables for the students, courses, and relationships between
        # the two.
        db.create_tables([
            Student,
            Course,
            Course.students.get_through_model()])

    When accessed from a model instance, the :py:class:`ManyToManyField`
    exposes a :py:class:`ModelSelect` representing the set of related objects.
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
    :py:meth:`~ManyToManyField.add` method. The difference between the two is
    that simply assigning will clear out any existing relationships, whereas
    ``add()`` can preserve existing relationships.

    .. code-block:: pycon

        >>> huey.courses = Course.select().where(Course.name.contains('english'))
        >>> for course in huey.courses.order_by(Course.name):
        ...     print course.name
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
    To remove objects, use the :py:meth:`~ManyToManyField.remove` method.

    .. code-block:: pycon

        >>> huey.courses.remove(Course.select().where(Course.name.contains('2'))
        2
        >>> [course.name for course in huey.courses.order_by(Course.name)]
        ['CS 101', 'CS151', 'English 101', 'English 151']

    To remove all relationships from a collection, you can use the
    :py:meth:`~SelectQuery.clear` method. Let's say that English 101 is
    canceled, so we need to remove all the students from it:

    .. code-block:: pycon

        >>> engl_101 = Course.get(Course.name == 'English 101')
        >>> engl_101.students.clear()

    .. note::
        For an overview of implementing many-to-many relationships using
        standard Peewee APIs, check out the :ref:`manytomany` section. For all
        but the most simple cases, you will be better off implementing
        many-to-many using the standard APIs.

    .. py:attribute:: through_model

        The :py:class:`Model` representing the many-to-many junction table.
        Will be auto-generated if not explicitly declared.

    .. py:method:: add(value[, clear_existing=True])

        :param value: Either a :py:class:`Model` instance, a list of model
            instances, or a :py:class:`SelectQuery`.
        :param bool clear_existing: Whether to remove existing relationships.

        Associate ``value`` with the current instance. You can pass in a single
        model instance, a list of model instances, or even a :py:class:`ModelSelect`.

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

    .. py:method:: remove(value)

        :param value: Either a :py:class:`Model` instance, a list of model
            instances, or a :py:class:`ModelSelect`.

        Disassociate ``value`` from the current instance. Like
        :py:meth:`~ManyToManyField.add`, you can pass in a model instance, a
        list of model instances, or even a :py:class:`ModelSelect`.

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

    .. py:method:: clear()

        Remove all associated objects.

        Example code:

        .. code-block:: python

            # English 101 is canceled this semester, so remove all
            # the enrollments.
            english_101 = Course.get(Course.name == 'English 101')
            english_101.students.clear()

    .. py:method:: get_through_model()

        Return the :py:class:`Model` representing the many-to-many junction
        table. This can be specified manually when the field is being
        instantiated using the ``through_model`` parameter. If a
        ``through_model`` is not specified, one will automatically be created.

        When creating tables for an application that uses
        :py:class:`ManyToManyField`, **you must create the through table expicitly**.

        .. code-block:: python

            # Get a reference to the automatically-created through table.
            StudentCourseThrough = Course.students.get_through_model()

            # Create tables for our two models as well as the through model.
            db.create_tables([
                Student,
                Course,
                StudentCourseThrough])

.. py:class:: DeferredThroughModel()

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

.. py:class:: CompositeKey(*field_names)

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


Schema Manager
--------------

.. py:class:: SchemaManager(model[, database=None[, **context_options]])

    :param Model model: Model class.
    :param Database database: If unspecified defaults to model._meta.database.

    Provides methods for managing the creation and deletion of tables and
    indexes for the given model.

    .. py:method:: create_table([safe=True[, **options]])

        :param bool safe: Specify IF NOT EXISTS clause.
        :param options: Arbitrary options.

        Execute CREATE TABLE query for the given model.

    .. py:method:: drop_table([safe=True[, drop_sequences=True[, **options]]])

        :param bool safe: Specify IF EXISTS clause.
        :param bool drop_sequences: Drop any sequences associated with the
            columns on the table (postgres only).
        :param options: Arbitrary options.

        Execute DROP TABLE query for the given model.

    .. py:method:: create_indexes([safe=True])

        :param bool safe: Specify IF NOT EXISTS clause.

        Execute CREATE INDEX queries for the indexes defined for the model.

    .. py:method:: drop_indexes([safe=True])

        :param bool safe: Specify IF EXISTS clause.

        Execute DROP INDEX queries for the indexes defined for the model.

    .. py:method:: create_sequence(field)

        :param Field field: Field instance which specifies a sequence.

        Create sequence for the given :py:class:`Field`.

    .. py:method:: drop_sequence(field)

        :param Field field: Field instance which specifies a sequence.

        Drop sequence for the given :py:class:`Field`.

    .. py:method:: create_foreign_key(field)

        :param ForeignKeyField field: Foreign-key field constraint to add.

        Add a foreign-key constraint for the given field. This method should
        not be necessary in most cases, as foreign-key constraints are created
        as part of table creation. The exception is when you are creating a
        circular foreign-key relationship using :py:class:`DeferredForeignKey`.
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

    .. py:method:: create_all([safe=True[, **table_options]])

        :param bool safe: Whether to specify IF NOT EXISTS.

        Create sequence(s), index(es) and table for the model.

    .. py:method:: drop_all([safe=True[, drop_sequences=True[, **options]]])

        :param bool safe: Whether to specify IF EXISTS.
        :param bool drop_sequences: Drop any sequences associated with the
            columns on the table (postgres only).
        :param options: Arbitrary options.

        Drop table for the model and associated indexes.


Model
-----

.. py:class:: Metadata(model[, database=None[, table_name=None[, indexes=None[, primary_key=None[, constraints=None[, schema=None[, only_save_dirty=False[, table_alias=None[, depends_on=None[, options=None[, without_rowid=False[, **kwargs]]]]]]]]]]]])

    :param Model model: Model class.
    :param Database database: database model is bound to.
    :param str table_name: Specify table name for model.
    :param list indexes: List of :py:class:`ModelIndex` objects.
    :param primary_key: Primary key for model (only specified if this is a
        :py:class:`CompositeKey` or ``False`` for no primary key.
    :param list constraints: List of table constraints.
    :param str schema: Schema table exists in.
    :param bool only_save_dirty: When :py:meth:`~Model.save` is called, only
        save the fields which have been modified.
    :param str table_alias: Specify preferred alias for table in queries.
    :param dict options: Arbitrary options for the model.
    :param bool without_rowid: Specify WITHOUT ROWID (sqlite only).
    :param kwargs: Arbitrary setting attributes and values.

    Store metadata for a :py:class:`Model`.

    This class should not be instantiated directly, but is instantiated using
    the attributes of a :py:class:`Model` class' inner ``Meta`` class. Metadata
    attributes are then available on ``Model._meta``.

    .. py:attribute:: table

        Return a reference to the underlying :py:class:`Table` object.

    .. py:method:: model_graph([refs=True[, backrefs=True[, depth_first=True]]])

        :param bool refs: Follow foreign-key references.
        :param bool backrefs: Follow foreign-key back-references.
        :param bool depth_first: Do a depth-first search (``False`` for
            breadth-first).

        Traverse the model graph and return a list of 3-tuples, consisting of
        ``(foreign key field, model class, is_backref)``.


.. py:class:: SubclassAwareMetadata

    Metadata subclass that tracks :py:class:`Model` subclasses.

    .. py:method:: map_models(fn)

        Apply a function to all subclasses.


.. py:class:: Model(**kwargs)

    :param kwargs: Mapping of field-name to value to initialize model with.

    Model class provides a high-level abstraction for working with database
    tables. Models are a one-to-one mapping with a database table (or a
    table-like object, such as a view). Subclasses of ``Model`` declare any
    number of :py:class:`Field` instances as class attributes. These fields
    correspond to columns on the table.

    Table-level operations, such as :py:meth:`~Model.select`,
    :py:meth:`~Model.update`, :py:meth:`~Model.insert` and
    :py:meth:`~Model.delete` are implemented as classmethods. Row-level
    operations, such as :py:meth:`~Model.save` and
    :py:meth:`~Model.delete_instance` are implemented as instancemethods.

    Example:

    .. code-block:: python

        db = SqliteDatabase(':memory:')

        class User(Model):
            username = TextField()
            join_date = DateTimeField(default=datetime.datetime.now)
            is_admin = BooleanField(default=False)

        admin = User(username='admin', is_admin=True)
        admin.save()

    .. py:classmethod:: alias([alias=None])

        :param str alias: Optional name for alias.
        :returns: :py:class:`ModelAlias` instance.

        Create an alias to the model-class. Model aliases allow you to
        reference the same :py:class:`Model` multiple times in a query, for
        example when doing a self-join or sub-query.

        Example:

        .. code-block:: pycon

            Parent = Category.alias()
            sq = (Category
                  .select(Category, Parent)
                  .join(Parent, on=(Category.parent == Parent.id))
                  .where(Parent.name == 'parent category'))

        .. note::
            When using a :py:class:`ModelAlias` in a join, you must explicitly
            specify the join condition.

    .. py:classmethod:: select(*fields)

        :param fields: A list of model classes, field instances, functions or
            expressions. If no arguments are provided, all columns for the
            given model will be selected by default.
        :returns: :py:class:`ModelSelect` query.

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

    .. py:classmethod:: update([__data=None[, **update]])

        :param dict __data: ``dict`` of fields to values.
        :param update: Field-name to value mapping.

        Create an UPDATE query.

        Example showing users being marked inactive if their registration has
        expired:

        .. code-block:: python

            q = (User
                 .update({User.active: False})
                 .where(User.registration_expired == True))
            q.execute()  # Execute the query, returning number of rows updated.

        Example showing an atomic update:

        .. code-block:: python

            q = (PageView
                 .update({PageView.count: PageView.count + 1})
                 .where(PageView.url == url))
            q.execute()  # Execute the query.

        .. note::
            When an update query is executed, the number of rows modified will
            be returned.

    .. py:classmethod:: insert([__data=None[, **insert]])

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

        You can also use :py:class:`Field` objects as the keys:

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

        .. note::
            When an insert query is executed on a table with an
            auto-incrementing primary key, the primary key of the new row will
            be returned.

    .. py:classmethod:: insert_many(rows[, fields=None])

        :param rows: An iterable that yields rows to insert.
        :param list fields: List of fields being inserted.

        INSERT multiple rows of data.

        The ``rows`` parameter must be an iterable that yields dictionaries or
        tuples, where the ordering of the tuple values corresponds to the
        fields specified in the ``fields`` argument. As with
        :py:meth:`~Model.insert`, fields that are not specified in the
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

        .. warning::
            If you are using SQLite, your SQLite library must be version 3.7.11
            or newer to take advantage of bulk inserts.

        .. note::
            SQLite has a default limit of 999 bound variables per statement.
            This limit can be modified at compile-time or at run-time, **but**
            if modifying at run-time, you can only specify a *lower* value than
            the default limit.

            For more information, check out the following SQLite documents:

            * `Max variable number limit <https://www.sqlite.org/limits.html#max_variable_number>`_
            * `Changing run-time limits <https://www.sqlite.org/c3ref/limit.html>`_
            * `SQLite compile-time flags <https://www.sqlite.org/compile.html>`_

    .. py:classmethod:: insert_from(query, fields)

        :param Select query: SELECT query to use as source of data.
        :param fields: Fields to insert data into.

        INSERT data using a SELECT query as the source. This API should be used
        for queries of the form *INSERT INTO ... SELECT FROM ...*.

        Example of inserting data across tables for denormalization purposes:

        .. code-block:: python

            source = (User
                      .select(User.username, fn.COUNT(Tweet.id))
                      .join(Tweet, JOIN.LEFT_OUTER)
                      .group_by(User.username))

            UserTweetDenorm.insert_from(
                source,
                [UserTweetDenorm.username, UserTweetDenorm.num_tweets]).execute()

    .. py:classmethod:: replace([__data=None[, **insert]])

        :param dict __data: ``dict`` of fields to values to insert.
        :param insert: Field-name to value mapping.

        Create an INSERT query that uses REPLACE for conflict-resolution.

        See :py:meth:`Model.insert` for examples.

    .. py:classmethod:: replace_many(rows[, fields=None])

        :param rows: An iterable that yields rows to insert.
        :param list fields: List of fields being inserted.

        INSERT multiple rows of data using REPLACE for conflict-resolution.

        See :py:meth:`Model.insert_many` for examples.

    .. py:classmethod:: raw(sql, *params)

        :param str sql: SQL query to execute.
        :param params: Parameters for query.

        Execute a SQL query directly.

        Example selecting rows from the User table:

        .. code-block:: python

            q = User.raw('select id, username from users')
            for user in q:
                print user.id, user.username

        .. note::
            Generally the use of ``raw`` is reserved for those cases where you
            can significantly optimize a select query. It is useful for select
            queries since it will return instances of the model.

    .. py:classmethod:: delete()

        Create a DELETE query.

        Example showing the deletion of all inactive users:

        .. code-block:: python

            q = User.delete().where(User.active == False)
            q.execute()  # Remove the rows, return number of rows removed.

        .. warning::
            This method performs a delete on the *entire table*. To delete a
            single instance, see :py:meth:`Model.delete_instance`.

    .. py:classmethod:: create(**query)

        :param query: Mapping of field-name to value.

        INSERT new row into table and return corresponding model instance.

        Example showing the creation of a user (a row will be added to the
        database):

        .. code-block:: python

            user = User.create(username='admin', password='test')

        .. note::
            The create() method is a shorthand for instantiate-then-save.

    .. py:classmethod:: get(*query, **filters)

        :param query: Zero or more :py:class:`Expression` objects.
        :param filters: Mapping of field-name to value for Django-style filter.
        :raises: :py:class:`DoesNotExist`
        :returns: Model instance matching the specified filters.

        Retrieve a single model instance matching the given filters. If no
        model is returned, a :py:class:`DoesNotExist` is raised.

        .. code-block:: python

            user = User.get(User.username == username, User.active == True)

        This method is also exposed via the :py:class:`SelectQuery`, though it
        takes no parameters:

        .. code-block:: python

            active = User.select().where(User.active == True)
            try:
                user = active.where(
                    (User.username == username) &
                    (User.active == True)
                ).get()
            except User.DoesNotExist:
                user = None

        .. note::
            The :py:meth:`~Model.get` method is shorthand for selecting with a
            limit of 1. It has the added behavior of raising an exception when
            no matching row is found. If more than one row is found, the first
            row returned by the database cursor will be used.

    .. py:classmethod:: get_or_none(*query, **filters)

        Identical to :py:meth:`Model.get` but returns ``None`` if no model
        matches the given filters.

    .. py:classmethod:: get_by_id(pk)

        :param pk: Primary-key value.

        Short-hand for calling :py:meth:`Model.get` specifying a lookup by
        primary key. Raises a :py:class:`DoesNotExist` if instance with the
        given primary key value does not exist.

        Example:

        .. code-block:: python

            user = User.get_by_id(1)  # Returns user with id = 1.

    .. py:classmethod:: set_by_id(key, value)

        :param key: Primary-key value.
        :param dict value: Mapping of field to value to update.

        Short-hand for updating the data with the given primary-key. If no row
        exists with the given primary key, no exception will be raised.

        Example:

        .. code-block:: python

            # Set "is_admin" to True on user with id=3.
            User.set_by_id(3, {'is_admin': True})

    .. py:classmethod:: delete_by_id(pk)

        :param pk: Primary-key value.

        Short-hand for deleting the row with the given primary-key. If no row
        exists with the given primary key, no exception will be raised.

    .. py:classmethod:: get_or_create(**kwargs)

        :param kwargs: Mapping of field-name to value.
        :param defaults: Default values to use if creating a new row.
        :returns: :py:class:`Model` instance.

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

    .. py:classmethod:: filter(*dq_nodes, **filters)

        :param dq_nodes: Zero or more :py:class:`DQ` objects.
        :param filters: Django-style filters.
        :returns: :py:class:`ModelSelect` query.

    .. py:method:: get_id()

        :returns: The primary-key of the model instance.

    .. py:method:: save([force_insert=False[, only=None]])

        :param bool force_insert: Force INSERT query.
        :param list only: Only save the given :py:class:`Field` instances.
        :returns: Number of rows modified.

        Save the data in the model instance. By default, the presence of a
        primary-key value will cause an UPDATE query to be executed.

        Example showing saving a model instance:

        .. code-block:: python

            user = User()
            user.username = 'some-user'  # does not touch the database
            user.save()  # change is persisted to the db

    .. py:attribute:: dirty_fields

        Return list of fields that have been modified.

        :rtype: list

        .. note::
            If you just want to persist modified fields, you can call
            ``model.save(only=model.dirty_fields)``.

            If you **always** want to only save a model's dirty fields, you can use the Meta
            option ``only_save_dirty = True``. Then, any time you call :py:meth:`Model.save()`,
            by default only the dirty fields will be saved, e.g.

            .. code-block:: python

                class Person(Model):
                    first_name = CharField()
                    last_name = CharField()
                    dob = DateField()

                    class Meta:
                        database = db
                        only_save_dirty = True

    .. py:method:: is_dirty()

        Return boolean indicating whether any fields were manually set.

    .. py:method:: delete_instance([recursive=False[, delete_nullable=False]])

        :param bool recursive: Delete related models.
        :param bool delete_nullable: Delete related models that have a null
            foreign key. If ``False`` nullable relations will be set to NULL.

        Delete the given instance.  Any foreign keys set to cascade on
        delete will be deleted automatically.  For more programmatic control,
        you can specify ``recursive=True``, which will delete any non-nullable
        related models (those that *are* nullable will be set to NULL).  If you
        wish to delete all dependencies regardless of whether they are nullable,
        set ``delete_nullable=True``.

        example:

        .. code-block:: python

            some_obj.delete_instance()  # it is gone forever

    .. py:classmethod:: bind(database[, bind_refs=True[, bind_backrefs=True]])

        :param Database database: database to bind to.
        :param bool bind_refs: Bind related models.
        :param bool bind_backrefs: Bind back-reference related models.

        Bind the model (and specified relations) to the given database.

        See also: :py:meth:`Database.bind`.

    .. py:classmethod:: bind_ctx(database[, bind_refs=True[, bind_backrefs=True]])

        Like :py:meth:`~Model.bind`, but returns a context manager that only
        binds the models for the duration of the wrapped block.

        See also: :py:meth:`Database.bind_ctx`.

    .. py:classmethod:: table_exists()

        :returns: boolean indicating whether the table exists.

    .. py:classmethod:: create_table([safe=True[, **options]])

        :param bool safe: If set to ``True``, the create table query will
            include an ``IF NOT EXISTS`` clause.

        Create the model table, indexes, constraints and sequences.

        Example:

        .. code-block:: python

            with database:
                SomeModel.create_table()  # Execute the create table query.

    .. py:classmethod:: drop_table([safe=True[, **options]])

        :param bool safe: If set to ``True``, the create table query will
            include an ``IF EXISTS`` clause.

        Drop the model table.

    .. py:classmethod:: index(*fields[, unique=False[, safe=True[, where=None[, using=None[, name=None]]]]])

        :param fields: Fields to index.
        :param bool unique: Whether index is UNIQUE.
        :param bool safe: Whether to add IF NOT EXISTS clause.
        :param Expression where: Optional WHERE clause for index.
        :param str using: Index algorithm.
        :param str name: Optional index name.

        Expressive method for declaring an index on a model. Wraps the
        declaration of a :py:class:`ModelIndex` instance.

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

    .. py:classmethod:: add_index(*args, **kwargs)

        :param args: a :py:class:`ModelIndex` instance, Field(s) to index,
            or a :py:class:`SQL` instance that contains the SQL for creating
            the index.
        :param kwargs: Keyword arguments passed to :py:class:`ModelIndex`
            constructor.

        Add an index to the model's definition.

        .. note::
            This method does not actually create the index in the database.
            Rather, it adds the index definition to the model's metadata, so
            that a subsequent call to :py:meth:`~Model.create_table` will
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

    .. py:method:: dependencies([search_nullable=False])

        :param bool search_nullable: Search models related via a nullable
            foreign key
        :rtype: Generator expression yielding queries and foreign key fields.

        Generate a list of queries of dependent models. Yields a 2-tuple
        containing the query and corresponding foreign key field.  Useful for
        searching dependencies of a model, i.e. things that would be orphaned
        in the event of a delete.

    .. py:method:: __iter__()

        :returns: a :py:class:`ModelSelect` for the given class.

        Convenience function for iterating over all instances of a model.

        Example:

        .. code-block:: python

            Setting.insert_many([
                {'key': 'host', 'value': '192.168.1.2'},
                {'key': 'port': 'value': '1337'},
                {'key': 'user': 'value': 'nuggie'}]).execute()

            # Load settings from db into dict.
            settings = {setting.key: setting.value for setting in Setting}

    .. py:method:: __len__()

        :returns: Count of rows in table.

        Example:

        .. code-block:: python

            n_accounts = len(Account)

            # Is equivalent to:
            n_accounts = Account.select().count()


.. py:class:: ModelAlias(model[, alias=None])

    :param Model model: Model class to reference.
    :param str alias: (optional) name for alias.

    Provide a separate reference to a model in a query.


.. py:class:: ModelSelect(model, fields_or_models)

    :param Model model: Model class to select.
    :param fields_or_models: List of fields or model classes to select.

    Model-specific implementation of SELECT query.

    .. py:method:: switch([ctx=None])

        :param ctx: A :py:class:`Model`, :py:class:`ModelAlias`, subquery, or
            other object that was joined-on.

        Switch the *join context* - the source which subsequent calls to
        :py:meth:`~ModelSelect.join` will be joined against. Used for
        specifying multiple joins against a single table.

        If the ``ctx`` is not given, then the query's model will be used.

        The following example selects from tweet and joins on both user and
        tweet-flag:

        .. code-block:: python

            sq = Tweet.select().join(User).switch(Tweet).join(TweetFlag)

            # Equivalent (since Tweet is the query's model)
            sq = Tweet.select().join(User).switch().join(TweetFlag)

    .. py:method:: objects([constructor=None])

        :param constructor: Constructor (defaults to returning model instances)

        Return result rows as objects created using the given constructor. The
        default behavior is to create model instances.

        .. note::
            This method can be used, when selecting field data from multiple
            sources/models, to make all data available as attributes on the
            model being queried (as opposed to constructing the graph of joined
            model instances). For very complex queries this can have a positive
            performance impact, especially iterating large result sets.

            Similarly, you can use :py:meth:`~BaseQuery.dicts`,
            :py:meth:`~BaseQuery.tuples` or :py:meth:`~BaseQuery.namedtuples`
            to achieve even more performance.

    .. py:method:: join(dest[, join_type='INNER'[, on=None[, src=None[, attr=None]]]])

        :param dest: A :py:class:`Model`, :py:class:`ModelAlias`,
            :py:class:`Select` query, or other object to join to.
        :param str join_type: Join type, defaults to INNER.
        :param on: Join predicate or a :py:class:`ForeignKeyField` to join on.
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
        See the :py:ref:`example app <example-app>` for a real-life usage:

        .. code-block:: python

            sq = User.select().join(Relationship, on=Relationship.to_user)

    .. py:method:: join_from(src, dest[, join_type='INNER'[, on=None[, attr=None]]])

        :param src: Source for join.
        :param dest: Table to join to.

        Use same parameter order as the non-model-specific
        :py:meth:`~ModelSelect.join`. Bypasses the *join context* by requiring
        the join source to be specified.

    .. py:method:: filter(*args, **kwargs)

        :param args: Zero or more :py:class:`DQ` objects.
        :param kwargs: Django-style keyword-argument filters.

        Use Django-style filters to express a WHERE clause.

    .. py:method:: prefetch(*subqueries)

        :param subqueries: A list of :py:class:`Model` classes or select
            queries to prefetch.

        Execute the query, prefetching the given additional resources.

        See also :py:func:`prefetch` standalone function.

        Example:

        .. code-block:: python

            # Fetch all Users and prefetch their associated tweets.
            query = User.select().prefetch(Tweet)
            for user in query:
                print(user.username)
                for tweet in user.tweets:
                    print('  *', tweet.content)


.. py:function:: prefetch(sq, *subqueries)

    :param sq: Query to use as starting-point.
    :param subqueries: One or more models or :py:class:`ModelSelect` queries
        to eagerly fetch.

    Eagerly fetch related objects, allowing efficient querying of multiple
    tables when a 1-to-many relationship exists.

    For example, it is simple to query a many-to-1 relationship efficiently::

        query = (Tweet
                 .select(Tweet, User)
                 .join(User))
        for tweet in query:
            # Looking up tweet.user.username does not require a query since
            # the related user's columns were selected.
            print(tweet.user.username, '->', tweet.content)

    To efficiently do the inverse, query users and their tweets, you can use
    prefetch::

        query = User.select()
        for user in prefetch(query, Tweet):
            print(user.username)
            for tweet in user.tweets:  # Does not require additional query.
                print('    ', tweet.content)


Query-builder Internals
-----------------------

.. py:class:: AliasManager()

    Manages the aliases assigned to :py:class:`Source` objects in SELECT
    queries, so as to avoid ambiguous references when multiple sources are
    used in a single query.

    .. py:method:: add(source)

        Add a source to the AliasManager's internal registry at the current
        scope. The alias will be automatically generated using the following
        scheme (where each level of indentation refers to a new scope):

        :param Source source: Make the manager aware of a new source. If the
            source has already been added, the call is a no-op.

    .. py:method:: get(source[, any_depth=False])

        Return the alias for the source in the current scope. If the source
        does not have an alias, it will be given the next available alias.

        :param Source source: The source whose alias should be retrieved.
        :returns: The alias already assigned to the source, or the next
            available alias.
        :rtype: str

    .. py:method:: __setitem__(source, alias)

        Manually set the alias for the source at the current scope.

        :param Source source: The source for which we set the alias.

    .. py:method:: push()

        Push a new scope onto the stack.

    .. py:method:: pop()

        Pop scope from the stack.


.. py:class:: State(scope[, parentheses=False[, subquery=False[, **kwargs]]])

    Lightweight object for representing the state at a given scope. During SQL
    generation, each object visited by the :py:class:`Context` can inspect the
    state. The :py:class:`State` class allows Peewee to do things like:

    * Use a common interface for field types or SQL expressions, but use
      vendor-specific data-types or operators.
    * Compile a :py:class:`Column` instance into a fully-qualified attribute,
      as a named alias, etc, depending on the value of the ``scope``.
    * Ensure parentheses are used appropriately.

    :param int scope: The scope rules to be applied while the state is active.
    :param bool parentheses: Wrap the contained SQL in parentheses.
    :param bool subquery: Whether the current state is a child of an outer
        query.
    :param dict kwargs: Arbitrary settings which should be applied in the
        current state.


.. py:class:: Context(**settings)

    Converts Peewee structures into parameterized SQL queries.

    Peewee structures should all implement a `__sql__` method, which will be
    called by the `Context` class during SQL generation. The `__sql__` method
    accepts a single parameter, the `Context` instance, which allows for
    recursive descent and introspection of scope and state.

    .. py:attribute:: scope

        Return the currently-active scope rules.

    .. py:attribute:: parentheses

        Return whether the current state is wrapped in parentheses.

    .. py:attribute:: subquery

        Return whether the current state is the child of another query.

    .. py:method:: scope_normal([**kwargs])

        The default scope. Sources are referred to by alias, columns by
        dotted-path from the source.

    .. py:method:: scope_source([**kwargs])

        Scope used when defining sources, e.g. in the column list and FROM
        clause of a SELECT query. This scope is used for defining the
        fully-qualified name of the source and assigning an alias.

    .. py:method:: scope_values([**kwargs])

        Scope used for UPDATE, INSERT or DELETE queries, where instead of
        referencing a source by an alias, we refer to it directly. Similarly,
        since there is a single table, columns do not need to be referenced
        by dotted-path.

    .. py:method:: scope_cte([**kwargs])

        Scope used when generating the contents of a common-table-expression.
        Used after a WITH statement, when generating the definition for a CTE
        (as opposed to merely a reference to one).

    .. py:method:: scope_column([**kwargs])

        Scope used when generating SQL for a column. Ensures that the column is
        rendered with it's correct alias. Was needed because when referencing
        the inner projection of a sub-select, Peewee would render the full
        SELECT query as the "source" of the column (instead of the query's
        alias + . + column).  This scope allows us to avoid rendering the full
        query when we only need the alias.

    .. py:method:: sql(obj)

        Append a composable Node object, sub-context, or other object to the
        query AST. Python values, such as integers, strings, floats, etc. are
        treated as parameterized values.

        :returns: The updated Context object.

    .. py:method:: literal(keyword)

        Append a string-literal to the current query AST.

        :returns: The updated Context object.

    .. py:method:: parse(node)

        :param Node node: Instance of a Node subclass.
        :returns: a 2-tuple consisting of (sql, parameters).

        Convert the given node to a SQL AST and return a 2-tuple consisting
        of the SQL query and the parameters.

    .. py:method:: query()

        :returns: a 2-tuple consisting of (sql, parameters) for the context.


Constants and Helpers
---------------------

.. py:class:: Proxy()

    Create a proxy or placeholder for another object.

    .. py:method:: initialize(obj)

        :param obj: Object to proxy to.

        Bind the proxy to the given object. Afterwards all attribute lookups
        and method calls on the proxy will be sent to the given object.

        Any callbacks that have been registered will be called.

    .. py:method:: attach_callback(callback)

        :param callback: A function that accepts a single parameter, the bound
            object.
        :returns: self

        Add a callback to be executed when the proxy is initialized.

