.. _cysqlite:

cysqlite Extension
==================

SQLite database implementation using `cysqlite <https://cysqlite.readthedocs.io/>`_
as the driver.

.. py:class:: CySqliteDatabase(database[, pragmas=None[, timeout=5[, rank_functions=True[, regexp_function=False[, json_contains=False]]]]])

    :param list pragmas: A list of 2-tuples containing pragma key and value to
        set every time a connection is opened.
    :param timeout: Set the busy-timeout on the SQLite driver (in seconds).
    :param bool rank_functions: Make search result ranking functions available.
    :param bool regexp_function: Make the REGEXP function available.
    :param bool json_contains: Make json_containts() function available.

    Extends :py:class:`SqliteDatabase` and inherits methods for declaring
    user-defined functions, aggregates, window functions, collations, pragmas,
    etc.

    Example:

    .. code-block:: python

        db = CySqliteDatabase('app.db', pragmas={'journal_mode': 'wal'})

    .. py:method:: table_function([name=None])

        Class-decorator for registering a ``cysqlite.TableFunction``. Table
        functions are user-defined functions that, rather than returning a
        single, scalar value, can return any number of rows of tabular data.

        See `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#tablefunction>`_ for details on
        ``TableFunction`` API.

        Example:

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

            # Usage:
            cursor = db.execute_sql('SELECT * FROM series(?, ?, ?)', (0, 5, 2))
            for value, in cursor:
                print(value)

            # Prints:
            # 0
            # 2
            # 4

    .. py:method:: unregister_table_function(name)

        :param name: Name of the user-defined table function.
        :returns: True or False, depending on whether the function was removed.

        Unregister the user-defined scalar function.

    .. py:method:: on_commit(fn)

        :param fn: callable or ``None`` to clear the current hook.

        Register a callback to be executed whenever a transaction is committed
        on the current connection. The callback accepts no parameters and the
        return value is ignored.

        However, if the callback raises a :py:class:`ValueError`, the
        transaction will be aborted and rolled-back.

        Example:

        .. code-block:: python

            db = CySqliteDatabase(':memory:')

            @db.on_commit
            def on_commit():
                logger.info('COMMITing changes')

    .. py:method:: on_rollback(fn)

        :param fn: callable or ``None`` to clear the current hook.

        Register a callback to be executed whenever a transaction is rolled
        back on the current connection. The callback accepts no parameters and
        the return value is ignored.

        Example:

        .. code-block:: python

            @db.on_rollback
            def on_rollback():
                logger.info('Rolling back changes')

    .. py:method:: on_update(fn)

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

    .. py:method:: authorizer(fn)

        :param fn: callable or ``None`` to clear the current authorizer.

        Register an authorizer callback. Authorizer callbacks must accept 5
        parameters, which vary depending on the operation being checked.

        * op: operation code, e.g. ``cysqlite.C_SQLITE_INSERT``.
        * p1: operation-specific value, e.g. table name for ``C_SQLITE_INSERT``.
        * p2: operation-specific value.
        * p3: database name, e.g. ``"main"``.
        * p4: inner-most trigger or view responsible for the access attempt if
          applicable, else ``None``.

        See `sqlite authorizer documentation <https://www.sqlite.org/c3ref/c_alter_table.html>`_
        for description of authorizer codes and values for parameters p1 and p2.

        The authorizer callback must return one of:

        * ``cysqlite.C_SQLITE_OK``: allow operation.
        * ``cysqlite.C_SQLITE_IGNORE``: allow statement compilation but prevent
          the operation from occuring.
        * ``cysqlite.C_SQLITE_DENY``: prevent statement compilation.

        More details can be found in the `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#Connection.authorizer>`_.

    .. py:method:: trace(fn, mask=2):

        :param fn: callable or ``None`` to clear the current trace hook.
        :param int mask: mask of what types of events to trace. Default value
            corresponds to ``SQLITE_TRACE_PROFILE``.

        Register a trace hook (``sqlite3_trace_v2``). Trace callback must
        accept 4 parameters, which vary depending on the operation being
        traced.

        * event: type of event, e.g. ``cysqlite.TRACE_PROFILE``.
        * sid: memory address of statement (only ``cysqlite.TRACE_CLOSE``), else -1.
        * sql: SQL string (only ``cysqlite.TRACE_STMT``), else None.
        * ns: estimated number of nanoseconds the statement took to run (only
          ``cysqlite.TRACE_PROFILE``), else -1.

        Any return value from callback is ignored.

        More details can be found in the `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#Connection.trace>`_.

    .. py:method:: progress(fn, n=1)

        :param fn: callable or ``None`` to clear the current progress handler.
        :param int n: approximate number of VM instructions to execute between
          calls to the progress handler.

        Register a progress handler (``sqlite3_progress_handler``). Callback
        takes no arguments and returns 0 to allow progress to continue or any
        non-zero value to interrupt progress.

        More details can be found in the `cysqlite docs <https://cysqlite.readthedocs.io/en/latest/api.html#Connection.progress>`_.

    .. py:attribute:: autocommit

        Property which returns a boolean indicating if autocommit is enabled.
        By default, this value will be ``True`` except when inside a
        transaction (or :py:meth:`~Database.atomic` block).

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

    .. py:method:: backup(destination[, pages=None, name=None, progress=None])

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

    .. py:method:: backup_to_file(filename[, pages, name, progress])

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

    .. py:method:: blob_open(table, column, rowid[, read_only=False])

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
            rowid = Image.insert({Image.filename: 'thefile.jpg',
                                  Image.data: ZeroBlob(buf_size)}).execute()

            # Open the blob, returning a file-like object.
            blob = db.blob_open('image', 'data', rowid)

            # Write some data to the blob.
            blob.write(image_data)
            img_size = blob.tell()

            # Read the data back out of the blob.
            blob.seek(0)
            image_data = blob.read(img_size)
