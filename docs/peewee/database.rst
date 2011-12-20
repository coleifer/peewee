.. _databases:

Databases
=========

Below the :py:class:`Model` level, peewee uses an abstraction for representing the database.  The
:py:class:`Database` is responsible for establishing and closing connections, making queries,
and gathering information from the database.

The :py:class:`Database` in turn uses another abstraction called an :py:class:`Adapter`, which
is backend-specific and encapsulates functionality specific to a given db driver.  Since there
is some difference in column types across database engines, this information also resides
in the adapter.  The adapter is responsible for smoothing out the quirks of each database
driver to provide a consistent interface, for example sqlite uses the question-mark "?" character
for parameter interpolation, while all the other backends use "%s".

.. note::
    The internals of the :py:class:`Database` and :py:class:`BaseAdapter` will be
    of interest to anyone interested in adding support for another database driver.

Database and its subclasses
---------------------------

.. py:class:: Database

    A high-level api for working with the supported database engines.  ``Database``
    provides a wrapper around some of the functions performed by the ``Adapter``,
    in addition providing support for:
    
    - execution of SQL queries
    - creating and dropping tables and indexes
    
    .. py:method:: __init__(adapter, database[, threadlocals=False[, autocommit=True[, **connect_kwargs]]])
    
        :param adapter: an instance of a :py:class:`BaseAdapter` subclass
        :param database: the name of the database (or filename if using sqlite)
        :param threadlocals: whether to store connections in a threadlocal
        :param autocommit: automatically commit every query executed by calling :py:meth:`~Database.execute`
        :param connect_kwargs: any arbitrary parameters to pass to the database driver when connecting
    
    .. py:method:: connect()
    
        Establishes a connection to the database
        
        .. note::
            If you initialized with ``threadlocals=True``, then this will store
            the connection inside a threadlocal, ensuring that connections are not
            shared across threads.
    
    .. py:method:: close()
    
        Closes the connection to the database (if one is open)
        
        .. note::
            If you initialized with ``threadlocals=True``, only a connection local
            to the calling thread will be closed.
    
    .. py:method:: get_conn()
    
        :rtype: a connection to the database, creates one if does not exist
    
    .. py:method:: get_cursor()
    
        :rtype: a cursor for executing queries
    
    .. py:method:: set_autocommit(autocommit)
    
        :param autocommit: a boolean value indicating whether to turn on/off autocommit
            **for the current connection**
    
    .. py:method:: get_autocommit()
    
        :rtype: a boolean value indicating whether autocommit is on **for the current connection**
    
    .. py:method:: execute(sql[, params=None])
    
        :param sql: a string sql query
        :param params: a list or tuple of parameters to interpolate
        
        .. note::
            You can configure whether queries will automatically commit by using
            the :py:meth:`~Database.set_autocommit` and :py:meth:`Database.get_autocommit`
            methods.
    
    .. py:method:: commit()
        
        Call ``commit()`` on the active connection, committing the current transaction
    
    .. py:method:: rollback()
    
        Call ``rollback()`` on the active connection, rolling back the current transaction
    
    .. py:method:: commit_on_success(func)
    
        Decorator that wraps the given function in a single transaction, which,
        upon success will be committed.  If an error is raised inside the function,
        the transaction will be rolled back and the error will be re-raised.
    
        :param func: function to decorate
        
        .. code-block:: python
        
            @database.commit_on_success
            def transfer_money(from_acct, to_acct, amt):
                from_acct.charge(amt)
                to_acct.pay(amt)
                return amt
    
    .. py:method:: last_insert_id(cursor, model)
    
        :param cursor: the database cursor used to perform the insert query
        :param model: the model class that was just created
        :rtype: the primary key of the most recently inserted instance
    
    .. py:method:: rows_affected(cursor)
    
        :rtype: number of rows affected by the last query
    
    .. py:method:: create_table(model_class[, safe=False])
    
        :param model_class: :py:class:`Model` class to create table for
        :param safe: if ``True``, query will add a ``IF NOT EXISTS`` clause
    
    .. py:method:: create_index(model_class, field_name[, unique=False])
    
        :param model_class: :py:class:`Model` table on which to create index
        :param field_name: name of field to create index on
        :param unique: whether the index should enforce uniqueness

    .. py:method:: create_foreign_key(model_class, field)
    
        :param model_class: :py:class:`Model` table on which to create foreign key index / constraint
        :param field: :py:class:`Field` object 
    
    .. py:method:: drop_table(model_class[, fail_silently=False])
    
        :param model_class: :py:class:`Model` table to drop
        :param fail_silently: if ``True``, query will add a ``IF EXISTS`` clause
        
        .. note::
            Cascading drop tables are not supported at this time, so if a constraint
            exists that prevents a table being dropped, you will need to handle
            that in application logic.
    
    .. py:method:: create_sequence(sequence_name)
    
        :param sequence_name: name of sequence to create
        
        .. note:: only works with database engines that support sequences
    
    .. py:method:: drop_sequence(sequence_name)
    
        :param sequence_name: name of sequence to drop
        
        .. note:: only works with database engines that support sequences
    
    .. py:method:: get_indexes_for_table(table)
    
        :param table: the name of table to introspect
        :rtype: a list of ``(index_name, is_unique)`` tuples
    
        .. warning::
            Not implemented -- implementations exist in subclasses
    
    .. py:method:: get_tables()
    
        :rtype: a list of table names in the database
        
        .. warning::
            Not implemented -- implementations exist in subclasses
    
    .. py:method:: sequence_exists(sequence_name)
    
        :rtype boolean:


