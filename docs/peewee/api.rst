.. _api:

.. py:module:: peewee

API Documentation
=================

This document specifies Peewee's APIs.

Database
--------

.. py:class:: Database(database[, thread_safe=True[, autorollback=False[,
    field_types=None[, operations=None[, **kwargs]]]]])

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

        :param list models: List of models to bind to the database.
        :param bool bind_refs: Bind models that are referenced using
            foreign-keys.
        :param bool bind_backrefs: Bind models that reference the given model
            with a foreign-key.

        Create a context-manager that binds (associates) the given models with
        the current database for the duration of the wrapped block.

.. py:class:: SqliteDatabase(database[, pragmas=None[, timeout=5[, **kwargs]]])

    Sqlite database implementation.

    Additional optional keyword-parameters:

    :param list pragmas: A list of 2-tuples containing pragma key and value to
        set whenever a connection is opened.
    :param timeout: Set the busy-timeout on the SQLite driver (in seconds).

    Example of using PRAGMAs::

        db = SqliteDatabase('my_app.db', pragmas=(
            ('cache_size', -16000),  # 16MB
            ('journal_mode', 'wal'),  # Use write-ahead-log journal mode.
        ))

    .. py:method:: pragma(key[, value=SENTINEL])

        :param key: Setting name.
        :param value: New value for the setting (optional).

        Execute a PRAGMA query once on the active connection. If a value is not
        specified, then the current value will be returned.

        .. note::
            This only affects the current connection. If the PRAGMA being
            executed is not persistent, then it will only be in effect for the
            lifetime of the connection (or until over-written).

    .. py:attribute:: cache_size

        Get or set the cache_size pragma.

    .. py:attribute:: foreign_keys

        Get or set the foreign_keys pragma.

    .. py:attribute:: journal_mode

        Get or set the journal_mode pragma.

    .. py:attribute:: journal_size_limit

        Get or set the journal_size_limit pragma.

    .. py:attribute:: mmap_size

        Get or set the mmap_size pragma.

    .. py:attribute:: page_size

        Get or set the page_size pragma.

    .. py:attribute:: read_uncommitted

        Get or set the read_uncommitted pragma.

    .. py:attribute:: synchronous

        Get or set the synchronous pragma.

    .. py:attribute:: wal_autocheckpoint

        Get or set the wal_autocheckpoint pragma.

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

        Decorator to register a user-defined aggregate function.

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

    .. py:method:: unregister_aggregate(name)

        :param name: Name of the user-defined aggregate function.

        Unregister the user-defined aggregate function.

    .. py:method:: unregister_collation(name)

        :param name: Name of the user-defined collation.

        Unregister the user-defined collation.

    .. py:method:: unregister_function(name)

        :param name: Name of the user-defined scalar function.

        Unregister the user-defined scalar function.

    .. py:method:: transaction([lock_type=None])

        :param str lock_type: Locking strategy: DEFERRED, IMMEDIATE, EXCLUSIVE.

        Create a transaction context-manager using the specified locking
        strategy (defaults to DEFERRED).


.. py:class:: PostgresqlDatabase(database[, register_unicode=True[,
    encoding=None]])

    Postgresql database implementation.

    Additional optional keyword-parameters:

    :param bool register_unicode: Register unicode types.
    :param str encoding: Database encoding.


.. py:class:: MySQLDatabase(database[, **kwargs])

    MySQL database implementation.


Query-builder
-------------

.. py:class:: Node()

    Base-class for all components which make up the AST for a SQL query.

    .. py:staticmethod:: copy(method)

        Decorator to use with Node methods that mutate the node's state.
        This allows method-chaining, e.g.:

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


.. py:class:: Table(name[, columns=None[, primary_key=None[, schema=None[,
    alias=None]]]])

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


.. py:class:: CTE(name, query[, recursive=False[, columns=None]])

    Represent a common-table-expression.

    :param name: Name for the CTE.
    :param query: :py:class:`Select` query describing CTE.
    :param bool recursive: Whether the CTE is recursive.
    :param list columns: Explicit list of columns produced by CTE (optional).


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

    .. py:method:: over([partition_by=None[, order_by=None[, start=None[,
        end=None[, window=None]]]]])

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


.. py:class:: Window([partition_by=None[, order_by=None[, start=None[,
    end=None[, alias=None]]]]])

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


.. py:class:: OnConflict([action=None[, update=None[, preserve=None[,
    where=None[, conflict_target=None]]]]])

    :param str action: Action to take when resolving conflict.
    :param update: A dictionary mapping column to new value.
    :param preserve: A list of columns whose values should be preserved.
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

    Base-class implementing common query methods.

    .. py:attribute:: default_row_type = ROW.DICT

    .. py:method:: bind([database=None])

        :param Database database: Database to execute query against.

        Bind the query to the given database for execution.

    .. py:method:: dicts([as_dict=True])

        :param bool as_dict: Specify whether to return rows as dictionaries.

        Return rows as dictionaries.

    .. py:method:: as_tuples([as_tuples=True])

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
        executed).

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


.. py:class:: Query([where=None[, order_by=None[, limit=None[, offset=None[,
    **kwargs]]]]])

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


.. py:class:: SelectQuery()

    Select query helper-class that implements operator-overloads for creating
    compound queries.

    .. py:method:: __add__(dest)

        Create a UNION ALL query with ``dest``.

    .. py:method:: __or__(dest)

        Create a UNION query with ``dest``.

    .. py:method:: __and__(dest)

        Create an INTERSECT query with ``dest``.

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


.. py:class:: Select([from_list=None[, columns=None[, group_by=None[,
    having=None[, distinct=None[, windows=None[, for_update=None[,
    **kwargs]]]]]]]])

    :param list from_list: List of sources for FROM clause.
    :param list columns: Columns or values to select.
    :param list group_by: List of columns or values to group by.
    :param Expression having: Expression for HAVING clause.
    :param distinct: Either a boolean or a list of column-like objects.
    :param list windows: List of :py:class:`Window` clauses.
    :param for_update: Boolean or str indicating if SELECT...FOR UPDATE.

    Class representing a SELECT query.

    .. note::
        While it is possible to instantiate the query, more commonly you will
        build the query using the method-chaining APIs.

    .. py:method:: columns(*columns)

        :param columns: Zero or more column-like objects to SELECT.

        Specify which columns or column-like values to SELECT.

    .. py:method:: from_(*sources)

        :param sources: Zero or more sources for the FROM clause.

        Specify which table-like objects should be used in the FROM clause.

    .. py:method:: join(dest[, join_type='INNER'[, on=None]])

        :param dest: A table or table-like object.
        :param str join_type: Type of JOIN, default is "INNER".
        :param Expression on: Join predicate.

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


.. py:class:: Insert(table[, insert=None[, columns=None[, on_conflict=None[,
    **kwargs]]]])

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

    .. py:method:: on_conflict(*args, **kwargs)

        Specify an ON CONFLICT clause by populating a :py:class:`OnConflict`
        object.


.. py:class:: Delete()

    Class representing a DELETE query.


.. py:class:: Index(name, table, expressions[, unique=False[, safe=False[,
    where=None[, using=None]]]])

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


.. py:class:: ModelIndex(model, fields[, unique=False[, safe=True[,
    where=None[, using=None[, name=None]]]]])

    :param Model model: Model class to create index on.
    :param list fields: Fields to index.
    :param bool unique: Whether index is UNIQUE.
    :param bool safe: Whether to add IF NOT EXISTS clause.
    :param Expression where: Optional WHERE clause for index.
    :param str using: Index algorithm.
    :param str name: Optional index name.


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

