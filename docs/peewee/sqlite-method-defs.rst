.. py:method:: pragma(key, value=SENTINEL, permanent=False)

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

.. py:method:: register_aggregate(klass, name=None, num_params=-1)

    :param klass: Class implementing aggregate API.
    :param str name: Aggregate function name (defaults to name of class).
    :param int num_params: Number of parameters the aggregate accepts, or
        -1 for any number.

    Register a user-defined aggregate function.

    The function will be registered each time a new connection is opened.
    Additionally, if a connection is already open, the aggregate will be
    registered with the open connection.

.. py:method:: aggregate(name=None, num_params=-1)

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

.. py:method:: register_collation(fn, name=None)

    :param fn: The collation function.
    :param str name: Name of collation (defaults to function name)

    Register a user-defined collation. The collation will be registered
    each time a new connection is opened.  Additionally, if a connection is
    already open, the collation will be registered with the open
    connection.

.. py:method:: collation(name=None)

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

.. py:method:: register_function(fn, name=None, num_params=-1, deterministic=None)

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

.. py:method:: func(name=None, num_params=-1, deterministic=None)

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

        # Usage:
        title_case_books = Book.select(fn.title_case(Book.title))

.. py:method:: register_window_function(klass, name=None, num_params=-1)

    :param klass: Class implementing window function API.
    :param str name: Window function name (defaults to name of class).
    :param int num_params: Number of parameters the function accepts, or
        -1 for any number.

    Register a user-defined window function.

    .. attention:: This feature requires SQLite >= 3.25.0.

    The window function will be registered each time a new connection is
    opened. Additionally, if a connection is already open, the window
    function will be registered with the open connection.

.. py:method:: window_function(name=None, num_params=-1)

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

.. py:method:: unregister_aggregate(name)

    :param name: Name of the user-defined aggregate function.

    Unregister the user-defined aggregate function.

.. py:method:: unregister_collation(name)

    :param name: Name of the user-defined collation.

    Unregister the user-defined collation.

.. py:method:: unregister_function(name)

    :param name: Name of the user-defined scalar function.

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
    call to ``attach()``. If the main database is currently connected, the
    attached database will be detached from the open connection.

.. py:method:: atomic(lock_type=None)

    :param str lock_type: Locking strategy: DEFERRED, IMMEDIATE, EXCLUSIVE.

    Create an atomic context-manager, optionally using the specified
    locking strategy (if unspecified, DEFERRED is used).

    .. note:: Lock type only applies to the outermost ``atomic()`` block.

.. py:method:: transaction(lock_type=None)

    :param str lock_type: Locking strategy: DEFERRED, IMMEDIATE, EXCLUSIVE.

    Create a transaction context-manager using the specified locking
    strategy (defaults to DEFERRED).