.. py:class:: SqliteDatabase(Database)

    :py:class:`Database` subclass that communicates to the "sqlite3" driver

.. py:class:: MySQLDatabase(Database)

    :py:class:`Database` subclass that communicates to the "MySQLdb" driver

.. py:class:: PostgresqlDatabase(Database)

    :py:class:`Database` subclass that communicates to the "psycopg2" driver


BaseAdapter and its subclasses
------------------------------

.. py:class:: BaseAdapter

    The various subclasses of `BaseAdapter` provide a bridge between the high-
    level :py:class:`Database` abstraction and the underlying python libraries like
    psycopg2.  It also provides a way to unify the pythonic field types with
    the underlying column types used by the database engine.
    
    The `BaseAdapter` provides two types of mappings:    
    - mapping between filter operations and their database equivalents
    - mapping between basic field types and their database column types
    
    The `BaseAdapter` also is the mechanism used by the :py:class:`Database` class to:
    - handle connections with the database
    - extract information from the database cursor
    
    .. py:attribute:: operations = {'eq': '= %s'}
    
        A mapping of query operation to SQL
    
    .. py:attribute:: interpolation = '%s'
    
        The string used by the driver to interpolate query parameters
    
    .. py:attribute:: sequence_support = False
    
        Whether the given backend supports sequences
    
    .. py:attribute:: reserved_tables = []
    
        Table names that are reserved by the backend -- if encountered in the
        application a warning will be issued.
    
    .. py:method:: get_field_types()
    
        :rtype: a dictionary mapping "user-friendly field type" to specific column type,
            e.g. ``{'string': 'VARCHAR', 'float': 'REAL', ... }``
    
    .. py:method:: get_field_type_overrides()
    
        :rtype: a dictionary similar to that returned by ``get_field_types()``.
        
        Provides a mechanism to override any number of field types without having
        to override all of them.
    
    .. py:method:: connect(database, **kwargs)
    
        :param database: string representing database name (or filename if using sqlite)
        :param kwargs: any keyword arguments to pass along to the database driver when connecting
        :rtype: a database connection
    
    .. py:method:: close(conn)
    
        :param conn: a database connection
        
        Close the given database connection
    
    .. py:method:: lookup_cast(lookup, value)
    
        :param lookup: a string representing the lookup type
        :param value: a python value that will be passed in to the lookup
        :rtype: a converted value appropriate for the given lookup
        
        Used as a hook when a specific lookup requires altering the given value,
        like for example when performing a LIKE query you may need to insert wildcards.
    
    .. py:method:: last_insert_id(cursor, model)
    
        :rtype: most recently inserted primary key
    
    .. py:method:: rows_affected(cursor)
    
        :rtype: number of rows affected by most recent query


.. py:class:: SqliteAdapter(BaseAdapter)

    Subclass of :py:class:`BaseAdapter` that works with the "sqlite3" driver

.. py:class:: MySQLAdapter(BaseAdapter)

    Subclass of :py:class:`BaseAdapter` that works with the "MySQLdb" driver

.. py:class:: PostgresqlAdapter(BaseAdapter)

    Subclass of :py:class:`BaseAdapter` that works with the "psycopg2" driver
